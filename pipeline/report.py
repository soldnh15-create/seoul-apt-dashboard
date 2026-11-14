"""주간 시장 요약. 기본은 규칙 기반(계산된 숫자를 문장 틀에 끼워 넣기)이고,
AI 글(선택)은 숫자 검증을 통과했을 때만 함께 싣는다."""
from __future__ import annotations

import re


def _chg(v) -> str:
    """'2.1% 올랐습니다' 같은 서술어. 0 이면 변동 없음."""
    if not v:
        return "변동이 없었습니다"
    return f"{abs(v)}% {'올랐습니다' if v > 0 else '내렸습니다'}"


def _eok(manwon) -> str:
    if manwon is None:
        return "-"
    e, m = divmod(int(manwon), 10000)
    return (f"{e}억" + (f" {m:,}만" if m else "")) if e else f"{m:,}만"


def facts(doc: dict) -> dict:
    k = doc["kpi"]
    gus = [g for g in doc["gus"] if g.get("chg3m") is not None]
    up = sorted(gus, key=lambda g: g["chg3m"], reverse=True)[:3]
    down = sorted(gus, key=lambda g: g["chg3m"])[:3]
    busy = sorted([g for g in doc["gus"] if (g.get("volchg") or 0) > 0],     # 늘어난 구만(다 줄었으면 칸을 뺀다)
                  key=lambda g: g["volchg"], reverse=True)[:3]
    nh = sorted(doc["newhighs"], key=lambda x: x.get("rise") or 0, reverse=True)[:5]
    return {
        "region": doc["short"], "asof": doc["asof"], "ppy": k["ppy"], "chg3m": k["chg3m"], "yoy": k["yoy"],
        "vol_last": k["vol_last"], "vol_prev": k["vol_prev"],
        "vol_diff": abs((k["vol_last"] or 0) - (k["vol_prev"] or 0)), "jr": k["jr"], "cancel": k["cancel"],
        "direct": k["direct"], "nh30": k["nh30"], "nh7": k["nh7"],
        "up": [{"name": g["name"], "chg3m": g["chg3m"]} for g in up],
        "down": [{"name": g["name"], "chg3m": g["chg3m"]} for g in down],
        "busy": [{"name": g["name"], "volchg": g["volchg"]} for g in busy],
        "newhighs": [{"name": x["name"], "gu": x["gu"], "a": x["a"], "price": x["price"], "rise": x["rise"]}
                     for x in nh],
    }


def render(f: dict) -> list[str]:
    if f["ppy"]:
        # 비교할 과거 자료가 아직 없으면(처음 채우는 중) 비교 문장을 빼고 숫자만 말한다.
        lines = [f"{f['region']} 아파트 중위 평단가는 최근 3개월 기준 3.3㎡당 {f['ppy']:,}만원입니다."]
    else:
        lines = [f"{f['region']} 평단가를 계산할 거래가 부족합니다."]
    # 변동률은 같은 단지·같은 면적끼리 비교한 값의 중간값(어떤 집이 팔렸는지에 따라 출렁이지 않게).
    if f["chg3m"] is not None:
        lines.append(f"같은 단지·같은 면적끼리 비교하면 직전 3개월보다 {_chg(f['chg3m'])}.")
    if f["yoy"] is not None:
        lines.append(f"1년 전 같은 기간보다는 {_chg(f['yoy'])}.")
    if f["vol_last"] is not None:
        d = f["vol_last"] - (f["vol_prev"] or 0)
        lines.append(f"지난달 신고된 매매는 {f['vol_last']:,}건으로 그 전달({f['vol_prev']:,}건)보다 "
                     f"{abs(d):,}건 {'늘었습니다' if d >= 0 else '줄었습니다'}. 신고 기한(계약 후 30일)이 남아 더 늘 수 있습니다.")
    if f["up"]:
        lines.append("많이 오른 구: "+ ", ".join(f"{g['name']}({g['chg3m']:+}%)" for g in f["up"]) + ".")
    if f["down"]:
        lines.append("덜 오르거나 내린 구: "+ ", ".join(f"{g['name']}({g['chg3m']:+}%)" for g in f["down"]) + ".")
    if f["jr"] is not None:
        lines.append(f"전세가율(같은 단지·같은 면적의 전세가 ÷ 매매가, 중간값)은 {f['jr']}%입니다.")
    lines.append(f"최근 30일 신고가 거래는 {f['nh30']:,}건(최근 7일 {f['nh7']:,}건)입니다.")
    for x in f["newhighs"][:3]:
        lines.append(f"· {x['gu']} {x['name']} {x['a']}㎡ {_eok(x['price'])}원 (직전 최고가 대비 {x['rise']:+}%)")
    if f["cancel"] is not None:
        lines.append(f"최근 3개월 해제 거래 비율 {f['cancel']}%, 직거래 비율 {f['direct']}%.")
    return lines


