"""지표 계산. 금액 단위는 만원, 평단가는 3.3058㎡(1평)당 만원."""
from __future__ import annotations

import datetime as dt
import statistics
from collections import Counter, defaultdict

PY = 3.3058


def med(xs):
    return statistics.median(xs) if xs else None


def pct(new, old, nd: int = 1):
    if new is None or old in (None, 0):
        return None
    return round((new - old) / old * 100, nd)


def rint(x):
    return None if x is None else int(round(x))


def ym_add(ym: str, k: int) -> str:
    """'2024-01' + k개월"""
    n = int(ym[:4]) * 12 + int(ym[5:7]) - 1 + k
    return f"{n // 12:04d}-{n % 12 + 1:02d}"


def ym_range(end: str, count: int) -> list[str]:
    return [ym_add(end, -i) for i in range(count - 1, -1, -1)]


def band_of(area: float, bands: list[dict]) -> str:
    for b in bands:
        if b.get("min", 0) < area <= b.get("max", 1e9):
            return b["key"]
    return bands[-1]["key"]


def age_label(age: int, edges: list[int]) -> str:
    lo = 0
    for e in edges:
        if age <= e:
            return f"{lo + 1 if lo else 0}~{e}년"
        lo = e
    return f"{lo}년 초과"


class SeriesAcc:
    """월별 집계 누적기(지역 단위). 구 → 시도로 merge 해서 쓴다."""

    def __init__(self, band_keys: list[str]):
        self.bk = band_keys
        self.m: dict[str, dict] = {}

    def _slot(self, ym: str) -> dict:
        s = self.m.get(ym)
        if s is None:
            s = self.m[ym] = {"p": [], "ppm": [], "all": 0, "cancel": 0, "direct": 0, "jn": 0, "wn": 0,
                              "jppm": [], "b": {k: {"p": [], "ppm": []} for k in self.bk}}
        return s

    def add_trade(self, t: dict, band: str) -> None:
        s = self._slot(t["date"][:7])
        s["all"] += 1
        if t["cancel"]:
            s["cancel"] += 1
            return
        if t["direct"]:
            s["direct"] += 1
        ppm = t["price"] / t["area"]
        s["p"].append(t["price"])
        s["ppm"].append(ppm)
        s["b"][band]["p"].append(t["price"])
        s["b"][band]["ppm"].append(ppm)

    def add_rent(self, r: dict) -> None:
        s = self._slot(r["date"][:7])
        if r["monthly"]:
            s["wn"] += 1
        else:
            s["jn"] += 1
            s["jppm"].append(r["deposit"] / r["area"])

    def merge(self, o: "SeriesAcc") -> None:
        for ym, src in o.m.items():
            s = self._slot(ym)
            for k in ("p", "ppm", "jppm"):
                s[k].extend(src[k])
            for k in ("all", "cancel", "direct", "jn", "wn"):
                s[k] += src[k]
            for b in self.bk:
                s["b"][b]["p"].extend(src["b"][b]["p"])
                s["b"][b]["ppm"].extend(src["b"][b]["ppm"])

    def window(self, months: list[str], field: str, band: str | None = None) -> list:
        out: list = []
        for ym in months:
            s = self.m.get(ym)
            if s:
                out.extend(s["b"][band][field] if band else s[field])
        return out

    def count(self, months: list[str], key: str) -> int:
        return sum(len(self.m[ym]["p"]) if key == "n" else self.m[ym][key] for ym in months if ym in self.m)

    def to_json(self, last: int | None = None, bands: bool = True) -> dict:
        ms = sorted(self.m)
        if last:
            ms = ms[-last:]
        ppy = lambda xs: rint(med(xs) * PY) if xs else None  # noqa: E731
        out = {
            "m": ms,
            "n": [len(self.m[x]["p"]) for x in ms],
            "med": [rint(med(self.m[x]["p"])) for x in ms],
            "avg": [rint(statistics.fmean(self.m[x]["p"])) if self.m[x]["p"] else None for x in ms],
            "ppy": [ppy(self.m[x]["ppm"]) for x in ms],
            "cancel": [self.m[x]["cancel"] for x in ms],
            "direct": [self.m[x]["direct"] for x in ms],
            "jn": [self.m[x]["jn"] for x in ms],
            "wn": [self.m[x]["wn"] for x in ms],
            "jppy": [ppy(self.m[x]["jppm"]) for x in ms],
        }
        if bands:
            out["bands"] = {b: {"n": [len(self.m[x]["b"][b]["p"]) for x in ms],
                                "med": [rint(med(self.m[x]["b"][b]["p"])) for x in ms],
                                "ppy": [ppy(self.m[x]["b"][b]["ppm"]) for x in ms]} for b in self.bk}
        return out

    def stats(self, asof_ym: str) -> dict:
        """지역 요약: 최근 3개월(집계 중인 이번 달 포함) 대 직전 3개월, 1년 전 같은 3개월."""
        cur = ym_range(asof_ym, 3)
        prev = ym_range(ym_add(asof_ym, -3), 3)
        yago = ym_range(ym_add(asof_ym, -12), 3)
        full = ym_range(ym_add(asof_ym, -1), 3)      # 거래량은 다 끝난 달만 비교
        fullp = ym_range(ym_add(asof_ym, -4), 3)
        p_cur, p_prev, p_y = (med(self.window(w, "ppm")) for w in (cur, prev, yago))
        j_cur = med(self.window(cur, "jppm"))
        allc, canc = self.count(cur, "all"), self.count(cur, "cancel")
        nval = self.count(cur, "n")
        monthly = [(ym, med(s["ppm"])) for ym, s in sorted(self.m.items()) if len(s["ppm"]) >= 5]
        peak = max((v for _, v in monthly), default=None)
        v3, v3p = self.count(full, "n"), self.count(fullp, "n")
        return {
            "ppy": rint(p_cur * PY) if p_cur else None,
            "chg3m": pct(p_cur, p_prev), "yoy": pct(p_cur, p_y),
            "vol3m": v3, "volchg": pct(v3, v3p),
            "vol_last": self.count([ym_add(asof_ym, -1)], "n"),
            "vol_prev": self.count([ym_add(asof_ym, -2)], "n"),
            "jr": round(j_cur / p_cur * 100, 1) if j_cur and p_cur else None,
            "cancel": round(canc / allc * 100, 1) if allc else None,
            "direct": round(self.count(cur, "direct") / nval * 100, 1) if nval else None,
            "dd": pct(p_cur, peak) if peak and p_cur else None,
            "band_ppy": {b: (rint(med(self.window(cur, "ppm", b)) * PY) if self.window(cur, "ppm", b) else None)
                         for b in self.bk},
        }


