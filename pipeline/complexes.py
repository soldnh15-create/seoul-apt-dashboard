"""단지 식별: 매매(단지 일련번호 aptSeq)를 기준으로 안정적인 단지 ID를 만들고 전월세·K-apt 를 붙인다."""
from __future__ import annotations

import difflib
import hashlib
import re


def norm_name(s: str) -> str:
    s = re.sub(r"\(.*?\)", "", s or "")
    s = re.sub(r"[\s·\-.,]", "", s)
    return s.replace("아파트", "").lower()


def safe_id(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", s)


def _hid(*parts: str) -> str:
    return "x" + hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:10]


def rent_key(r: dict) -> str:
    return f"{r['sgg']}|{r['umd']}|{r['jibun']}|{r['apt']}"


def assign(trades: list[dict], rents: list[dict], ov: dict | None = None) -> tuple[dict, list[str]]:
    """각 행에 cid(단지 ID)를 붙인다. (단지 사전, 매매 단지에 못 붙인 전월세 키 목록)"""
    ov = ov or {}
    complexes: dict[str, dict] = {}
    k4: dict[tuple, str] = {}
    k3: dict[tuple, set] = {}
    kn: dict[tuple, set] = {}
    for t in trades:  # 날짜순 — 마지막(최근) 이름이 남는다
        nn = norm_name(t["apt"])
        cid = safe_id(t["apt_seq"]) if t.get("apt_seq") else _hid(t["sgg"], t["umd"], t["jibun"], nn)
        t["cid"] = cid
        c = complexes.setdefault(cid, {"id": cid, "sgg": t["sgg"], "trades": 0})
        c.update(name=t["apt"], umd=t["umd"], umd_cd=t.get("umd_cd", ""), jibun=t["jibun"])
        if t.get("by"):
            c["by"] = t["by"]
        c["trades"] += 1
        k4[(t["umd"], t["jibun"], nn)] = cid
        k3.setdefault((t["umd"], t["jibun"]), set()).add(cid)
        kn.setdefault((t["umd"], nn), set()).add(cid)
    unmatched: dict[str, None] = {}
    manual = ov.get("rent_to_complex", {})
    for r in rents:
        nn = norm_name(r["apt"])
        key = rent_key(r)
        cid = manual.get(key)
        if not cid and r.get("apt_seq") and safe_id(r["apt_seq"]) in complexes:
            cid = safe_id(r["apt_seq"])
        if not cid:
            cid = k4.get((r["umd"], r["jibun"], nn))
        if not cid:
            s = k3.get((r["umd"], r["jibun"]), ())
            cid = next(iter(s)) if len(s) == 1 else None
        if not cid:
            s = kn.get((r["umd"], nn), ())
            cid = next(iter(s)) if len(s) == 1 else None
        if not cid:
            cid = _hid(r["sgg"], r["umd"], r["jibun"], nn)
            unmatched[key] = None
            c = complexes.setdefault(cid, {"id": cid, "sgg": r["sgg"], "trades": 0})
            c.update(name=r["apt"], umd=r["umd"], umd_cd="", jibun=r["jibun"])
            if r.get("by"):
                c["by"] = r["by"]
        r["cid"] = cid
    for c in complexes.values():
        # 신고된 이름이 비었거나 '(50-5)'처럼 지번뿐이면 검색·목록에서 알아볼 수 있게 동 이름을 앞에 붙인다.
        if not norm_name(c.get("name", "")):
            c["name"] = f"{c.get('umd', '')} {c.get('name') or c.get('jibun', '')}".strip()
    for cid, name in (ov.get("rename") or {}).items():
        if cid in complexes:
            complexes[cid]["name"] = name
    return complexes, list(unmatched)


def _canon(s: str) -> str:
    """견주기 좋게 다듬은 이름: 괄호·띄어쓰기·'아파트' 제거 + 'N단지'·'N차'·'제N' → 'N'."""
    s = re.sub(r"\((\d+)(?:단지|차)\)", r"\1", s or "")      # '텐즈힐(1단지)' → '텐즈힐1'
    s = norm_name(s)
    if s.endswith("apt") and len(s) > 5:                    # '중앙하이츠 A.P.T'
        s = s[:-3]
    for ko, en in (("에스케이", "sk"), ("이편한세상", "e편한세상"), ("엘지", "lg"), ("지에스", "gs")):
        s = s.replace(ko, en)
    return re.sub(r"제?(\d+)(?:단지|차)?", r"\1", s)


