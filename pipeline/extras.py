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
from concurrent.futures import ThreadPoolExecutor
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
        "hh": num(basic.get("kaptdaCnt")) or None, "dongs": num(basic.get("kaptDongCnt")) or None,
        "used": f"{used[:4]}-{used[4:6]}-{used[6:8]}" if len(used) >= 8 else None,
        "parking": sum(x for x in p if x) or None, "heat": basic.get("codeHeatNm") or None,
        "top": num(basic.get("kaptTopFloor")), "builder": basic.get("kaptBcompany") or None,
        "addr": basic.get("doroJuso") or basic.get("kaptAddr") or None,
    }
    return {k: v for k, v in out.items() if v is not None}


KAPT_TRIES = 6        # 빈 응답만 오는 단지는 이 횟수(실행 단위)까지 다시 받아 보고 그만둔다
KAPT_BLANK_STOP = 40  # 이만큼 연달아 빈 응답이면 그 실행에서는 더 부르지 않는다(서비스가 잠깐 이상한 때 호출만 쓰지 않게)


def _kapt_shape(text: str) -> str:
    """빈 응답이 어떤 모양이었는지(원인 추적용). 응답 속 값은 담지 않고 결과 코드와 칸 이름만 남긴다."""
    try:
        doc = json.loads(text or "")
    except ValueError:
        return f"JSON 아님({len(text or '')}자)"
    resp = doc.get("response", doc) if isinstance(doc, dict) else {}
    head = (resp.get("header") or {}) if isinstance(resp, dict) else {}
    body = resp.get("body") if isinstance(resp, dict) else None
    if isinstance(body, dict):
        b = "{" + ",".join(f"{k}:{type(v).__name__}" + (f"[{len(v)}]" if isinstance(v, (dict, list, str)) else "")
                           for k, v in sorted(body.items())) + "}"
    else:
        b = type(body).__name__
    return f"resultCode={head.get('resultCode')} resultMsg={str(head.get('resultMsg'))[:40]} body={b}"


