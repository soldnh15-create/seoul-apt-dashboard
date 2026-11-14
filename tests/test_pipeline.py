"""수집(이어받기·멱등)·단지 매칭·지표·검증·내보내기 테스트."""
import datetime as dt
import json

import pytest

from pipeline import api, collect, complexes, config, export, exportcsv, metrics, mock_api, report, store, validate

TODAY = dt.date.today()
GU = [r for r in config.regions() if r["sgg"] in ("11680", "11740")]
CFG = config.settings()
BANDS = CFG["area_bands"]


# ── 수집 ─────────────────────────────────────────────
def test_daily_collect_is_idempotent(tmp_path):
    s1 = collect.run("daily", sample=True, sggs=["11680"], base=tmp_path, log=lambda *_: None)
    files = sorted(tmp_path.rglob("*.csv.gz"))
    before = {p: p.read_bytes() for p in files}
    s2 = collect.run("daily", sample=True, sggs=["11680"], base=tmp_path, log=lambda *_: None)
    assert s1["done"] == s2["done"] == 6 and s1["rows"] == s2["rows"] > 0      # 3개월 × 매매·전월세
    assert before == {p: p.read_bytes() for p in sorted(tmp_path.rglob("*.csv.gz"))}


def test_backfill_resumes_from_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setitem(config.settings(), "backfill_years", 1)
    quiet = lambda *_: None  # noqa: E731
    s1 = collect.run("backfill", sample=True, sggs=["11680"], base=tmp_path, max_calls=4, log=quiet)
    assert s1["stopped"] and 0 < s1["done"] < s1["planned"] and s1["left"] > 0
    s2 = collect.run("backfill", sample=True, sggs=["11680"], base=tmp_path, log=quiet)
    assert s2["left"] == 6            # 남는 것은 매번 다시 받는 최근 3개월뿐
    assert s2["planned"] < s1["planned"] + 6
    s3 = collect.run("backfill", sample=True, sggs=["11680"], base=tmp_path, log=quiet)
    assert s3["planned"] == 6 and s3["done"] == 6


def test_quota_stops_gracefully_and_keeps_checkpoint(tmp_path):
    n = {"c": 0}

    def transport(url, timeout=30):
        n["c"] += 1
        if n["c"] > 3:
            return 200, ("<OpenAPI_ServiceResponse><cmmMsgHeader><returnAuthMsg>LIMITED_NUMBER_OF_SERVICE_"
                         "REQUESTS_EXCEEDS_ERROR</returnAuthMsg><returnReasonCode>22</returnReasonCode>"
                         "</cmmMsgHeader></OpenAPI_ServiceResponse>")
        return mock_api.transport(url)
    s = collect.run("daily", sggs=["11680"], kinds=("trade",), base=tmp_path, transport=transport,
                    months=["202401", "202402", "202403", "202404", "202405"], log=lambda *_: None)
    assert s["done"] == 3 and "한도" in s["stopped"]
    assert len(store.read_json(store.checkpoint_path(tmp_path))) == 3


def test_time_budget_stops_and_resumes_next_run(tmp_path, monkeypatch):
    """실행 시간 상한을 넘으면 받은 데까지 저장하고 멈춘다(자동 실행 제한 시간에 걸려 통째로 날리지 않게)."""
    monkeypatch.setitem(config.settings(), "collect_minutes_budget", 1)
    monkeypatch.setitem(config.settings(), "request_interval_sec", 0)
    clock = iter([0, 0] + [10 ** 6] * 50)            # 시작 → 첫 달은 통과 → 그다음부터 시간 초과
    monkeypatch.setattr(collect.time, "monotonic", lambda: next(clock))
    s = collect.run("daily", sggs=["11680"], kinds=("trade",), base=tmp_path, transport=mock_api.transport,
                    months=["202401", "202402", "202403"], log=lambda *_: None)
    assert s["done"] == 1 and "실행 시간" in s["stopped"]
    assert len(store.read_json(store.checkpoint_path(tmp_path))) == 1


