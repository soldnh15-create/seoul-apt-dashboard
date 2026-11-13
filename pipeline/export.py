"""원천 데이터 → 지표 → 사이트용 JSON(site/data). 지역·단지별로 쪼개서 필요한 것만 불러오게 한다."""
from __future__ import annotations

import csv
import datetime as dt
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from . import complexes as cx
from . import config, metrics, report, store
from .parse import KINDS

KST = dt.timezone(dt.timedelta(hours=9))


def find_asof(base: Path, sggs: list[str], today: dt.date) -> dt.date | None:
    dates = [d for d in (store.latest_date(base, "trade", s) for s in sggs) if d and d <= today.isoformat()]
    return dt.date.fromisoformat(max(dates)) if dates else None


def load_specs(base: Path) -> dict:
    """K-apt 스펙(kapt/specs.json)과 좌표(geo/geo.json)를 단지 ID 기준으로 합친다. 없으면 빈 사전."""
    specs = dict(store.read_json(Path(base) / "kapt" / "specs.json"))
    for cid, g in store.read_json(Path(base) / "geo" / "geo.json").items():
        specs.setdefault(cid, {}).update(g)
    return specs


def _top(rows: list[dict], n: int) -> list[dict]:
    return sorted(rows, key=lambda x: (x["date"], x.get("rise") or 0), reverse=True)[:n]