def type_stats(a: int, trs: list[dict], rts: list[dict], asof: dt.date, cfg: dict, bands: list[dict]):
    """단지 × 면적(㎡ 정수) 단위 지표. 거래 행에 nh(직전 최고가)·anom(기준 시세) 표시를 남긴다."""
    valid = [t for t in trs if not t["cancel"]]
    if not valid:
        return None
    day = dt.timedelta(days=1)
    recent_from = (asof - day * int(cfg.get("recent_days", 183))).isoformat()
    year_ago = (asof - day * 365).isoformat()
    # 저가 직거래 표시
    disc = float(cfg.get("anomaly_direct_discount_pct", 20)) / 100
    min_ref = int(cfg.get("anomaly_min_ref_trades", 3))
    for i, t in enumerate(valid):
        if not t["direct"]:
            continue
        lo = (dt.date.fromisoformat(t["date"]) - day * 183).isoformat()
        ref = [x["price"] for x in valid[:i] if not x["direct"] and x["date"] >= lo]
        if len(ref) >= min_ref and t["price"] <= med(ref) * (1 - disc):
            t["anom"] = rint(med(ref))
    base = [t for t in valid if "anom" not in t] or valid
    # 신고가
    run, peak_d, min_prior = 0, "", int(cfg.get("new_high_min_prior", 3))
    for i, t in enumerate(base):
        if t["price"] > run:
            if i >= min_prior:
                t["nh"] = run
            run, peak_d = t["price"], t["date"]
    peak = run
    rec = [t["price"] for t in base if t["date"] >= recent_from]
    last = base[-1]
    recent = rint(med(rec)) if rec else last["price"]
    stale = last["date"] < year_ago
    after = [t["price"] for t in base if t["date"] > peak_d]
    trough = min(after) if after else None
    y_from = (asof - day * (365 + int(cfg.get("recent_days", 183)))).isoformat()
    prev_year = med([t["price"] for t in base if y_from <= t["date"] < year_ago])
    # 전세 시세: 갱신 계약은 인상 한도 때문에 시세보다 낮게 찍히므로, 신규 계약이 있으면 신규만 본다.
    jall = [r for r in rts if not r["monthly"]]
    js = []
    for since in (recent_from, year_ago):
        win = [r for r in jall if r["date"] >= since]
        js = [r["deposit"] for r in win if not r.get("renew")] or [r["deposit"] for r in win]
        if js:
            break
    jeonse = rint(med(js)) if js else None
    two_y = (asof - day * 730).isoformat()
    lf = int(cfg.get("low_floor_max", 3))
    lows = [t["price"] for t in base if t["date"] >= two_y and t["floor"] is not None and t["floor"] <= lf]
    highs = [t["price"] for t in base if t["date"] >= two_y and t["floor"] is not None and t["floor"] > lf]
    area = med([t["area"] for t in valid])
    ok = jeonse is not None and not stale
    # 지역 변동률의 재료: 같은 집(단지·면적)의 최근 3개월 중위가를 직전 3개월·1년 전 같은 3개월과 비교한다.
    ym = asof.isoformat()[:7]

    def mwin(end: str):
        lo = ym_add(end, -2)
        return med([t["price"] for t in base if lo <= t["date"][:7] <= end])

    m_cur = mwin(ym)
    return {
        "_c3": pct(m_cur, mwin(ym_add(ym, -3)), 2), "_cy": pct(m_cur, mwin(ym_add(ym, -12)), 2),
        "a": a, "area": round(area, 2), "band": band_of(area, bands), "n": len(valid),
        "recent": recent, "rn": len(rec), "last_d": last["date"], "stale": 1 if stale else 0,
        "peak": peak, "peak_d": peak_d, "dd": pct(recent, peak),
        "trough": trough, "reb": pct(recent, trough) if trough else None,
        "chg1y": pct(recent, prev_year) if prev_year else None,
        "jeonse": jeonse, "jr": round(jeonse / recent * 100, 1) if ok and recent else None,
        "gap": recent - jeonse if ok else None,
        "low": rint(med(lows)), "high": rint(med(highs)),
        "ppy": rint(recent / area * PY),
    }


