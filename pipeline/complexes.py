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
    for cid, name in (ov.get("rename") or {}).items():
        if cid in complexes:
            complexes[cid]["name"] = name
    return complexes, list(unmatched)


def match_kapt(complexes: dict, kapt_items: list[dict], ov: dict | None = None) -> dict[str, str]:
    """단지 ID → K-apt 단지코드. 같은 법정동 안에서 이름이 같거나 충분히 비슷한 것만 붙인다."""
    manual = (ov or {}).get("kapt", {})
    by_bjd: dict[str, list] = {}
    by_dong: dict[tuple, list] = {}
    for k in kapt_items:
        code, name = k.get("kaptCode"), k.get("kaptName") or ""
        if not code:
            continue
        ent = (norm_name(name), code)
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
        nn = norm_name(c.get("name", ""))
        if not nn or not cands:
            continue
        best, score = None, 0.0
        for kn_, code in cands:
            s = 1.0 if kn_ == nn else (0.9 if (nn in kn_ or kn_ in nn) and min(len(nn), len(kn_)) >= 3
                                       else difflib.SequenceMatcher(None, nn, kn_).ratio())
            if s > score:
                best, score = code, s
        if best and score >= 0.8:
            out[cid] = best
    return out
