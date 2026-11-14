"""선택 기능: K-apt 단지정보, 카카오 좌표·입지, 금리·지수, AI 주간 글, 텔레그램 알림.

모두 '키가 환경변수에 있을 때만' 동작하고, 없으면 조용히 건너뛴다(사이트는 그 기능만 숨긴다).
주의: 이 파일의 외부 호출은 공식 문서 기준으로 작성했고 실제 키로는 아직 검증하지 못했다(미검증).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import api, complexes as cx, config, report, store


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


LAST_ERR = ""   # 마지막 _json_call 실패 이유(상태 코드나 오류 종류만 — 주소·키는 담지 않는다)


def _json_call(url: str, headers: dict | None = None, body: dict | None = None, timeout: float = 30):
    """JSON 호출. 실패하면 None (키가 든 주소는 절대 출력하지 않는다). 실패 이유는 LAST_ERR 에 남긴다."""
    global LAST_ERR
    LAST_ERR = ""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    h = {"User-Agent": "apt-dashboard/1.0", **(headers or {})}
    if data:
        h["Content-Type"] = "application/json"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h), timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        LAST_ERR = f"HTTP {e.code}"
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        LAST_ERR = type(e).__name__
    return None


def _deadline(cfg: dict):
    """선택 기능 하나가 한 번 실행에 쓸 시간 상한(분). 넘으면 저장하고 다음 실행에서 이어받는다."""
    minutes = float(cfg.get("extras_minutes_budget", 30) or 0)
    return time.monotonic() + minutes * 60 if minutes > 0 else None


# ── K-apt 단지정보 ───────────────────────────────────
def kapt_spec(basic: dict, detail: dict) -> dict:
    def num(v):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None
    used = str(basic.get("kaptUsedate") or "")
    p = [num(detail.get("kaptdPcnt")), num(detail.get("kaptdPcntu"))]
    out = {
        "hh": num(basic.get("kaptdaCnt")), "dongs": num(basic.get("kaptDongCnt")),
        "used": f"{used[:4]}-{used[4:6]}-{used[6:8]}" if len(used) >= 8 else None,
        "parking": sum(x for x in p if x) or None, "heat": basic.get("codeHeatNm") or None,
        "top": num(basic.get("kaptTopFloor")), "builder": basic.get("kaptBcompany") or None,
        "addr": basic.get("doroJuso") or basic.get("kaptAddr") or None,
    }
    return {k: v for k, v in out.items() if v is not None}


def kapt_update(sample: bool = False, transport=None, log=print, base: Path | None = None,
                regs: list[dict] | None = None) -> int:
    key = api.service_key()
    if sample or (not key and transport is None):
        log("[K-apt] 인증키 없음 — 건너뜀")
        return 0
    cfg = config.settings()
    base = Path(base) if base else config.data_base(False)
    kw = {"transport": transport} if transport else {}
    lst = api.Client(key or "TEST", cfg, parser=api.parse_json_page, **kw)
    inf = api.Client(key or "TEST", cfg, parser=api.parse_json_page, key_name="ServiceKey", **kw)
    budget = int(cfg.get("kapt_call_budget", 4500))
    deadline = _deadline(cfg) if transport is None else None
    kdir = Path(base) / "kapt"
    info = store.read_json(kdir / "info.json")
    specs = store.read_json(kdir / "specs.json")
    ov = config.overrides()
    new = left = 0
    try:
        for reg in regs or config.regions():
            lp = kdir / "list" / f"{reg['sgg']}.json"
            items = store.read_json(lp) if lp.exists() else None    # 받아 둔 목록이 없을 때만 새로 받는다
            if items is None and lst.calls < budget:
                items = lst.fetch_all(cfg["endpoints"]["kapt_list"], {"sigunguCode": reg["sgg"]})
                if items:                                           # 빈 목록은 저장하지 않는다(다음에 다시 받게)
                    store.write_json(lp, items)
                log(f"[K-apt] {reg['name']}: 단지 목록 {len(items):,}개")
            if not items:
                continue
            cxs, _ = cx.assign(store.load(base, "trade", reg["sgg"]), [], ov)
            for cid, code in cx.match_kapt(cxs, items, ov).items():
                if code not in info:
                    if inf.calls >= budget - 2 or (deadline is not None and time.monotonic() > deadline):
                        left += 1
                        continue
                    b, _n = inf.get_page(cfg["endpoints"]["kapt_basic"], {"kaptCode": code})
                    d, _n = inf.get_page(cfg["endpoints"]["kapt_detail"], {"kaptCode": code})
                    info[code] = {"basic": b[0] if b else {}, "detail": d[0] if d else {}}
                    new += 1
                    if new % 200 == 0:
                        log(f"[K-apt]  … 새로 {new:,}개 받음")
                specs[cid] = {"kapt": code, **kapt_spec(info[code]["basic"], info[code]["detail"])}
    except api.QuotaExceeded as e:
        log(f"[K-apt] {e} — 다음 실행에서 이어받음")
    except api.ApiError as e:
        # 선택 기능이 실패해도 매일 갱신은 계속돼야 한다. 이유만 남기고 다음 실행에서 다시 시도한다.
        log(f"[K-apt] 중단 — {e} (다음 실행에서 다시 시도)")
    finally:
        store.write_json(kdir / "info.json", info)
        store.write_json(kdir / "specs.json", specs)
    log(f"[K-apt] 스펙 보유 단지 {len(specs):,} (새로 {new:,} · 남음 {left:,} · 호출 {lst.calls + inf.calls})")
    return len(specs)


# ── 카카오 좌표·입지 ─────────────────────────────────
KAKAO = "https://dapi.kakao.com/v2/local/search"


def geo_update(sample: bool = False, limit: int = 3000, log=print) -> int:
    key = _env("KAKAO_REST_KEY")
    if sample or not key:
        log("[좌표] 카카오 키 없음 — 건너뜀")
        return 0
    base = config.data_base(False)
    geo = store.read_json(Path(base) / "geo" / "geo.json")
    h = {"Authorization": f"KakaoAK {key}"}
    done = fails = left = 0
    deadline = _deadline(config.settings())
    stop = ""
    for reg in config.regions():
        if stop:
            break
        cxs, _ = cx.assign(store.load(base, "trade", reg["sgg"]), [], config.overrides())
        for cid, c in cxs.items():
            if cid in geo:
                continue
            if done >= limit or (deadline is not None and time.monotonic() > deadline):
                left += 1
                continue
            q = urllib.parse.quote(f"{reg['sido_name']} {reg['name']} {c['umd']} {c['jibun']}")
            doc = _json_call(f"{KAKAO}/address.json?query={q}", h)
            if doc is None:
                fails += 1
                if fails >= 5 and done == 0:     # 처음부터 계속 실패 = 키·사용 설정 문제. 더 두드리지 않는다.
                    stop = f"카카오 호출이 계속 실패({LAST_ERR}) — 키와 '카카오맵' 사용 설정을 확인"
                    break
                continue
            docs = doc.get("documents") or []
            if not docs:
                geo[cid] = {}
                continue
            x, y = docs[0]["x"], docs[0]["y"]
            ent = {"lat": round(float(y), 6), "lng": round(float(x), 6)}
            for code, name, need in (("SW8", "subway", ""), ("SC4", "school", "초등학교")):
                near = _json_call(f"{KAKAO}/category.json?category_group_code={code}&x={x}&y={y}"
                                  "&radius=2000&sort=distance", h) or {}
                hit = next((d for d in near.get("documents", []) if need in d.get("place_name", "")), None)
                if hit:
                    ent[name] = {"name": hit["place_name"], "dist": int(hit.get("distance") or 0)}
            geo[cid] = ent
            done += 1
            if done % 500 == 0:
                log(f"[좌표]  … 새로 {done:,}개")
    store.write_json(Path(base) / "geo" / "geo.json", geo)
    if stop:
        log(f"[좌표] 중단 — {stop}")
    log(f"[좌표] 새로 {done:,}개 · 누적 {len(geo):,} · 남음 {left:,} · 실패 {fails:,}")
    return done


# ── 금리·지수 ────────────────────────────────────────
def macro_update(sample: bool = False, log=print) -> dict:
    cfg, base = config.settings(), config.data_base(False)
    out = store.read_json(Path(base) / "macro" / "macro.json")
    ekey, rkey = _env("ECOS_KEY"), _env("RONE_KEY")
    if sample or not (ekey or rkey):
        log("[거시] ECOS·R-ONE 키 없음 — 건너뜀")
        return {}
    end = dt.date.today()
    if ekey:
        for name, s in (cfg.get("ecos") or {}).items():
            url = (f"https://ecos.bok.or.kr/api/StatisticSearch/{urllib.parse.quote(ekey)}/json/kr/1/1000/"
                   f"{s['stat']}/{s['cycle']}/{end.year - 12}01/{end.year}{end.month:02d}/{s['item']}")
            doc = _json_call(url) or {}
            rows = (doc.get("StatisticSearch") or {}).get("row") or []
            if not rows:     # 키·통계코드 문제를 기록에서 알아볼 수 있게(ECOS 는 오류도 200 으로 준다)
                err = (doc.get("RESULT") or {}).get("MESSAGE") or LAST_ERR or "빈 응답"
                log(f"[거시] {name}: 받지 못함 — {err}")
            if rows:
                out[name] = {"t": [f"{r['TIME'][:4]}-{r['TIME'][4:6]}" for r in rows],
                             "v": [float(r["DATA_VALUE"]) for r in rows]}
    if rkey:
        rc = cfg.get("rone") or {}
        for name in ("weekly_sale_index", "weekly_jeonse_index"):
            s = rc.get(name) or {}
            if not s.get("statbl_id"):
                continue
            p = {"KEY": rkey, "Type": "json", "pIndex": 1, "pSize": 1000, "STATBL_ID": s["statbl_id"],
                 "DTACYCLE_CD": s.get("cycle", "WK")}
            p.update({k.upper(): v for k, v in s.items() if k in ("itm_id", "cls_id") and v})
            doc = _json_call(f"{rc['url']}?{urllib.parse.urlencode(p)}") or {}
            rows = next((b["row"] for b in doc.get("SttsApiTblData", []) if "row" in b), [])
            if rows:
                out[name] = {"t": [str(r.get("WRTTIME_IDTFR_ID")) for r in rows],
                             "v": [float(r["DTA_VAL"]) for r in rows]}
    if out:
        store.write_json(Path(base) / "macro" / "macro.json", out)
    log(f"[거시] 계열 {len(out)}개")
    return out


# ── AI 주간 글(Gemini) ───────────────────────────────
PROMPT = """너는 부동산 통계 요약 작성자다. 아래 JSON 의 숫자만 사용해 {region} 아파트 시장 주간 요약을 한국어 5~7문장으로 써라.
규칙: JSON 에 없는 숫자는 절대 쓰지 않는다(개수·순위·합계·반올림한 값도 새로 만들지 않는다). 전망·예측·매수/매도 권유·수익 보장 표현을 쓰지 않는다. 사실만 담담하게 쓴다.
JSON:
{facts}"""


def ai_report(sample: bool = False, force: bool = False, log=print) -> int:
    key = _env("GEMINI_API_KEY")
    if sample or not key:
        log("[AI 글] Gemini 키 없음 — 규칙 기반 요약만 사용")
        return 0
    base, out = config.data_base(False), config.SITE / "data"
    gcfg = config.settings().get("gemini") or {}
    models = gcfg.get("models") or [gcfg.get("model", "gemini-2.5-flash")]
    made = 0
    for p in sorted((out / "report").glob("*.json")):
        rep = store.read_json(p)
        saved = Path(base) / "report" / f"ai_{p.stem}.json"
        old = store.read_json(saved)
        if not force and old.get("asof") == rep["asof"] and old.get("text"):
            continue   # 같은 기준일 글이 이미 있으면 다시 만들지 않는다(하루 1회 — 무료 한도 안)
        prompt = PROMPT.format(region=rep["region"], facts=json.dumps(rep["facts"], ensure_ascii=False))
        text, model = "", models[0]
        for model in models:           # 모델 이름이 바뀌어 없어졌으면 다음 후보로
            for _ in range(2):
                doc = _json_call(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                                 {"x-goog-api-key": key}, {"contents": [{"parts": [{"text": prompt}]}]}, 60)
                if doc is None:
                    log(f"[AI 글] {model} 호출 실패({LAST_ERR})")
                    break
                try:
                    text = doc["candidates"][0]["content"]["parts"][0]["text"].strip()
                except (KeyError, IndexError, TypeError):
                    text = ""
                bad = report.verify_numbers(text, rep["facts"]) if text else ["응답 없음"]
                if not bad:
                    break
                log(f"[AI 글] 숫자 검증 실패({len(bad)}건: {', '.join(bad[:5])}) — 다시 시도")
                text = ""
            if text:
                break
        if not text:
            continue   # 검증을 통과하지 못한 글은 싣지 않는다
        ai = {"asof": rep["asof"], "text": text, "model": model, "generated": dt.date.today().isoformat()}
        store.write_json(saved, ai)
        rep["ai"] = {k: ai[k] for k in ("text", "model", "generated")}
        store.write_json(p, rep, compact=True)
        made += 1
    log(f"[AI 글] {made}건 생성")
    return made


# ── 텔레그램 알림 ────────────────────────────────────
def _eok(v: int) -> str:
    e, m = divmod(int(v), 10000)
    return (f"{e}억" + (f" {m:,}" if m else "")) if e else f"{m:,}만"


def digest(doc: dict, sent: set, weekly_lines: list[str] | None = None, site_url: str = "") -> tuple[str, list[str]]:
    """아직 안 보낸 신고가·저가 직거래로 알림 글을 만든다. (글, 이번에 보낸 키)"""
    key = lambda x: f"{x['id']}|{x['date']}|{x['price']}|{x['floor']}"  # noqa: E731
    nh = [x for x in doc["newhighs"] if key(x) not in sent]
    an = [x for x in doc["anoms"] if "a:" + key(x) not in sent]
    if not nh and not an and not weekly_lines:
        return "", []
    lines = [f"📊 {doc['short']} 아파트 실거래 ({doc['asof']} 기준)"]
    if weekly_lines:
        lines += ["", "■ 주간 요약"] + weekly_lines[:6]
    if nh:
        lines += ["", f"■ 새로 신고된 신고가 {len(nh)}건"]
        for x in sorted(nh, key=lambda x: x.get("rise") or 0, reverse=True)[:15]:
            lines.append(f"· {x['gu']} {x['name']} {x['a']}㎡ {x['floor']}층 {_eok(x['price'])} ({x['rise']:+}%)")
    if an:
        lines += ["", f"■ 시세보다 낮은 직거래 {len(an)}건(참고)"]
        for x in an[:5]:
            lines.append(f"· {x['gu']} {x['name']} {x['a']}㎡ {_eok(x['price'])} ({x['disc']:+}%)")
    lines += ["", "투자 권유가 아닙니다. 자료: 국토교통부 실거래가"] + ([site_url] if site_url else [])
    return "\n".join(lines), [key(x) for x in nh] + ["a:" + key(x) for x in an]


def notify(sample: bool = False, weekly: bool = False, log=print) -> int:
    token, chat = _env("TELEGRAM_BOT_TOKEN"), _env("TELEGRAM_CHAT_ID")
    if sample or not (token and chat):
        log("[알림] 텔레그램 설정 없음 — 건너뜀")
        return 0
    base, out = config.data_base(False), config.SITE / "data"
    state = Path(base) / "state" / "notified.json"
    sent = set(store.read_json(state, default=[]))
    n = 0
    for p in sorted((out / "sido").glob("*.json")):
        doc = store.read_json(p)
        wl = store.read_json(out / "report" / p.name).get("lines") if weekly else None
        text, keys = digest(doc, sent, wl, _env("SITE_URL"))
        if not text:
            continue
        res = _json_call(f"https://api.telegram.org/bot{token}/sendMessage", None,
                         {"chat_id": chat, "text": text[:4000], "disable_web_page_preview": True})
        if res and res.get("ok"):
            sent.update(keys)
            n += 1
    store.write_json(state, sorted(sent)[-20000:])
    log(f"[알림] {n}건 발송")
    return n