def _variants(name: str, dong: str) -> list[str]:
    """이름 후보: 다듬은 이름 + 앞에 붙은 동 이름을 뗀 이름('중계주공4단지' → '주공4', '역삼동월드메르디앙' → '월드메르디앙')."""
    kn = _canon(name)
    d = norm_name(dong)
    d2 = re.sub(r"\d+가$", "", d)                           # '성수동1가' → '성수동'
    out = [kn]
    for pre in (d, d2, d2[:-1] if d2.endswith("동") else ""):
        if len(pre) >= 2 and kn.startswith(pre) and len(kn) - len(pre) >= 2:
            out.append(kn[len(pre):])
            break
    return out


def _name_score(nn: str, kn: str) -> float:
    """우리 단지 이름(nn)과 K-apt 단지 이름(kn)이 같은 단지로 보이는 정도(0~1). 둘 다 _canon 을 거친 값."""
    if nn == kn:
        return 1.0
    a, b = re.findall(r"\d+", nn), re.findall(r"\d+", kn)
    # '8단지'와 '9단지', '1차'와 '2차'는 다른 단지다. K-apt 쪽에만 숫자가 있으면 어느 단지인지 알 수 없어 붙이지 않는다.
    # (우리 쪽에만 숫자가 있는 경우는 K-apt 가 1~5단지를 한 단지로 올린 것이라 허용한다.)
    if b and a != b:
        return 0.0
    short, long_ = sorted((len(nn), len(kn)))
    if short >= 2 and (kn.endswith(nn) or nn.endswith(kn)):  # 한쪽 앞에 지역·건설사 이름이 더 붙은 것('우면코오롱' ↔ '코오롱')
        return 0.93 if short >= 3 else 0.88
    if short >= 3 and short * 2 >= long_ and (nn in kn or kn in nn):   # '래미안' ⊂ '래미안퍼스티지' 같은 짧은 겹침은 제외
        return 0.86
    if short >= 4 and a == b:
        return difflib.SequenceMatcher(None, nn, kn).ratio()
    return 0.0


def match_kapt(complexes: dict, kapt_items: list[dict], ov: dict | None = None) -> dict[str, str]:
    """단지 ID → K-apt 단지코드. 같은 법정동 안에서 이름이 같거나 충분히 비슷하고, 그런 후보가 하나뿐일 때만 붙인다.
    이름이 없는 단지('구로동 (749-96)'처럼 동 이름 + 지번)는 붙이지 않는다
    (2026-11-14 실제 자료: '구로동' 221곳이 '구로극동' 한 단지에 잘못 붙었다).
    이름만으로는 틀릴 수 있어, 정보를 받은 뒤 준공연도가 다르면 버린다(extras.kapt_update)."""
    manual = (ov or {}).get("kapt", {})
    by_bjd: dict[str, list] = {}
    by_dong: dict[tuple, list] = {}
    for k in kapt_items:
        code, name = k.get("kaptCode"), k.get("kaptName") or ""
        if not code or "임대" in name:      # 임대 단지는 매매 신고가 거의 없고, 같은 이름의 분양 단지와 헷갈린다
            continue
        ent = (_variants(name, k.get("as3") or ""), code)
        bjd = str(k.get("bjdCode") or "")
        if bjd:
            by_bjd.setdefault(bjd, []).append(ent)
        by_dong.setdefault((bjd[:5], (k.get("as3") or "").strip()), []).append(ent)
    out: dict[str, str] = {}
    for cid, c in complexes.items():
        if cid in manual:
            out[cid] = manual[cid]
            continue
        cands = by_bjd.get(f"{c['sgg']}{c.get('umd_cd', '')}") if c.get("umd_cd") else None
        cands = cands or by_dong.get((c["sgg"], c.get("umd", "")), [])
        if not cands or not norm_name(c.get("name", "")) or norm_name(c.get("name", "")) == norm_name(c.get("umd", "")):
            continue
        mine = _variants(c.get("name", ""), c.get("umd", ""))
        scores: dict[str, float] = {}
        for names, code in cands:
            s = max(_name_score(nn, kn_) for nn in mine for kn_ in names)
            if s > scores.get(code, 0.0):
                scores[code] = s
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        if ranked and ranked[0][1] >= 0.85 and (len(ranked) == 1 or ranked[1][1] < ranked[0][1]):   # 똑같이 비슷한 후보가 둘이면 붙이지 않는다
            out[cid] = ranked[0][0]
    return out
