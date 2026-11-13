"""공공데이터포털 호출: 인증키, 재시도, 본문 속 오류 감지, 페이지 넘기기.

인증키는 환경변수(DATA_GO_KR_KEY)에서만 읽는다. 주소·오류 문구에 키를 남기지 않는다.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

KEY_ENV = "DATA_GO_KR_KEY"
OK_CODES = {"0", "00", "000"}
NODATA_CODES = {"3", "03"}
QUOTA_CODES = {"22"}
AUTH_CODES = {"20", "30", "31", "32", "33"}


class ApiError(Exception):
    def __init__(self, msg: str, code: str = ""):
        super().__init__(msg)
        self.code = code


class QuotaExceeded(ApiError):
    """하루 호출 한도 초과 — 내일 이어서 받으면 된다."""


class AuthError(ApiError):
    """인증키 문제 — 재시도해도 소용없다."""


class TransientError(ApiError):
    """일시 오류 — 재시도 대상."""


def service_key(env: str = KEY_ENV) -> str:
    return os.environ.get(env, "").strip()


def encode_key(key: str) -> str:
    # 포털이 주는 'Encoding' 키(이미 % 포함)와 'Decoding' 키 둘 다 받는다.
    return key if "%" in key else urllib.parse.quote(key, safe="")


def build_url(base: str, params: dict, key: str, key_name: str = "serviceKey") -> str:
    return f"{base}?{key_name}={encode_key(key)}&{urllib.parse.urlencode(params)}"


def http_get(url: str, timeout: float = 30, headers: dict | None = None) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "apt-dashboard/1.0", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        raise TransientError(f"네트워크 오류: {type(e).__name__}") from None


def _classify(code: str, msg: str) -> ApiError:
    code = (code or "").strip()
    up = (msg or "").upper()
    if code in QUOTA_CODES or "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS" in up:
        return QuotaExceeded(f"하루 호출 한도 초과({code} {msg})", code)
    if code in AUTH_CODES or "SERVICE_KEY" in up or "SERVICE KEY" in up or "UNREGISTERED" in up:
        return AuthError(f"인증키 오류({code} {msg})", code)
    return TransientError(f"API 오류({code} {msg})", code)


def parse_xml_page(text: str) -> tuple[list[dict], int]:
    """XML 응답 한 쪽을 (행 목록, 전체 건수)로 바꾼다. HTTP 200 이어도 본문 속 오류를 잡아낸다."""
    body = (text or "").strip()
    if not body.startswith("<"):
        raise TransientError("XML 이 아닌 응답")
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        raise TransientError("XML 해석 실패") from None
    if root.tag == "OpenAPI_ServiceResponse":  # 게이트웨이 오류 형식
        raise _classify(root.findtext(".//returnReasonCode", ""),
                        root.findtext(".//returnAuthMsg", "") or root.findtext(".//errMsg", ""))
    code = (root.findtext("./header/resultCode") or "").strip()
    msg = (root.findtext("./header/resultMsg") or "").strip()
    if code in NODATA_CODES:
        return [], 0
    if code not in OK_CODES:
        raise _classify(code, msg)
    items = [{c.tag: (c.text or "").strip() for c in it} for it in root.iter("item")]
    total = root.findtext("./body/totalCount")
    return items, int(total) if (total or "").strip().isdigit() else len(items)


def parse_json_page(text: str) -> tuple[list[dict], int]:
    """JSON 응답(K-apt 등). 오류가 XML 로 오는 경우도 처리한다."""
    body = (text or "").strip()
    if body.startswith("<"):
        return parse_xml_page(body)
    try:
        doc = json.loads(body)
    except json.JSONDecodeError:
        raise TransientError("JSON 해석 실패") from None
    resp = doc.get("response", doc)
    head = resp.get("header", {})
    code = str(head.get("resultCode", "00")).strip()
    if code in NODATA_CODES:
        return [], 0
    if code not in OK_CODES:
        raise _classify(code, str(head.get("resultMsg", "")))
    b = resp.get("body", {}) or {}
    items = b.get("items", b.get("item", []))
    if isinstance(items, dict):
        items = items.get("item", items)
    if isinstance(items, dict):
        items = [items]
    items = [i for i in (items or []) if isinstance(i, dict)]
    return items, int(b.get("totalCount") or len(items))


class Client:
    """재시도·페이지 처리·호출 수 세기를 맡는 호출기. transport 를 바꿔 끼우면 테스트·샘플에 쓴다."""

    def __init__(self, key: str, cfg: dict | None = None, transport=http_get, sleep=time.sleep,
                 parser=parse_xml_page, key_name: str = "serviceKey"):
        cfg = cfg or {}
        self.key = key
        self.transport = transport
        self.sleep = sleep
        self.parser = parser
        self.key_name = key_name
        self.rows = int(cfg.get("num_of_rows", 1000))
        self.retry_max = int(cfg.get("retry_max", 4))
        self.retry_base = float(cfg.get("retry_base_sec", 1.5))
        self.interval = float(cfg.get("request_interval_sec", 0))
        self.timeout = float(cfg.get("timeout_sec", 30))
        self.calls = 0

    def get_page(self, base: str, params: dict) -> tuple[list[dict], int]:
        url = build_url(base, params, self.key, self.key_name)
        last: ApiError | None = None
        for attempt in range(self.retry_max + 1):
            self.calls += 1
            try:
                status, text = self.transport(url, self.timeout)
                if status in (401, 403):
                    raise AuthError(f"HTTP {status}", str(status))
                if status == 429 or status >= 500:
                    raise TransientError(f"HTTP {status}", str(status))
                page = self.parser(text)
                if self.interval:
                    self.sleep(self.interval)
                return page
            except TransientError as e:
                last = e
                if attempt < self.retry_max:
                    self.sleep(self.retry_base * (2 ** attempt))
        raise last  # type: ignore[misc]

    def fetch_all(self, base: str, params: dict, paged: bool = True) -> list[dict]:
        rows: list[dict] = []
        page = 1
        while True:
            p = {**params, "pageNo": page, "numOfRows": self.rows} if paged else dict(params)
            items, total = self.get_page(base, p)
            rows.extend(items)
            if not paged or not items or len(rows) >= total or page >= 500:
                return rows
            page += 1