def test_gives_up_early_when_api_unreachable(tmp_path, monkeypatch):
    monkeypatch.setitem(config.settings(), "retry_max", 0)

    def dead(url, timeout=30):
        raise api.TransientError("네트워크 오류: TimeoutError")
    s = collect.run("daily", sggs=["11680"], kinds=("trade",), base=tmp_path, transport=dead,
                    months=["202401", "202402", "202403", "202404", "202405"], log=lambda *_: None)
    assert s["done"] == 0 and len(s["failed"]) == 3 and "연결" in s["stopped"]


def test_missing_key_raises_auth_error(tmp_path, monkeypatch):
    monkeypatch.delenv(api.KEY_ENV, raising=False)
    with pytest.raises(api.AuthError):
        collect.run("daily", sggs=["11680"], base=tmp_path, log=lambda *_: None)


def test_suspicious_empty_month_is_not_overwritten(tmp_path):
    quiet = lambda *_: None  # noqa: E731
    collect.run("daily", sample=True, sggs=["11680"], kinds=("rent",), months=["202306"], base=tmp_path, log=quiet)
    had = store.month_count(tmp_path, "rent", "11680", "202306")
    assert had >= 20
    empty = lambda url, timeout=30: (200, mock_api.to_xml([], 1, 1000, 0))  # noqa: E731
    s = collect.run("daily", sggs=["11680"], kinds=("rent",), months=["202306"], base=tmp_path,
                    transport=empty, log=quiet)
    assert s["skipped_suspicious"] and store.month_count(tmp_path, "rent", "11680", "202306") == had


def test_replace_month_only_touches_that_month(tmp_path):
    row = lambda d, p: {"date": d, "sgg": "1", "apt": "A", "area": 59.9, "price": p}  # noqa: E731
    store.replace_month(tmp_path, "trade", "1", "202401", [row("2024-01-03", 1), row("2024-01-09", 2)])
    store.replace_month(tmp_path, "trade", "1", "202402", [row("2024-02-03", 3)])
    assert store.replace_month(tmp_path, "trade", "1", "202401", [row("2024-01-20", 9)]) == (2, 1)
    assert [(r["date"], r["price"]) for r in store.load(tmp_path, "trade", "1")] == \
        [("2024-01-20", 9), ("2024-02-03", 3)]


# ── 단지 매칭 ────────────────────────────────────────
def _t(date, price, area=84.97, apt="가나 마을", seq="11680-1", **kw):
    return {"date": date, "sgg": "11680", "umd": "역삼동", "umd_cd": "10100", "jibun": "10-1", "apt": apt,
            "apt_seq": seq, "area": area, "floor": kw.get("floor", 10), "price": price, "by": 2005,
            "cancel": kw.get("cancel", 0), "direct": kw.get("direct", 0)}


def _r(date, deposit, monthly=0, area=84.97, apt="가나마을", jibun="10-1", umd="역삼동"):
    return {"date": date, "sgg": "11680", "umd": umd, "jibun": jibun, "apt": apt, "apt_seq": "",
            "area": area, "floor": 5, "deposit": deposit, "monthly": monthly, "by": 2005, "renew": 0}


def test_rent_rows_attach_to_trade_complex():
    trades = [_t("2024-01-01", 100000), _t("2024-01-02", 90000, apt="다라아파트", seq="11680-2") | {"jibun": "20"}]
    rents = [_r("2024-01-05", 50000),                         # 이름 띄어쓰기만 다름 → 같은 단지
             _r("2024-01-06", 50000, apt="가나마을(주상복합)"),   # 괄호 설명 무시
             _r("2024-01-07", 40000, apt="전혀다른이름", jibun="20"),  # 지번이 유일하게 일치
             _r("2024-01-08", 30000, apt="없는단지", jibun="999")]
    cxs, unmatched = complexes.assign(trades, rents)
    assert [r["cid"] for r in rents[:3]] == ["11680-1", "11680-1", "11680-2"]
    assert unmatched == ["11680|역삼동|999|없는단지"] and rents[3]["cid"].startswith("x")
    cxs2, un2 = complexes.assign(trades, [_r("2024-01-08", 30000, apt="없는단지", jibun="999")],
                                 {"rent_to_complex": {"11680|역삼동|999|없는단지": "11680-2"}})
    assert un2 == []


