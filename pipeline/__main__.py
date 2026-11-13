"""실행 명령.  python -m pipeline <명령> [옵션]

  sample                가상 샘플로 전체 흐름 실행(키 불필요) → site/data 생성
  collect --mode daily  최근 3개월 다시 받기(매일)        collect --mode backfill  과거 채우기(이어받기)
  build                 지표 계산 + 사이트 데이터 내보내기
  validate              배포 전 검증(실패 시 종료코드 1)
  csv                   지역·기간 → 엑셀용 CSV
  kapt / geo / macro / ai-report / notify   선택 기능(키가 있을 때만 동작)
"""
from __future__ import annotations

import argparse
import os
import sys

from . import api, collect, config, export, exportcsv, extras, store, validate


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="python -m pipeline", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", action="store_true", help="가상 샘플 데이터(data/sample)로 실행")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("sample")
    p.add_argument("--years", type=int, default=None, help="샘플 기간(년). 기본은 settings 의 backfill_years")
    p = sub.add_parser("collect")
    p.add_argument("--mode", choices=["daily", "backfill"], default="daily")
    p.add_argument("--max-calls", type=int, default=None)
    p.add_argument("--sgg", nargs="*", help="시군구 코드(생략하면 설정된 전체)")
    p.add_argument("--months", nargs="*", help="YYYYMM 직접 지정")
    p.add_argument("--kinds", nargs="*", default=["trade", "rent"])
    sub.add_parser("build")
    p = sub.add_parser("validate")
    p.add_argument("--no-sample", action="store_true", help="샘플 데이터면 실패(배포용)")
    p.add_argument("--update", action="store_true", help="통과하면 기준 통계를 갱신")
    p = sub.add_parser("csv")
    p.add_argument("--sgg", nargs="+", required=True)
    p.add_argument("--from", dest="ym_from", required=True, help="YYYYMM")
    p.add_argument("--to", dest="ym_to", required=True, help="YYYYMM")
    p.add_argument("--kind", choices=["trade", "rent"], default="trade")
    p.add_argument("--apt", default="", help="단지명에 포함된 글자")
    p.add_argument("--out", default=None)
    for name in ("kapt", "geo", "macro"):
        sub.add_parser(name)
    p = sub.add_parser("ai-report")
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("notify")
    p.add_argument("--weekly", action="store_true")
    a = ap.parse_args(argv)

    sample = a.sample or a.cmd == "sample" or config.is_sample()
    if sample:
        os.environ["APT_SAMPLE"] = "1"
    try:
        if a.cmd == "sample":
            if a.years:
                config.settings()["backfill_years"] = a.years
            collect.run("backfill", sample=True)
            from . import mock_api
            store.write_json(config.data_base(True) / "kapt" / "specs.json", mock_api.sample_specs())
            export.build(sample=True)
            return 1 if validate.run(sample=True, update=True) else 0
        if a.cmd == "collect":
            s = collect.run(a.mode, sample=sample, max_calls=a.max_calls, kinds=tuple(a.kinds),
                            sggs=a.sgg or None, months=a.months or None)
            return 1 if s["failed"] and not s["done"] else 0
        if a.cmd == "build":
            export.build(sample=sample)
            return 0
        if a.cmd == "validate":
            return 1 if validate.run(sample=sample, no_sample=a.no_sample, update=a.update) else 0
        if a.cmd == "csv":
            path, n = exportcsv.export(a.sgg, a.ym_from, a.ym_to, a.kind, a.out, sample, a.apt)
            print(f"[CSV] {n:,}행 → {path}")
            return 0
        if a.cmd == "kapt":
            extras.kapt_update(sample)
        elif a.cmd == "geo":
            extras.geo_update(sample)
        elif a.cmd == "macro":
            extras.macro_update(sample)
        elif a.cmd == "ai-report":
            extras.ai_report(sample, a.force)
        elif a.cmd == "notify":
            extras.notify(sample, a.weekly)
        return 0
    except api.AuthError as e:
        print(f"[중단] {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
