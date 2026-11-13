"""배포 전 검증. 하나라도 실패하면 종료코드 1 → 워크플로가 멈추고 깨진 데이터가 공개되지 않는다."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from . import config, store


def check(stats: dict, prev: dict, out: Path, cfg: dict, regs: list[dict], today: dt.date,
          no_sample: bool = False) -> list[str]:
    v = cfg.get("validate", {})
    errs: list[str] = []
    meta = store.read_json(out / "meta.json", default=None)
    index = store.read_json(out / "index.json", default=None)
    if not meta or not index or not index.get("rows"):
        return ["사이트 데이터(meta.json·index.json)가 없거나 비어 있음"]
    if no_sample and meta.get("sample"):
        errs.append("가상 샘플 데이터는 배포할 수 없음")
    errs.extend(f"스키마 변경 감지: {e}" for e in stats.get("schema_errors", []))
    for r in regs:
        if not (out / "gu" / f"{r['sgg']}.json").exists():
            errs.append(f"{r['name']} 데이터 파일 없음")
        elif not stats["by_gu"].get(r["sgg"]):
            errs.append(f"{r['name']} 매매 0건")
    drop = float(v.get("max_row_drop_pct", 10))
    for k, label in (("trade", "매매"), ("rent", "전월세")):
        old, new = prev.get(k, 0), stats.get(k, 0)
        if old and new < old * (1 - drop / 100):
            errs.append(f"{label} 행 수 급감: {old:,} → {new:,} (허용 -{drop}%)")
    for sgg, old in (prev.get("by_gu") or {}).items():
        new = stats["by_gu"].get(sgg)
        if new is not None and old >= 100 and new < old * 0.7:
            errs.append(f"{sgg} 매매 행 수 급감: {old:,} → {new:,}")
    if stats.get("trade"):
        o = stats["outliers"] / stats["trade"] * 100
        if o > float(v.get("max_outlier_pct", 0.5)):
            errs.append(f"가격 이상치 비율 {o:.2f}% (허용 {v.get('max_outlier_pct', 0.5)}%)")
        b = stats["blank"] / stats["trade"] * 100
        if b > float(v.get("max_blank_pct", 1.0)):
            errs.append(f"단지명·동 빈칸 비율 {b:.2f}% (허용 {v.get('max_blank_pct', 1.0)}%)")
    age = (today - dt.date.fromisoformat(stats["asof"])).days
    if age > int(v.get("max_stale_days", 45)):
        errs.append(f"최신 거래일이 {age}일 전({stats['asof']}) — 수집이 멈춘 것으로 보임")
    return errs


def run(sample: bool | None = None, no_sample: bool = False, update: bool = False,
        out: Path | None = None, today: dt.date | None = None, log=print) -> list[str]:
    sample = config.is_sample() if sample is None else sample
    base = config.data_base(sample)
    out = Path(out) if out else config.SITE / "data"
    stats = store.read_json(base / "state" / "build_stats.json", default=None)
    if not stats:
        errs = ["build 결과(build_stats.json)가 없음 — build 를 먼저 실행"]
    else:
        prev = store.read_json(base / "state" / "stats_prev.json")
        errs = check(stats, prev, out, config.settings(), config.regions(), today or dt.date.today(), no_sample)
    if errs:
        log("[검증 실패] 배포하지 않습니다")
        for e in errs:
            log(f"  ✗ {e}")
    else:
        log(f"[검증 통과] 매매 {stats['trade']:,} · 전월세 {stats['rent']:,} · 기준일 {stats['asof']}")
        if update:
            store.write_json(base / "state" / "stats_prev.json", stats)
    return errs