INDEX_COLS = ["id", "name", "sgg", "umd", "by", "hh", "a", "band", "price", "ppy", "dd", "reb", "jr", "gap",
              "n12", "turn", "chg1y", "lat", "lng", "sub", "nh", "stale"]


def process_gu(reg: dict, trades: list[dict], rents: list[dict], complexes: dict, specs: dict,
               cfg: dict, asof: dt.date) -> dict:
    """한 시군구의 모든 지표. trades·rents 에는 cid 가 붙어 있어야 한다."""
    bands = cfg["area_bands"]
    bk = [b["key"] for b in bands]
    acc = SeriesAcc(bk)
    dong_acc: dict[str, SeriesAcc] = defaultdict(lambda: SeriesAcc(bk))
    weekly: Counter = Counter()
    age: dict[str, list] = defaultdict(list)
    day = dt.timedelta(days=1)
    wk_from = (asof - day * 7 * 26).isoformat()
    recent_from = (asof - day * int(cfg.get("recent_days", 183))).isoformat()
    y1 = (asof - day * 365).isoformat()
    y3 = (asof - day * 365 * 3).isoformat()
    list_from = (asof - day * int(cfg.get("newhigh_list_days", 30))).isoformat()
    edges = cfg.get("age_bands", [5, 10, 20, 30])

    t_by: dict[str, dict[int, list]] = defaultdict(lambda: defaultdict(list))
    r_by: dict[str, dict[int, list]] = defaultdict(lambda: defaultdict(list))
    for t in trades:
        band = band_of(t["area"], bands)
        acc.add_trade(t, band)
        dong_acc[t["umd"]].add_trade(t, band)
        t_by[t["cid"]][int(t["area"])].append(t)
        if not t["cancel"]:
            if t["date"] >= wk_from:
                d = dt.date.fromisoformat(t["date"])
                weekly[(d - day * d.weekday()).isoformat()] += 1
            if t["date"] >= recent_from and t.get("by"):
                age[age_label(max(0, asof.year - t["by"]), edges)].append(t["price"] / t["area"])
    for r in rents:
        acc.add_rent(r)
        dong_acc[r["umd"]].add_rent(r)
        r_by[r["cid"]][int(r["area"])].append(r)

    index_rows, newhighs, anoms, apts = [], [], [], {}
    # 지역 전세가율 = 같은 단지·같은 면적끼리 맞춘 전세가율들의 중위값(서로 다른 집을 섞어 나누지 않는다).
    jr_all: list[float] = []
    jr_dong: dict[str, list[float]] = defaultdict(list)
    # 지역 변동률도 같은 방식: 평단가 중위값끼리 나누면 '어떤 집이 팔렸는지'에 따라 출렁이므로,
    # 같은 집의 변동률을 모아 그 중위값을 쓴다. c3 = 직전 3개월 대비, cy = 1년 전 대비.
    chg_all: dict[str, list[float]] = {"c3": [], "cy": []}
    chg_dong: dict[str, dict[str, list[float]]] = defaultdict(lambda: {"c3": [], "cy": []})
    # 흐름 지수의 재료: 기준 달에서 거꾸로 3개월씩 끊은 분기 k(0 = 최근 3개월)마다,
    # 같은 집의 '최근 3개월 중위가 ÷ 분기 k 중위가'를 모은다(과거 각 분기를 지금과 직접 비교).
    # 분기를 차례로 이어 붙이는 방식은 거래가 마른 하락기에 오차가 쌓여 5년 넘는 구간이 실제보다 높게 나왔다
    # (2026-11 실측: 서울 5년 변동 직접 비교 +7.6% vs 이어 붙이기 +26.5%). 그래서 직접 비교를 쓴다.
    qlinks: dict[int, list[float]] = defaultdict(list)
    asof_i = asof.year * 12 + asof.month - 1
    for cid, types in t_by.items():
        c = complexes[cid]
        spec = specs.get(cid) or {}
        tstats = []
        for a in sorted(types):
            st = type_stats(a, types[a], r_by.get(cid, {}).get(a, []), asof, cfg, bands)
            if st:
                for k in ("c3", "cy"):
                    v = st.pop("_" + k)
                    if v is not None:
                        chg_all[k].append(v)
                        chg_dong[c["umd"]][k].append(v)
                tstats.append(st)
                qp: dict[int, list] = defaultdict(list)
                for t in types[a]:
                    if not t["cancel"] and "anom" not in t:
                        qp[(asof_i - (int(t["date"][:4]) * 12 + int(t["date"][5:7]) - 1)) // 3].append(t["price"])
                if 0 in qp:
                    now = med(qp[0])
                    for k, v in qp.items():
                        if k > 0:
                            qlinks[k].append(now / med(v))
                if st["jr"] is not None and st["rn"]:      # 최근 6개월 안에 매매가 있는 면적만
                    jr_all.append(st["jr"])
                    jr_dong[c["umd"]].append(st["jr"])
        if not tstats:
            continue
        cnt3 = {a: sum(1 for t in types[a] if not t["cancel"] and t["date"] >= y3) for a in types}
        main = max(tstats, key=lambda s: (cnt3[s["a"]], s["n"], -abs(s["a"] - 84)))
        all_t = [t for a in types for t in types[a]]
        all_t.sort(key=lambda t: t["date"])
        n12 = sum(1 for t in all_t if not t["cancel"] and t["date"] >= y1)
        hh = spec.get("hh")
        nh_dates = [t["date"] for t in all_t if "nh" in t and t["date"] >= list_from]
        for t in all_t:
            if t["date"] < list_from or t["cancel"]:
                continue
            ent = {"id": cid, "name": c["name"], "sgg": reg["sgg"], "gu": reg["name"], "a": int(t["area"]),
                   "price": t["price"], "date": t["date"], "floor": t["floor"]}
            if "nh" in t:
                newhighs.append({**ent, "prev": t["nh"], "rise": pct(t["price"], t["nh"])})
            if "anom" in t:
                anoms.append({**ent, "ref": t["anom"], "disc": pct(t["price"], t["anom"])})
        sub = (spec.get("subway") or {}).get("dist")
        index_rows.append([
            cid, c["name"], reg["sgg"], c["umd"], c.get("by"), hh, main["a"], main["band"], main["recent"],
            main["ppy"], main["dd"], main["reb"], main["jr"], main["gap"], n12,
            round(n12 / hh * 100, 1) if hh else None, main["chg1y"],
            spec.get("lat"), spec.get("lng"), sub, max(nh_dates) if nh_dates else None, main["stale"],
        ])
        all_r = [r for a in r_by.get(cid, {}) for r in r_by[cid][a]]
        all_r.sort(key=lambda r: r["date"])
        apts[cid] = {
            "id": cid, "name": c["name"], "sgg": reg["sgg"], "gu": reg["name"], "umd": c["umd"],
            "jibun": c.get("jibun", ""), "by": c.get("by"), "main": main["a"], "n12": n12,
            "turn": round(n12 / hh * 100, 1) if hh else None,
            "spec": {k: spec.get(k) for k in ("kapt", "hh", "dongs", "used", "parking", "heat", "top", "builder")
                     if spec.get(k) is not None} or None,
            "geo": {k: spec.get(k) for k in ("lat", "lng", "subway", "school") if spec.get(k) is not None} or None,
            "types": tstats,
            # 거래: [계약일, 면적, 층, 금액, 표시] — 표시: 1 해제, 2 직거래, 4 신고가, 8 저가 직거래
            "trades": [[t["date"], t["area"], t["floor"], t["price"],
                        (1 if t["cancel"] else 0) | (2 if t["direct"] else 0)
                        | (4 if "nh" in t else 0) | (8 if "anom" in t else 0)] for t in all_t],
            # 전월세: [계약일, 면적, 층, 보증금, 월세, 갱신]
            "rents": [[r["date"], r["area"], r["floor"], r["deposit"], r["monthly"], r["renew"]] for r in all_r],
        }
    return {"acc": acc, "dong_acc": dict(dong_acc), "weekly": weekly, "age": dict(age),
            "index_rows": index_rows, "newhighs": newhighs, "anoms": anoms, "apts": apts,
            "jr": jr_all, "jr_dong": dict(jr_dong), "chg": chg_all, "chg_dong": dict(chg_dong),
            "qlinks": dict(qlinks)}


def flow_index(links: dict[int, list[float]], asof_ym: str, min_n: int = 5) -> dict:
    """같은 집끼리 비교한 흐름 지수(최근 3개월 = 100).

    links[k] = 같은 집의 '최근 3개월 중위가 ÷ 분기 k 중위가' 목록(k = 1 이 직전 3개월, 4 가 1년 전).
    분기 k 의 값 = 100 ÷ 그 비율들의 중위값. 표본이 min_n 보다 적은 분기는 비워 둔다(None).
    m = 각 분기의 마지막 달(오래된 것부터).
    """
    ks = [k for k, v in links.items() if len(v) >= min_n]
    top = max(ks) if ks else 0
    v = [round(100 / med(links[k]), 1) if len(links.get(k, [])) >= min_n else None for k in range(top, 0, -1)]
    return {"m": [ym_add(asof_ym, -3 * k) for k in range(top, -1, -1)], "v": v + [100.0]}


def jr_med(xs: list[float], min_n: int = 3):
    """맞춘 전세가율 목록의 중위값. 표본이 너무 적으면 None."""
    return round(med(xs), 1) if len(xs) >= min_n else None


def apply_matched_chg(stats: dict, chg: dict | None, min_n: int = 5) -> dict:
    """지역 요약의 변동률(chg3m·yoy)을 '같은 집끼리 비교한 변동률의 중위값'으로 바꾼다. 표본이 적으면 None."""
    chg = chg or {}
    stats["chg3m"] = jr_med(chg.get("c3", []), min_n)
    stats["yoy"] = jr_med(chg.get("cy", []), min_n)
    return stats


def apply_index_dd(stats: dict, idx: dict) -> dict:
    """지역의 '전고점 대비'를 흐름 지수(같은 집끼리 비교) 기준으로 바꾼다. 지수가 너무 짧으면 그대로 둔다.

    월 중위 평단가의 최고 달과 견주면 그달에 비싼 집이 많이 팔렸는지에 따라 값이 출렁이기 때문.
    """
    v = [x for x in idx.get("v") or [] if x is not None]
    if len(v) > 2:
        stats["dd"] = pct(v[-1], max(v))
    return stats


def weekly_json(weekly: Counter, asof: dt.date, weeks: int = 26) -> dict:
    start = asof - dt.timedelta(days=asof.weekday())
    ws = [(start - dt.timedelta(days=7 * i)).isoformat() for i in range(weeks - 1, -1, -1)]
    return {"w": ws, "n": [weekly.get(w, 0) for w in ws]}


def age_json(age: dict, edges: list[int]) -> list[dict]:
    labels, lo = [], 0
    for e in edges:
        labels.append(f"{lo + 1 if lo else 0}~{e}년")
        lo = e
    labels.append(f"{lo}년 초과")
    return [{"label": lb, "ppy": rint(med(age[lb]) * PY), "n": len(age[lb])} for lb in labels if age.get(lb)]