def test_nameless_complex_gets_dong_prefix():
    cxs, _ = complexes.assign([_t("2024-01-01", 1, apt="(50-5)", seq="11680-9"), _t("2024-01-01", 1)], [])
    assert cxs["11680-9"]["name"] == "역삼동 (50-5)" and cxs["11680-1"]["name"] == "가나 마을"


def test_kapt_matching_needs_same_dong_and_similar_name():
    cxs, _ = complexes.assign([_t("2024-01-01", 1), _t("2024-01-01", 1, apt="다라", seq="11680-2")], [])
    kapt = [{"kaptCode": "A1", "kaptName": "가나마을아파트", "bjdCode": "1168010100"},
            {"kaptCode": "A2", "kaptName": "다라", "bjdCode": "1168099900"}]       # 다른 동
    assert complexes.match_kapt(cxs, kapt) == {"11680-1": "A1"}
    assert complexes.match_kapt(cxs, kapt, {"kapt": {"11680-2": "A9"}})["11680-2"] == "A9"


# ── 지표 ─────────────────────────────────────────────
def test_area_bands():
    assert [metrics.band_of(a, BANDS) for a in (39.6, 59.96, 60.0, 60.01, 84.97, 85.0, 101.9)] == \
        ["small", "small", "small", "std", "std", "std", "large"]


def test_type_stats_new_high_drawdown_jeonse_anomaly():
    asof = dt.date(2024, 12, 31)
    trs = [_t("2023-01-10", 100000), _t("2023-03-10", 105000), _t("2023-06-10", 110000),
           _t("2023-09-10", 120000),                       # 신고가(이전 3건 뒤)
           _t("2024-02-10", 90000, cancel=1),              # 해제 — 계산 제외
           _t("2024-08-10", 100000, floor=2), _t("2024-09-10", 104000), _t("2024-10-10", 102000),
           _t("2024-11-10", 78000, direct=1)]              # 시세 102000 대비 -23.5% 직거래
    rts = [_r("2024-10-01", 60000), _r("2024-11-01", 62000), _r("2024-11-05", 20000, monthly=150)]
    st = metrics.type_stats(84, trs, rts, asof, CFG, BANDS)
    assert trs[3]["nh"] == 110000 and "nh" not in trs[2] and "nh" not in trs[4]
    assert trs[8]["anom"] == 102000
    assert st["peak"] == 120000 and st["peak_d"] == "2023-09-10"
    assert st["recent"] == 102000 and st["rn"] == 3          # 저가 직거래·해제는 최근 시세에서 제외
    assert st["dd"] == -15.0 and st["trough"] == 100000 and st["reb"] == 2.0
    assert st["jeonse"] == 61000 and st["jr"] == 59.8 and st["gap"] == 41000
    assert st["low"] == 100000 and st["high"] == 104500 and st["band"] == "std"   # 최근 2년 저층·그 외 중위
    assert st["ppy"] == round(102000 / 84.97 * 3.3058)


def test_jeonse_uses_new_contracts_over_renewals():
    asof = dt.date(2024, 12, 31)
    trs = [_t("2024-09-10", 100000), _t("2024-10-10", 100000)]
    rts = [_r("2024-10-01", 50000) | {"renew": 1}, _r("2024-10-05", 52000) | {"renew": 1},
           _r("2024-11-01", 60000)]                         # 신규 1건이 갱신 2건보다 우선
    st = metrics.type_stats(84, trs, rts, asof, CFG, BANDS)
    assert st["jeonse"] == 60000 and st["jr"] == 60.0
    only_renew = metrics.type_stats(84, [dict(t) for t in trs], rts[:2], asof, CFG, BANDS)
    assert only_renew["jeonse"] == 51000                    # 신규가 없으면 갱신이라도 쓴다


