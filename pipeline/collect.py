"""수집 실행기: 백필(이어받기)과 일일 업데이트.

- 백필: 최근 달부터 거꾸로 받는다. 받은 달은 체크포인트에 적어 두고, 한도에 걸리면 멈췄다가 다음 실행 때 이어받는다.
- 일일: 최근 N개월을 매일 다시 받아 신규·정정·해제를 반영한다.
"""
from __future__ import annotations

import datetime as dt
import time
from pathlib import Path

from . import api, config, store
from .parse import KINDS


def add_months(ym: str, k: int) -> str:
    """'202401' + k개월"""
    n = int(ym[:4]) * 12 + int(ym[4:6]) - 1 + k
    return f"{n // 12:04d}{n % 12 + 1:02d}"


def month_list(end_ym: str, count: int) -> list[str]:
    """end_ym 부터 과거로 count 개월(최근 달 먼저)."""
    return [add_months(end_ym, -i) for i in range(count)]


def plan(mode: str, today: dt.date, cfg: dict, sggs: list[str], ckpt: dict,
         kinds=("trade", "rent"), months: list[str] | None = None) -> list[tuple[str, str, str]]:
    """할 일 목록 [(kind, sgg, ym)]"""
    this_ym = f"{today.year:04d}{today.month:02d}"
    refetch = month_list(this_ym, int(cfg.get("refetch_months", 3)))
    if months:
        target, skip_done = months, False
    elif mode == "daily":
        target, skip_done = refetch, False
    else:
        target, skip_done = month_list(this_ym, int(cfg.get("backfill_years", 10)) * 12), True
    tasks = []
    for ym in target:
        for kind in kinds:
            for sgg in sggs:
                if skip_done and ym not in refetch and f"{kind}:{sgg}:{ym}" in ckpt:
                    continue
                tasks.append((kind, sgg, ym))
    return tasks


def run(mode: str = "daily", sample: bool = False, max_calls: int | None = None,
        kinds=("trade", "rent"), sggs: list[str] | None = None, months: list[str] | None = None,
        today: dt.date | None = None, transport=None, base: Path | None = None,
        log=print) -> dict:
    cfg = config.settings()
    base = Path(base) if base else config.data_base(sample)
    today = today or dt.date.today()
    sggs = sggs or [r["sgg"] for r in config.regions()]
    if sample:
        from . import mock_api
        key, transport, sleep = "SAMPLE", transport or mock_api.transport, (lambda s: None)
    else:
        key, sleep = api.service_key(), None
        if not key and transport is None:
            raise api.AuthError(f"환경변수 {api.KEY_ENV} 가 없습니다. README 의 '인증키 넣는 법'을 보세요.")
    kw = {"transport": transport} if transport else {}
    if sleep:
        kw["sleep"] = sleep
    clients = {k: api.Client(key or "TEST", cfg, **kw) for k in kinds}
    budget = int(max_calls if max_calls is not None else cfg.get("daily_call_budget", 9000))
    # 한 번 실행에 쓸 시간 상한(분). 넘으면 받은 데까지 저장하고 멈춘다 — 자동 실행 제한 시간에 걸려 통째로 날리지 않게.
    minutes = float(cfg.get("collect_minutes_budget", 0) or 0)
    deadline = time.monotonic() + minutes * 60 if minutes > 0 and not sample else None

    ck_path = store.checkpoint_path(base)
    ckpt = store.read_json(ck_path)
    tasks = plan(mode, today, cfg, sggs, ckpt, kinds, months)
    summary = {"mode": mode, "sample": sample, "started": dt.datetime.now().isoformat(timespec="seconds"),
               "planned": len(tasks), "done": 0, "rows": 0, "skipped_suspicious": [], "failed": [],
               "stopped": ""}
    stopped_kinds: set[str] = set()
    for kind, sgg, ym in tasks:
        if kind in stopped_kinds:
            continue
        if deadline is not None and time.monotonic() > deadline:
            summary["stopped"] = f"실행 시간 {minutes:g}분 도달 — 다음 실행에서 이어받습니다"
            break
        cl = clients[kind]
        if cl.calls >= budget:
            stopped_kinds.add(kind)
            summary["stopped"] = "하루 호출 예산 도달 — 다음 실행에서 이어받습니다"
            continue
        try:
            items = cl.fetch_all(cfg["endpoints"][kind], {"LAWD_CD": sgg, "DEAL_YMD": ym})
        except api.QuotaExceeded as e:
            stopped_kinds.add(kind)
            summary["stopped"] = f"{e} — 다음 실행에서 이어받습니다"
            continue
        except api.AuthError:
            store.write_json(ck_path, ckpt)
            raise
        except api.ApiError as e:
            summary["failed"].append(f"{kind}:{sgg}:{ym} {e}")
            log(f"  실패 {kind}:{sgg}:{ym} — {e}")
            if summary["done"] == 0 and len(summary["failed"]) >= 3:
                summary["stopped"] = "처음부터 연속 실패 — API에 연결되지 않아 중단"
                break
            if len(summary["failed"]) >= 20:
                summary["stopped"] = "오류가 20건 넘어 중단"
                break
            continue
        norm = KINDS[kind]["norm"]
        rows = [r for r in (norm(it, sgg) for it in items) if r]
        old_n, new_n = store.replace_month(base, kind, sgg, ym, rows, guard=20)
        if new_n < 0:
            # 원래 거래가 많던 달이 갑자기 0건이면 응답 이상으로 보고 덮어쓰지 않는다.
            summary["skipped_suspicious"].append(f"{kind}:{sgg}:{ym} (기존 {old_n}건 → 0건)")
            continue
        ckpt[f"{kind}:{sgg}:{ym}"] = today.isoformat()
        summary["done"] += 1
        summary["rows"] += len(rows)
        if summary["done"] % 50 == 0:
            store.write_json(ck_path, ckpt)
            log(f"  … {summary['done']}/{len(tasks)} 완료 (행 {summary['rows']:,}, 실패 {len(summary['failed'])})")
    store.write_json(ck_path, ckpt)
    summary["calls"] = {k: c.calls for k, c in clients.items()}
    summary["left"] = len(plan(mode, today, cfg, sggs, ckpt, kinds, months)) if mode == "backfill" and not months else 0
    summary["finished"] = dt.datetime.now().isoformat(timespec="seconds")
    store.write_json(Path(base) / "state" / "last_run.json", summary)
    log(f"[수집 {mode}] {summary['done']}/{summary['planned']}건, 행 {summary['rows']:,}, "
        f"호출 {summary['calls']}, 남은 백필 {summary['left']}"
        + (f" · {summary['stopped']}" if summary["stopped"] else ""))
    return summary