def kapt_update(sample: bool = False, transport=None, log=print, base: Path | None = None,
                regs: list[dict] | None = None) -> int:
    key = api.service_key()
    if sample or (not key and transport is None):
        log("[K-apt] 인증키 없음 — 건너뜀")
        return 0
    cfg = config.settings()
    base = Path(base) if base else config.data_base(False)
    kw = {"transport": transport} if transport else {}
    blanks: dict[str, int] = {}                # 빈 응답 모양 → 횟수

    def parse_info(text: str):
        """기본·상세 정보 응답. 정상 코드인데 내용이 빈 응답(실제로 자주 온다)은 '없음'으로 돌려주고 모양을 적어 둔다."""
        items, n = api.parse_json_page(text)
        if not items or not any(v not in (None, "") for k, v in items[0].items() if k != "kaptCode"):
            shape = _kapt_shape(text)
            blanks[shape] = blanks.get(shape, 0) + 1
            return [], n
        return items, n

    lst = api.Client(key or "TEST", cfg, parser=api.parse_json_page, **kw)
    inf = api.Client(key or "TEST", cfg, parser=parse_info, key_name="ServiceKey", **kw)
    budget = int(cfg.get("kapt_call_budget", 4500))
    deadline = _deadline(cfg) if transport is None else None
    # 한 줄로만 받는다. 실측(2026-11-14): 4줄로 동시에 부르니 5곳 중 4곳이 빈 응답으로 왔다(한 줄일 때는 거의 다 채워짐).
    workers = max(1, int(cfg.get("kapt_workers", 1))) if transport is None else 1
    pause = 2.0 if transport is None else 0    # 빈 응답 뒤 한 번 더 부르기 전 쉬는 시간(초)
    kdir = Path(base) / "kapt"
    info = store.read_json(kdir / "info.json")
    specs = store.read_json(kdir / "specs.json")
    ov = config.overrides()
    pairs: list[tuple[str, str]] = []          # (단지 ID, K-apt 단지코드)
    seen: set[str] = set()                     # 이번에 목록과 맞춰 본 우리 단지(예전에 잘못 붙은 것을 지우려고)
    built: dict[str, object] = {}              # 우리 단지 ID → 준공연도(실거래 신고 기준)
    names: dict[str, str] = {}                 # 우리 단지 ID → 다듬은 이름
    knames: dict[str, str] = {}                # K-apt 단지코드 → 다듬은 이름
    manual = (ov or {}).get("kapt", {})
    wrong_year = 0
    new = left = 0
    blank_run = [0]                            # 연달아 빈 응답만 온 단지 수
    stop: list[str] = []                       # 중단 이유(있으면 더 부르지 않는다)
    try:
        # 1) 구별 단지 목록(받아 둔 것이 없을 때만 새로 받는다)과 우리 단지 맞추기
        for reg in regs or config.regions():
            lp = kdir / "list" / f"{reg['sgg']}.json"
            items = store.read_json(lp) if lp.exists() else None
            if items is None and lst.calls < budget:
                items = lst.fetch_all(cfg["endpoints"]["kapt_list"], {"sigunguCode": reg["sgg"]})
                if items:                                           # 빈 목록은 저장하지 않는다(다음에 다시 받게)
                    store.write_json(lp, items)
                log(f"[K-apt] {reg['name']}: 단지 목록 {len(items):,}개")
            if not items:
                continue
            cxs, _ = cx.assign(store.load(base, "trade", reg["sgg"]), [], ov)
            seen.update(cxs)
            built.update({cid: c.get("by") for cid, c in cxs.items()})
            names.update({cid: cx._canon(c.get("name", "")) for cid, c in cxs.items()})
            knames.update({k.get("kaptCode"): cx._canon(k.get("kaptName") or "") for k in items})
            pairs.extend(cx.match_kapt(cxs, items, ov).items())

        # 2) 아직 없거나 비어 있는 단지의 기본·상세 정보를 받는다(한 건에 1.5초쯤 — 시간 상한까지 받고 다음 실행에서 이어받는다)
        def fetch(code: str):
            old = info.get(code) or {}
            got = {"basic": old.get("basic") or {}, "detail": old.get("detail") or {}}
            if stop or inf.calls >= budget - 4 or (deadline is not None and time.monotonic() > deadline):
                return code, None
            try:
                for part, ep in (("basic", "kapt_basic"), ("detail", "kapt_detail")):
                    for attempt in range(2):                      # 빈 응답이면 잠깐 쉬고 한 번 더
                        if got[part]:
                            break
                        if attempt and pause:
                            time.sleep(pause)
                        rows, _n = inf.get_page(cfg["endpoints"][ep], {"kaptCode": code})
                        got[part] = rows[0] if rows else {}
            except api.QuotaExceeded as e:
                stop.append(f"{e} — 다음 실행에서 이어받음")
                return code, None
            except api.ApiError as e:
                stop.append(f"중단 — {e} (다음 실행에서 다시 시도)")
                return code, None
            if not (got["basic"] and got["detail"]):
                got["tries"] = int(old.get("tries", 0)) + 1       # 다음 실행에서 다시 받는다(KAPT_TRIES 번까지)
            blank_run[0] = 0 if (got["basic"] or got["detail"]) else blank_run[0] + 1
            if blank_run[0] >= KAPT_BLANK_STOP and not stop:
                stop.append(f"빈 응답이 {KAPT_BLANK_STOP}곳 연달아 옴 — 다음 실행에서 다시 시도")
            return code, got

        def need(code: str) -> bool:
            e = info.get(code)
            return e is None or (not (e.get("basic") and e.get("detail")) and int(e.get("tries", 0)) < KAPT_TRIES)

        todo = [code for code in dict.fromkeys(code for _cid, code in pairs) if need(code)]
        with ThreadPoolExecutor(workers) as pool:
            for code, got in pool.map(fetch, todo):
                if got is None:
                    left += 1
                    continue
                info[code] = got
                if got["basic"] and got["detail"]:
                    new += 1
                    if new % 200 == 0:
                        log(f"[K-apt]  … 새로 {new:,}개 받음")
                else:
                    left += 1
    except api.QuotaExceeded as e:
        stop.append(f"{e} — 다음 실행에서 이어받음")
    except api.ApiError as e:
        # 선택 기능이 실패해도 매일 갱신은 계속돼야 한다. 이유만 남기고 다음 실행에서 다시 시도한다.
        stop.append(f"중단 — {e} (다음 실행에서 다시 시도)")
    finally:
        specs = {cid: s for cid, s in specs.items() if cid not in seen}     # 이번에 맞춰 본 단지는 새 결과로 바꾼다
        share: dict[str, int] = {}
        for _cid, code in pairs:
            share[code] = share.get(code, 0) + 1
        for cid, code in pairs:
            e = info.get(code)
            if e and (e.get("basic") or e.get("detail")):
                # 이름만으로 붙인 것이 맞는지 준공연도로 한 번 더 본다(이름이 똑같으면 3년, 아니면 1년까지 차이 허용).
                ky = str((e.get("basic") or {}).get("kaptUsedate") or "")[:4]
                by = str(built.get(cid) or "")
                if cid not in manual and ky.isdigit() and by.isdigit() and \
                        abs(int(ky) - int(by)) > (3 if names.get(cid) == knames.get(code) else 1):
                    wrong_year += 1
                    continue
                specs[cid] = {"kapt": code, **kapt_spec(e.get("basic") or {}, e.get("detail") or {})}
                if share[code] > 1:        # K-apt 한 단지에 우리 단지 여럿(1~5단지를 한 단지로 올린 경우 등) — 세대수는 합친 값
                    specs[cid]["shared"] = share[code]
        store.write_json(kdir / "info.json", info)
        store.write_json(kdir / "specs.json", specs)
    if stop:
        log(f"[K-apt] {stop[0]}")
    for shape, n in sorted(blanks.items(), key=lambda kv: -kv[1])[:3]:
        log(f"[K-apt] 빈 응답 {n:,}번: {shape}")
    filled = sum(1 for s in specs.values() if s.get("hh"))
    log(f"[K-apt] 세대수 있는 단지 {filled:,} / 이름으로 맞춘 단지 {len(pairs):,} (새로 {new:,} · 남음 {left:,} · "
        f"준공연도가 달라 뺀 곳 {wrong_year:,} · 호출 {lst.calls + inf.calls})")
    return len(specs)