def test_region_jeonse_ratio_is_median_of_matched_pairs():
    """구 전세가율은 '전세 평단가 ÷ 매매 평단가'가 아니라 단지·면적별 전세가율의 중위값."""
    asof = dt.date(2024, 12, 31)
    trades, rents = [], []
    for i, (price, dep) in enumerate([(100000, 60000), (200000, 80000), (50000, 40000)]):   # 60% · 40% · 80%
        seq = f"11680-{i + 1}"
        trades += [_t("2024-10-10", price, apt=f"단지{i}", seq=seq) | {"jibun": str(i)},
                   _t("2024-11-10", price, apt=f"단지{i}", seq=seq) | {"jibun": str(i)}]
        rents += [_r("2024-11-01", dep, apt=f"단지{i}", jibun=str(i))]
    rents += [_r("2024-11-02", 5000, apt="매매없는원룸", jibun="777", area=20.0)] * 30   # 매매 없는 전세는 영향 없음
    cxs, _ = complexes.assign(trades, rents)
    res = metrics.process_gu(GU[0], trades, rents, cxs, {}, CFG, asof)
    assert sorted(res["jr"]) == [40.0, 60.0, 80.0] and metrics.jr_med(res["jr"]) == 60.0
    assert metrics.jr_med([55.0, 60.0]) is None             # 표본 3개 미만이면 표시 안 함


def test_report_skips_comparison_when_history_is_missing():
    base = {"region": "서울", "ppy": 4560, "yoy": None, "vol_last": None, "up": [], "down": [], "jr": None,
            "nh30": 0, "nh7": 0, "newhighs": [], "cancel": None}
    first = report.render(base | {"chg3m": None})[0]
    assert first.endswith("4,560만원입니다.") and "변동" not in first
    assert "2.1% 올랐습니다" in report.render(base | {"chg3m": 2.1})[0]
    assert "1.5% 내렸습니다" in report.render(base | {"chg3m": -1.5})[0]
    assert "변동이 없었습니다" in report.render(base | {"chg3m": 0})[0]


def test_series_stats_windows():
    acc = metrics.SeriesAcc(["small", "std", "large"])
    for m, price in (("2024-04", 80000), ("2024-05", 80000), ("2024-06", 80000),
                     ("2024-07", 88000), ("2024-08", 88000), ("2024-09", 88000)):
        for d in (5, 15):
            acc.add_trade(_t(f"{m}-{d:02d}", price, area=80.0), "std")
        acc.add_rent(_r(f"{m}-10", 40000, area=80.0))
    acc.add_trade(_t("2024-09-20", 1, cancel=1), "std")
    s = acc.stats("2024-09")
    assert s["chg3m"] == 10.0 and s["ppy"] == round(1100 * 3.3058) and s["jr"] == round(500 / 1100 * 100, 1)
    assert s["cancel"] == round(1 / 7 * 100, 1) and s["vol3m"] == 6 and s["vol_last"] == 2
    j = acc.to_json()
    assert j["m"][0] == "2024-04" and j["n"][-1] == 2 and j["cancel"][-1] == 1 and j["bands"]["std"]["n"][0] == 2


def test_ym_helpers():
    assert metrics.ym_add("2024-01", -1) == "2023-12" and metrics.ym_range("2024-02", 3) == \
        ["2023-12", "2024-01", "2024-02"]
    assert collect.add_months("202401", -13) == "202212"


# ── 내보내기·검증 ────────────────────────────────────
@pytest.fixture(scope="module")
def built(tmp_path_factory):
    base, out = tmp_path_factory.mktemp("data"), tmp_path_factory.mktemp("site")
    months = collect.month_list(f"{TODAY.year:04d}{TODAY.month:02d}", 30)
    collect.run("daily", sample=True, sggs=[g["sgg"] for g in GU], months=months, base=base, log=lambda *_: None)
    store.write_json(base / "kapt" / "specs.json", mock_api.sample_specs())
    stats = export.build(sample=True, out=out, base=base, regs=GU, log=lambda *_: None)
    return base, out, stats


