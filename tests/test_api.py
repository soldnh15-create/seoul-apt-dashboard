"""호출기·파서 테스트 — 공식 응답 형식을 본뜬 픽스처로 검증한다."""
from pathlib import Path

import pytest

from pipeline import api, mock_api, parse

FX = Path(__file__).parent / "fixtures"
ERR_KEY = ("<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg>"
           "<returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>"
           "<returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>")
ERR_QUOTA = ("<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg>"
             "<returnAuthMsg>LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR</returnAuthMsg>"
             "<returnReasonCode>22</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>")
NODATA = "<response><header><resultCode>03</resultCode><resultMsg>NODATA_ERROR</resultMsg></header></response>"
ERR_99 = "<response><header><resultCode>99</resultCode><resultMsg>UNKNOWN_ERROR</resultMsg></header></response>"


def test_trade_fixture_parses_and_normalizes():
    items, total = api.parse_xml_page((FX / "trade_ok.xml").read_text(encoding="utf-8"))
    assert total == 2 and len(items) == 2
    a, b = (parse.norm_trade(i, "11680") for i in items)
    assert a["price"] == 245000 and a["date"] == "2024-01-05" and a["area"] == 84.97
    assert a["cancel"] == 0 and a["direct"] == 0 and a["apt_seq"] == "11680-1" and a["dong"] == "101"
    assert b["price"] == 98500 and b["cancel"] == 1 and b["direct"] == 1 and b["floor"] == -1
    assert b["cancel_date"] == "24.02.01" and b["rgst"] == ""


def test_rent_fixture_parses_and_normalizes():
    items, _ = api.parse_xml_page((FX / "rent_ok.xml").read_text(encoding="utf-8"))
    a, b = (parse.norm_rent(i, "11680") for i in items)
    assert a["deposit"] == 120000 and a["monthly"] == 0 and a["renew"] == 1 and a["use_rr"] == 1
    assert a["pre_deposit"] == 110000
    assert b["deposit"] == 30000 and b["monthly"] == 280 and b["renew"] == 0 and b["pre_deposit"] == ""


def test_bad_rows_are_dropped():
    assert parse.norm_trade({"dealYear": "2024", "dealMonth": "13", "dealDay": "1", "dealAmount": "1",
                             "excluUseAr": "59"}, "11680") is None
    assert parse.norm_trade({"dealYear": "2024", "dealMonth": "1", "dealDay": "1", "dealAmount": "",
                             "excluUseAr": "59"}, "11680") is None


@pytest.mark.parametrize("body,exc", [
    (ERR_KEY, api.AuthError), (ERR_QUOTA, api.QuotaExceeded), (ERR_99, api.TransientError),
    ("<html>502 Bad Gateway</html", api.TransientError), ("서비스 점검 중", api.TransientError), ("", api.TransientError),
])
def test_errors_inside_http_200_are_detected(body, exc):
    with pytest.raises(exc):
        api.parse_xml_page(body)


def test_nodata_is_empty_not_error():
    assert api.parse_xml_page(NODATA) == ([], 0)


def _paged(total):
    rows = [{"n": i} for i in range(total)]

    def transport(url, timeout=30):
        import urllib.parse as up
        q = up.parse_qs(up.urlparse(url).query)
        p, s = int(q["pageNo"][0]), int(q["numOfRows"][0])
        return 200, mock_api.to_xml(rows[(p - 1) * s:p * s], p, s, total)
    return transport


def test_paging_collects_everything():
    c = api.Client("K", {"num_of_rows": 1000, "request_interval_sec": 0}, transport=_paged(2500))
    rows = c.fetch_all("https://x/y", {"LAWD_CD": "11680", "DEAL_YMD": "202401"})
    assert len(rows) == 2500 and c.calls == 3
    assert [r["n"] for r in rows[:3]] == ["0", "1", "2"]


def test_retry_with_exponential_backoff():
    seq = [(500, "err"), (200, "<html>"), (200, NODATA)]
    sleeps = []
    c = api.Client("K", {"retry_max": 4, "retry_base_sec": 1.5, "request_interval_sec": 0},
                   transport=lambda u, t=30: seq.pop(0), sleep=sleeps.append)
    assert c.get_page("https://x/y", {}) == ([], 0)
    assert sleeps == [1.5, 3.0] and c.calls == 3


def test_gives_up_after_max_retries_and_auth_is_not_retried():
    c = api.Client("K", {"retry_max": 2, "request_interval_sec": 0}, transport=lambda u, t=30: (503, ""),
                   sleep=lambda s: None)
    with pytest.raises(api.TransientError):
        c.get_page("https://x/y", {})
    assert c.calls == 3
    c2 = api.Client("K", {"retry_max": 4}, transport=lambda u, t=30: (200, ERR_KEY), sleep=lambda s: None)
    with pytest.raises(api.AuthError):
        c2.get_page("https://x/y", {})
    assert c2.calls == 1


def test_key_is_encoded_once_and_never_leaks_into_errors():
    assert "serviceKey=ab%2Bc%3D%3D&" in api.build_url("https://x/y", {"a": 1}, "ab+c==")
    assert "serviceKey=ab%2Bc%3D%3D&" in api.build_url("https://x/y", {"a": 1}, "ab%2Bc%3D%3D")
    c = api.Client("SECRETKEY123", {"retry_max": 0}, transport=lambda u, t=30: (500, u), sleep=lambda s: None)
    with pytest.raises(api.ApiError) as e:
        c.get_page("https://x/y", {})
    assert "SECRETKEY123" not in str(e.value)


def test_json_page_shapes():
    doc = '{"response":{"header":{"resultCode":"00"},"body":{"items":[{"kaptCode":"A1"}],"totalCount":1}}}'
    assert api.parse_json_page(doc) == ([{"kaptCode": "A1"}], 1)
    one = '{"response":{"header":{"resultCode":"00"},"body":{"item":{"kaptCode":"A1","kaptdaCnt":"500"}}}}'
    assert api.parse_json_page(one)[0][0]["kaptdaCnt"] == "500"
    with pytest.raises(api.AuthError):
        api.parse_json_page(ERR_KEY)