# ── 카카오 좌표·입지 ─────────────────────────────────
KAKAO = "https://dapi.kakao.com/v2/local/search"


def geo_update(sample: bool = False, limit: int = 12000, log=print) -> int:
    key = _env("KAKAO_REST_KEY")
    if sample or not key:
        log("[좌표] 카카오 키 없음 — 건너뜀")
        return 0
    base = config.data_base(False)
    geo = store.read_json(Path(base) / "geo" / "geo.json")
    h = {"Authorization": f"KakaoAK {key}"}
    cfg = config.settings()
    deadline = _deadline(cfg)
    workers = max(1, int(cfg.get("extras_workers", 4)))
    todo = []                                   # (단지 ID, 주소 검색어)
    for reg in config.regions():
        cxs, _ = cx.assign(store.load(base, "trade", reg["sgg"]), [], config.overrides())
        todo += [(cid, f"{reg['sido_name']} {reg['name']} {c['umd']} {c['jibun']}") for cid, c in cxs.items() if cid not in geo]
    left = max(0, len(todo) - limit)
    todo = todo[:limit]

    def one(item):
        """(단지 ID, 결과). 결과: 좌표 사전 / {}(주소를 못 찾음) / None(호출 실패·시간 초과 — 다음에 다시)."""
        cid, addr = item
        if deadline is not None and time.monotonic() > deadline:
            return cid, None, "시간"
        doc = _json_call(f"{KAKAO}/address.json?query={urllib.parse.quote(addr)}", h)
        if doc is None:
            return cid, None, LAST_ERR or "실패"
        docs = doc.get("documents") or []
        if not docs:
            return cid, {}, ""
        x, y = docs[0]["x"], docs[0]["y"]
        ent = {"lat": round(float(y), 6), "lng": round(float(x), 6)}
        for code, name, need in (("SW8", "subway", ""), ("SC4", "school", "초등학교")):
            near = _json_call(f"{KAKAO}/category.json?category_group_code={code}&x={x}&y={y}"
                              "&radius=2000&sort=distance", h) or {}
            hit = next((d for d in near.get("documents", []) if need in d.get("place_name", "")), None)
            if hit:
                ent[name] = {"name": hit["place_name"], "dist": int(hit.get("distance") or 0)}
        return cid, ent, ""

    done = fails = 0
    stop = ""
    # 처음 몇 건은 한 줄로 두드려 본다. 처음부터 계속 실패하면 키·사용 설정 문제이므로 더 부르지 않는다.
    probe, rest = todo[:5], todo[5:]
    results = [one(it) for it in probe]
    if probe and all(r[1] is None for r in results):
        stop = f"카카오 호출이 계속 실패({results[0][2]}) — 키와 '카카오맵' 사용 설정을 확인"
        left += len(rest)
        rest = []
    with ThreadPoolExecutor(workers) as pool:
        for cid, ent, why in list(results) + list(pool.map(one, rest)):
            if ent is None:
                if why == "시간":
                    left += 1
                else:
                    fails += 1
                continue
            geo[cid] = ent
            if ent:
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
PROMPT = """너는 부동산 통계 요약 작성자다. 아래 '사실'만 가지고 {region} 아파트 시장 주간 요약을 한국어 5~7문장으로 써라.
규칙:
- 숫자는 '사실'에 적힌 것만 쓰고, 적힌 단위(%, 만원, 억, 건, ㎡)를 숫자 바로 뒤에 그대로 붙인다. 단위 없는 숫자는 쓰지 않는다.
- 새 숫자(개수·순위·합계·반올림한 값)를 만들지 않는다.
- '~습니다' 체로, 부동산을 처음 보는 사람도 읽기 쉽게 쓴다. 목록·기호·굵은 글씨 없이 문장으로만 쓴다.
- 전망·예측·매수/매도 권유·수익 보장 표현을 쓰지 않는다. 사실만 담담하게 쓴다.
사실:
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
        if (not force and old.get("asof") == rep["asof"] and old.get("text")
                and not report.check_ai(old["text"], rep["facts"])):
            continue   # 같은 기준일의 (검사를 통과하는) 글이 이미 있으면 다시 만들지 않는다(하루 1회 — 무료 한도 안)
        # 단위가 붙은 문장을 재료로 준다(숫자만 든 JSON 을 주면 '변동률은 2.7이며'처럼 단위 없는 글이 나온다).
        prompt = PROMPT.format(region=rep["region"], facts="\n".join(rep["lines"]))
        text, model = "", models[0]
        for model in models:           # 모델 이름이 바뀌어 없어졌으면 다음 후보로
            for _ in range(2):
                doc = _json_call(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                                 {"x-goog-api-key": key}, {"contents": [{"parts": [{"text": prompt}]}]}, 150)
                if doc is None:
                    log(f"[AI 글] {model} 호출 실패({LAST_ERR})")
                    break
                try:
                    text = doc["candidates"][0]["content"]["parts"][0]["text"].replace("*", "").strip()
                except (KeyError, IndexError, TypeError, AttributeError):
                    text = ""
                bad = report.check_ai(text, rep["facts"]) if text else ["응답 없음"]
                if not bad:
                    break
                log(f"[AI 글] 검사 실패({len(bad)}건: {', '.join(bad[:5])}) — 다시 시도")
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