def test_build_writes_split_site_data(built):
    base, out, stats = built
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    assert meta["sample"] is True and meta["site"]["brand"] and meta["sidos"][0]["code"] == "11"
    assert meta["coverage"]["months"] == 30 and meta["coverage"]["target"] == CFG["backfill_years"] * 12
    assert index["cols"] == metrics.INDEX_COLS and len(index["rows"]) == stats["complexes"] > 10
    row = dict(zip(index["cols"], index["rows"][0]))
    apt = json.loads((out / "apt" / row["sgg"] / f"{row['id']}.json").read_text(encoding="utf-8"))
    assert apt["name"] == row["name"] and apt["trades"] and apt["rents"] and apt["spec"]["hh"] == row["hh"]
    assert all(len(t) == 5 for t in apt["trades"])
    gu = json.loads((out / "gu" / "11680.json").read_text(encoding="utf-8"))
    assert gu["series"]["m"] and gu["dongs"] and len(gu["weekly"]["w"]) == 26
    sido = json.loads((out / "sido" / "11.json").read_text(encoding="utf-8"))
    assert len(sido["gus"]) == 2 and sido["kpi"]["ppy"] > 0
    assert sum(sido["series"]["n"]) == sum(gu2["n"] for gu2 in [
        {"n": sum(json.loads((out / "gu" / f"{g['sgg']}.json").read_text(encoding="utf-8"))["series"]["n"])}
        for g in GU])
    rep = json.loads((out / "report" / "11.json").read_text(encoding="utf-8"))
    assert rep["lines"] and report.verify_numbers(" ".join(rep["lines"]), rep["facts"]) == []


def test_validate_passes_then_catches_problems(built):
    base, out, stats = built
    assert validate.check(stats, {}, out, CFG, GU, TODAY) == []
    assert any("샘플" in e for e in validate.check(stats, {}, out, CFG, GU, TODAY, no_sample=True))
    prev = {"trade": stats["trade"] * 2, "rent": stats["rent"], "by_gu": {}}
    assert any("급감" in e for e in validate.check(stats, prev, out, CFG, GU, TODAY))
    bad = {**stats, "outliers": stats["trade"] // 10}
    assert any("이상치" in e for e in validate.check(bad, {}, out, CFG, GU, TODAY))
    assert any("스키마" in e for e in validate.check({**stats, "schema_errors": ["trade:11680 열 누락"]},
                                                  {}, out, CFG, GU, TODAY))
    assert any("멈춘" in e for e in validate.check(stats, {}, out, CFG, GU, TODAY + dt.timedelta(days=90)))
    missing = GU + [{"sgg": "99999", "name": "없는구"}]
    assert any("없는구" in e for e in validate.check(stats, {}, out, CFG, missing, TODAY))


def test_ai_text_with_invented_number_is_rejected():
    f = {"region": "서울", "asof": "2024-12-31", "ppy": 4321, "chg3m": 1.2, "nh30": 15,
         "newhighs": [{"price": 245000}]}
    assert report.verify_numbers("평단가 4,321만원, 1.2% 상승, 신고가 15건, 24억 5,000만원", f) == []
    assert report.verify_numbers("평단가 4,321만원에서 내년 6,000만원 예상", f) == ["6,000"]
    doc_ai = {"text": "평단가는 9,999만원", "asof": "2024-12-31"}
    doc = {"asof": "2024-12-31", "short": "서울", "gus": [], "newhighs": [],
           "kpi": {k: None for k in ("ppy", "chg3m", "yoy", "vol_last", "vol_prev", "jr", "cancel", "direct")}
           | {"nh30": 0, "nh7": 0}}
    assert report.build(doc, doc_ai)["ai"] is None


def test_csv_export_for_other_teams(built, monkeypatch):
    base, out, _ = built
    monkeypatch.setattr(config, "data_base", lambda sample=None: base)
    ym = f"{TODAY.year - 1:04d}{TODAY.month:02d}"
    path, n = exportcsv.export(["11680"], ym, ym, "trade", base / "t.csv")
    text = path.read_bytes()
    assert text.startswith(b"\xef\xbb\xbf") and n > 0
    head = text.decode("utf-8-sig").splitlines()[0]
    assert head.startswith("계약일,구,법정동,단지명,전용면적(㎡),층,거래금액(만원)")
    assert "강남구" in text.decode("utf-8-sig").splitlines()[1]


def test_telegram_digest_only_sends_new_items():
    from pipeline import extras
    doc = {"short": "서울", "asof": "2024-12-31", "anoms": [],
           "newhighs": [{"id": "a", "name": "가상단지", "gu": "강남구", "a": 84, "price": 245000,
                         "date": "2024-12-20", "floor": 9, "rise": 3.1}]}
    text, keys = extras.digest(doc, set())
    assert "24억 5,000" in text and "+3.1%" in text and "투자 권유가 아닙니다" in text
    assert extras.digest(doc, set(keys)) == ("", [])