def build(sample: bool | None = None, out: Path | None = None, today: dt.date | None = None,
          base: Path | None = None, regs: list[dict] | None = None, log=print) -> dict:
    cfg = config.settings()
    sample = config.is_sample() if sample is None else sample
    base = Path(base) if base else config.data_base(sample)
    out = Path(out) if out else config.SITE / "data"
    today = today or dt.date.today()
    regs = regs or config.regions()
    bands = cfg["area_bands"]
    bk = [b["key"] for b in bands]
    asof = find_asof(base, [r["sgg"] for r in regs], today)
    if not asof:
        raise SystemExit("수집된 매매 데이터가 없습니다. 먼저 collect 를 실행하세요.")
    asof_ym = asof.isoformat()[:7]
    specs = load_specs(base)
    ov = config.overrides()
    vcfg = cfg.get("validate", {})

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    stats = {"asof": asof.isoformat(), "trade": 0, "rent": 0, "complexes": 0, "outliers": 0, "blank": 0,
             "by_gu": {}, "schema_errors": [], "sample": sample}
    sidos: dict[str, dict] = {}
    index_rows, unmatched_all = [], []
    kapt_hit = 0
    for reg in regs:
        trades = store.load(base, "trade", reg["sgg"])
        rents = store.load(base, "rent", reg["sgg"])
        trades = [t for t in trades if t["date"] <= asof.isoformat()]
        rents = [r for r in rents if r["date"] <= today.isoformat()]
        for kind, rows in (("trade", trades), ("rent", rents)):
            if rows and not set(KINDS[kind]["cols"]) <= set(rows[0]):
                stats["schema_errors"].append(f"{kind}:{reg['sgg']} 열 누락")
        stats["trade"] += len(trades)
        stats["rent"] += len(rents)
        stats["by_gu"][reg["sgg"]] = len(trades)
        stats["outliers"] += sum(1 for t in trades if not t["cancel"] and not
                                 (vcfg.get("price_min", 0) <= t["price"] <= vcfg.get("price_max", 10 ** 9)))
        stats["blank"] += sum(1 for t in trades if not t["apt"] or not t["umd"])
        cxs, unmatched = cx.assign(trades, rents, ov)
        unmatched_all.extend(unmatched)
        res = metrics.process_gu(reg, trades, rents, cxs, specs, cfg, asof)
        stats["complexes"] += len(res["apts"])
        kapt_hit += sum(1 for a in res["apts"].values() if a["spec"])
        for cid, apt in res["apts"].items():
            store.write_json(out / "apt" / reg["sgg"] / f"{cid}.json", apt, compact=True)
        index_rows.extend(res["index_rows"])

        gstats = res["acc"].stats(asof_ym)
        gstats["apts"] = len(res["apts"])
        dongs = []
        for umd, dacc in sorted(res["dong_acc"].items()):
            ds = dacc.stats(asof_ym)
            dongs.append({"umd": umd, **{k: ds[k] for k in ("ppy", "chg3m", "yoy", "vol3m", "volchg", "jr")}})
        store.write_json(out / "gu" / f"{reg['sgg']}.json", {
            "sgg": reg["sgg"], "name": reg["name"], "sido": reg["sido"], "asof": asof.isoformat(),
            "stats": gstats, "series": res["acc"].to_json(),
            "weekly": metrics.weekly_json(res["weekly"], asof),
            "dongs": dongs,
            "dong_series": {umd: {k: v for k, v in dacc.to_json(last=60, bands=False).items()
                                  if k in ("m", "n", "ppy", "jppy")} for umd, dacc in res["dong_acc"].items()},
            "age": metrics.age_json(res["age"], cfg.get("age_bands", [5, 10, 20, 30])),
            "newhighs": _top(res["newhighs"], 100), "anoms": _top(res["anoms"], 100),
        }, compact=True)

        s = sidos.setdefault(reg["sido"], {
            "code": reg["sido"], "name": reg["sido_name"], "short": reg["sido_short"],
            "acc": metrics.SeriesAcc(bk), "weekly": Counter(), "age": defaultdict(list),
            "gus": [], "newhighs": [], "anoms": []})
        s["acc"].merge(res["acc"])
        s["weekly"].update(res["weekly"])
        for k, v in res["age"].items():
            s["age"][k].extend(v)
        s["gus"].append({"sgg": reg["sgg"], "name": reg["name"], "lat": reg["lat"], "lng": reg["lng"], **gstats})
        s["newhighs"].extend(res["newhighs"])
        s["anoms"].extend(res["anoms"])
        log(f"  {reg['name']}: 매매 {len(trades):,} · 전월세 {len(rents):,} · 단지 {len(res['apts'])}")

    week_ago = (asof - dt.timedelta(days=7)).isoformat()
    sido_meta = []
    for code, s in sidos.items():
        kpi = s["acc"].stats(asof_ym)
        kpi["nh30"] = len(s["newhighs"])
        kpi["nh7"] = sum(1 for x in s["newhighs"] if x["date"] >= week_ago)
        doc = {
            "code": code, "name": s["name"], "short": s["short"], "asof": asof.isoformat(), "kpi": kpi,
            "series": s["acc"].to_json(), "weekly": metrics.weekly_json(s["weekly"], asof),
            "gus": s["gus"], "newhighs": _top(s["newhighs"], 300), "anoms": _top(s["anoms"], 200),
            "age": metrics.age_json(s["age"], cfg.get("age_bands", [5, 10, 20, 30])),
        }
        store.write_json(out / "sido" / f"{code}.json", doc, compact=True)
        ai = store.read_json(Path(base) / "report" / f"ai_{code}.json", default=None)
        store.write_json(out / "report" / f"{code}.json", report.build(doc, ai), compact=True)
        sido_meta.append({"code": code, "name": s["name"], "short": s["short"],
                          "gus": [{"sgg": g["sgg"], "name": g["name"]} for g in s["gus"]]})

    store.write_json(out / "index.json", {"cols": metrics.INDEX_COLS, "rows": index_rows}, compact=True)
    macro = store.read_json(Path(base) / "macro" / "macro.json", default=None)
    if macro:
        store.write_json(out / "macro.json", macro, compact=True)
    sc = config.site_config()
    store.write_json(out / "meta.json", {
        "updated": dt.datetime.now(KST).isoformat(timespec="minutes"), "asof": asof.isoformat(),
        "sample": sample, "site": sc, "sidos": sido_meta, "bands": bands,
        "partial": [metrics.ym_add(asof_ym, -1), asof_ym],
        "features": {"macro": bool(macro), "kapt": kapt_hit > 0,
                     "geo": any(r[17] is not None for r in index_rows)},
        "counts": {"trade": stats["trade"], "rent": stats["rent"], "complexes": stats["complexes"]},
        "params": {k: cfg.get(k) for k in ("recent_days", "low_floor_max", "anomaly_direct_discount_pct",
                                           "new_high_min_prior", "newhigh_list_days")},
    })
    stats["unmatched_rent"] = len(unmatched_all)
    state = Path(base) / "state"
    state.mkdir(parents=True, exist_ok=True)
    with open(state / "unmatched_rent.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["시군구코드|법정동|지번|단지명 (complex_overrides.yaml 의 rent_to_complex 키로 쓴다)"])
        w.writerows([k] for k in sorted(unmatched_all))
    store.write_json(state / "build_stats.json", stats)
    log(f"[내보내기] 기준일 {asof} · 매매 {stats['trade']:,} · 전월세 {stats['rent']:,} · "
        f"단지 {stats['complexes']:,} → {out}")
    return stats