_NUMS = re.compile(r"\d[\d,]*(?:\.\d+)?")


def allowed_numbers(obj, acc: set | None = None) -> set:
    """facts 안의 모든 숫자(절댓값, 쉼표 없는 문자열)."""
    acc = set() if acc is None else acc
    if isinstance(obj, dict):
        for v in obj.values():
            allowed_numbers(v, acc)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            allowed_numbers(v, acc)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        acc.add(f"{abs(obj):g}")
        if isinstance(obj, int) and abs(obj) >= 10000:   # 만원 → 억 표기 허용
            e, m = divmod(abs(obj), 10000)
            acc.update({str(e), str(m)})
            acc.add(f"{abs(obj) / 10000:g}")
    elif isinstance(obj, str):
        acc.update(n.replace(",", "") for n in _NUMS.findall(obj))
    return acc


def verify_numbers(text: str, f: dict) -> list[str]:
    """글 속 숫자 중 facts 에 없는 것(= 지어낸 숫자) 목록. 비어 있으면 통과."""
    ok = allowed_numbers(f) | {"3", "30", "7", "1", "3.3", "12"}   # 기간 표현(3개월·30일·7일·1년·3.3㎡)
    bad = []
    for n in _NUMS.findall(text):
        v = n.replace(",", "")
        try:
            v = f"{float(v):g}"
        except ValueError:
            pass
        if v not in ok:
            bad.append(n)
    return bad


_UNIT = re.compile(r"\s?(?:%|％|퍼센트|억|만|천|건|㎡|제곱미터|평|년|월|일|개|곳|세대|층|위|배|원|주|차|단지|호|동|분기)")


def _strings(obj, acc: list | None = None) -> list[str]:
    acc = [] if acc is None else acc
    if isinstance(obj, dict):
        for v in obj.values():
            _strings(v, acc)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _strings(v, acc)
    elif isinstance(obj, str):
        acc.append(obj)
    return acc


def check_ai(text: str, f: dict) -> list[str]:
    """AI 글을 실어도 되는지 검사한다. 문제 목록(비어 있으면 통과).
    ① 지어낸 숫자 ② 단위 없는 숫자('변동률은 2.7이며'처럼 — 2026-11-14 실제로 이렇게 나와 읽을 수 없었다)."""
    bad = verify_numbers(text, f)
    t = text
    for s in sorted(set(_strings(f)), key=len, reverse=True):   # 단지 이름·날짜 속 숫자는 단위 검사에서 뺀다
        if len(s) >= 2:
            t = t.replace(s, " ")
    for m in _NUMS.finditer(t):
        if not _UNIT.match(t[m.end():m.end() + 6]):
            bad.append(f"{m.group()}(단위 없음)")
    return bad


def build(doc: dict, ai: dict | None = None) -> dict:
    f = facts(doc)
    out = {"asof": doc["asof"], "region": doc["short"], "facts": f, "lines": render(f), "ai": None}
    if ai and ai.get("text") and ai.get("asof") == doc["asof"] and not check_ai(ai["text"], f):
        out["ai"] = {"text": ai["text"], "model": ai.get("model", ""), "generated": ai.get("generated", "")}
    return out
