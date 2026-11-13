"""API 원본 항목 → 정제된 행. 금액은 만원, 면적은 ㎡."""
from __future__ import annotations

import re

TRADE_COLS = ["date", "sgg", "umd", "umd_cd", "jibun", "apt", "apt_seq", "area", "floor", "price",
              "by", "cancel", "cancel_date", "direct", "dong", "rgst", "buyer", "seller", "agent"]
RENT_COLS = ["date", "sgg", "umd", "jibun", "apt", "apt_seq", "area", "floor", "deposit", "monthly",
             "by", "renew", "term", "use_rr", "pre_deposit", "pre_monthly"]

_NUM = re.compile(r"-?\d+")


def to_int(s, default=""):
    """'120,000' → 120000. 숫자가 없으면 default."""
    m = _NUM.search(str(s or "").replace(",", "").replace(" ", ""))
    return int(m.group()) if m else default


def to_float(s, default=""):
    try:
        return round(float(str(s).replace(",", "").strip()), 2)
    except (TypeError, ValueError):
        return default


def make_date(y, m, d) -> str:
    y, m, d = to_int(y, 0), to_int(m, 0), to_int(d, 0)
    if not (1990 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= 31):
        return ""
    return f"{y:04d}-{m:02d}-{d:02d}"


def norm_trade(it: dict, sgg: str) -> dict | None:
    date = make_date(it.get("dealYear"), it.get("dealMonth"), it.get("dealDay"))
    price = to_int(it.get("dealAmount"))
    area = to_float(it.get("excluUseAr"))
    if not date or price == "" or area == "":
        return None
    return {
        "date": date,
        "sgg": (it.get("sggCd") or sgg).strip() or sgg,
        "umd": (it.get("umdNm") or "").strip(),
        "umd_cd": (it.get("umdCd") or "").strip(),
        "jibun": (it.get("jibun") or "").strip(),
        "apt": (it.get("aptNm") or "").strip(),
        "apt_seq": (it.get("aptSeq") or "").strip(),
        "area": area,
        "floor": to_int(it.get("floor")),
        "price": price,
        "by": to_int(it.get("buildYear")),
        "cancel": 1 if (it.get("cdealType") or "").strip().upper() == "O" else 0,
        "cancel_date": (it.get("cdealDay") or "").strip(),
        "direct": 1 if "직" in (it.get("dealingGbn") or "") else 0,
        "dong": (it.get("aptDong") or "").strip(),
        "rgst": (it.get("rgstDate") or "").strip(),
        "buyer": (it.get("buyerGbn") or "").strip(),
        "seller": (it.get("slerGbn") or "").strip(),
        "agent": (it.get("estateAgentSggNm") or "").strip(),
    }


def norm_rent(it: dict, sgg: str) -> dict | None:
    date = make_date(it.get("dealYear"), it.get("dealMonth"), it.get("dealDay"))
    deposit = to_int(it.get("deposit"))
    area = to_float(it.get("excluUseAr"))
    if not date or deposit == "" or area == "":
        return None
    return {
        "date": date,
        "sgg": (it.get("sggCd") or sgg).strip() or sgg,
        "umd": (it.get("umdNm") or "").strip(),
        "jibun": (it.get("jibun") or "").strip(),
        "apt": (it.get("aptNm") or "").strip(),
        "apt_seq": (it.get("aptSeq") or "").strip(),
        "area": area,
        "floor": to_int(it.get("floor")),
        "deposit": deposit,
        "monthly": to_int(it.get("monthlyRent"), 0),
        "by": to_int(it.get("buildYear")),
        "renew": 1 if "갱신" in (it.get("contractType") or "") else 0,
        "term": (it.get("contractTerm") or "").strip(),
        "use_rr": 1 if "사용" in (it.get("useRRRight") or "") else 0,
        "pre_deposit": to_int(it.get("preDeposit")),
        "pre_monthly": to_int(it.get("preMonthlyRent")),
    }


KINDS = {
    "trade": {"cols": TRADE_COLS, "norm": norm_trade},
    "rent": {"cols": RENT_COLS, "norm": norm_rent},
}
