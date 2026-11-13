"""원천 데이터 저장: 시군구·연도별 gzip CSV. 같은 달을 다시 받으면 그 달만 통째로 바꾼다(멱등)."""
from __future__ import annotations

import csv
import gzip
import io
import json
from pathlib import Path

from .parse import KINDS

INT_COLS = {"floor", "price", "by", "cancel", "direct", "deposit", "monthly", "renew", "use_rr",
            "pre_deposit", "pre_monthly"}


def year_path(base: Path, kind: str, sgg: str, year: str | int) -> Path:
    return Path(base) / "raw" / kind / str(sgg) / f"{year}.csv.gz"


def read_year(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _encode(rows: list[dict], cols: list[str]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    lines = sorted(tuple("" if r.get(c) is None else str(r.get(c)) for c in cols) for r in rows)
    w.writerows(lines)
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", mtime=0) as g:  # mtime=0 → 같은 내용이면 같은 파일
        g.write(buf.getvalue().encode("utf-8"))
    return out.getvalue()


def write_year(path: Path, rows: list[dict], cols: list[str]) -> bool:
    """바뀐 경우에만 쓴다. 바뀌었으면 True."""
    data = _encode(rows, cols)
    if path.exists() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    return True


def replace_month(base: Path, kind: str, sgg: str, ym: str, rows: list[dict], guard: int = 0) -> tuple[int, int]:
    """ym(YYYYMM) 한 달 치를 새 행으로 교체. (이전 행 수, 새 행 수)

    guard > 0 이면, 원래 guard 건 이상 있던 달이 0건으로 바뀌려 할 때 덮어쓰지 않고 (이전 행 수, -1)을 돌려준다.
    """
    cols = KINDS[kind]["cols"]
    path = year_path(base, kind, sgg, ym[:4])
    prefix = f"{ym[:4]}-{ym[4:6]}"
    old = read_year(path)
    keep = [r for r in old if not r["date"].startswith(prefix)]
    old_n = len(old) - len(keep)
    new = [r for r in rows if str(r["date"]).startswith(prefix)]
    if guard and not new and old_n >= guard:
        return old_n, -1
    write_year(path, keep + new, cols)
    return old_n, len(new)


def month_count(base: Path, kind: str, sgg: str, ym: str) -> int:
    prefix = f"{ym[:4]}-{ym[4:6]}"
    return sum(1 for r in read_year(year_path(base, kind, sgg, ym[:4])) if r["date"].startswith(prefix))


def _typed(r: dict) -> dict:
    for k in r:
        v = r[k]
        if k in INT_COLS:
            r[k] = int(v) if v not in ("", None) else None
        elif k == "area":
            r[k] = float(v)
    return r


def load(base: Path, kind: str, sgg: str) -> list[dict]:
    """한 시군구의 전체 행(형 변환 포함), 날짜순."""
    d = Path(base) / "raw" / kind / str(sgg)
    rows: list[dict] = []
    if d.exists():
        for p in sorted(d.glob("*.csv.gz")):
            rows.extend(_typed(r) for r in read_year(p))
    rows.sort(key=lambda r: r["date"])
    return rows


def latest_date(base: Path, kind: str, sgg: str) -> str:
    d = Path(base) / "raw" / kind / str(sgg)
    files = sorted(d.glob("*.csv.gz")) if d.exists() else []
    for p in reversed(files):
        dates = [r["date"] for r in read_year(p)]
        if dates:
            return max(dates)
    return ""


# ── 체크포인트·상태 ──────────────────────────────────
def read_json(path: Path, default=None):
    if not Path(path).exists():
        return {} if default is None else default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj, compact: bool = False) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        if compact:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=True)
    tmp.replace(path)


def checkpoint_path(base: Path) -> Path:
    return Path(base) / "state" / "checkpoint.json"
