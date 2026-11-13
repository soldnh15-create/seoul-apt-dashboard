"""지역·기간을 넣으면 표(CSV)로 저장 — 엑셀에서 바로 열린다(UTF-8 BOM, 한글 제목)."""
from __future__ import annotations

import csv
from pathlib import Path

from . import config, store

HEAD = {
    "trade": [("date", "계약일"), ("gu", "구"), ("umd", "법정동"), ("apt", "단지명"), ("area", "전용면적(㎡)"),
              ("floor", "층"), ("price", "거래금액(만원)"), ("by", "건축년도"), ("cancel", "해제여부"),
              ("direct", "직거래여부"), ("jibun", "지번"), ("apt_seq", "단지일련번호")],
    "rent": [("date", "계약일"), ("gu", "구"), ("umd", "법정동"), ("apt", "단지명"), ("area", "전용면적(㎡)"),
             ("floor", "층"), ("deposit", "보증금(만원)"), ("monthly", "월세(만원)"), ("by", "건축년도"),
             ("renew", "갱신여부"), ("term", "계약기간"), ("jibun", "지번")],
}
YN = {"cancel", "direct", "renew"}


def export(sggs: list[str], ym_from: str, ym_to: str, kind: str = "trade", out: Path | None = None,
           sample: bool | None = None, apt: str = "") -> tuple[Path, int]:
    """ym_from·ym_to 는 YYYYMM. apt 를 주면 단지명에 그 글자가 든 행만."""
    base = config.data_base(sample)
    names = {r["sgg"]: r["name"] for r in config.regions(False)}
    lo, hi = f"{ym_from[:4]}-{ym_from[4:6]}-00", f"{ym_to[:4]}-{ym_to[4:6]}-99"
    out = Path(out) if out else config.ROOT / "out" / f"{kind}_{'-'.join(sggs)}_{ym_from}_{ym_to}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([h for _, h in HEAD[kind]])
        for sgg in sggs:
            for r in store.load(base, kind, sgg):
                if not (lo <= r["date"] <= hi) or (apt and apt not in r["apt"]):
                    continue
                r["gu"] = names.get(sgg, sgg)
                w.writerow([("Y" if r.get(k) else "") if k in YN else ("" if r.get(k) is None else r.get(k))
                            for k, _ in HEAD[kind]])
                n += 1
    return out, n
