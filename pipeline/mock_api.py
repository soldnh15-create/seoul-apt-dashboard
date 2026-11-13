"""가상 샘플 응답 생성기 — 인증키 없이 전체 흐름을 개발·시연하기 위한 것.

공식 응답과 같은 XML 모양으로, 지어낸(가상) 단지와 거래를 돌려준다.
단지 이름은 모두 '가상○○단지' 이고 실제 거래가 아니다. 샘플은 data/sample/ 에만 저장되고
사이트에는 '가상 샘플' 경고가 뜬다. 실제 배포 워크플로는 샘플 데이터를 거부한다.
"""
from __future__ import annotations

import datetime as dt
import random
import urllib.parse
from functools import lru_cache
from xml.sax.saxutils import escape

from . import config

AREAS = [39.6, 49.94, 59.96, 74.82, 84.97, 101.9, 114.5, 134.8]
# 순전히 시연용 상대 수준(실제 시세 아님)
LEVEL = {"11680": 2.3, "11650": 2.25, "11710": 1.8, "11170": 1.9, "11200": 1.6, "11440": 1.5,
         "11590": 1.35, "11560": 1.35, "11215": 1.4, "11470": 1.4, "11740": 1.3, "11140": 1.3,
         "11110": 1.25, "11410": 1.15, "11230": 1.05, "11290": 1.0, "11500": 1.0, "11380": 0.95,
         "11620": 0.95, "11530": 0.85, "11350": 0.85, "11260": 0.8, "11545": 0.78, "11305": 0.75,
         "11320": 0.72}
_IDX = [(201401, 0.60), (201801, 0.80), (202110, 1.25), (202301, 0.98), (202406, 1.08), (202712, 1.24)]
_VOL = [(201401, 1.0), (202006, 1.6), (202201, 0.7), (202210, 0.3), (202306, 0.8), (202712, 1.0)]


def _interp(points, ym: str) -> float:
    x = int(ym[:4]) * 12 + int(ym[4:6])
    pts = [(p // 100 * 12 + p % 100, v) for p, v in points]
    if x <= pts[0][0]:
        return pts[0][1]
    for (x0, v0), (x1, v1) in zip(pts, pts[1:]):
        if x <= x1:
            return v0 + (v1 - v0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


@lru_cache(maxsize=None)
def complexes_for(sgg: str) -> list[dict]:
    rng = random.Random(int(sgg))
    gu = next((r["name"] for r in config.regions(False) if r["sgg"] == sgg), "샘플")
    short = gu.replace("특별시", "").rstrip("구") or gu
    out = []
    for i in range(9 + rng.randrange(5)):
        out.append({
            "seq": f"{sgg}-{i + 1}", "name": f"가상{short}{i + 1}단지",
            "umd": f"가상{1 + i % 3}동", "umd_cd": f"{10100 + (i % 3) * 100}",
            "jibun": str(100 + i * 7), "by": rng.randint(1986, 2022),
            "hh": rng.choice([180, 320, 540, 860, 1200, 2400]),
            "types": sorted(rng.sample(AREAS, k=rng.choice([2, 3, 3]))),
            "q": rng.uniform(0.85, 1.2), "top": rng.choice([12, 15, 20, 25, 35]),
            "jr": rng.uniform(0.46, 0.66),
        })
    return out


def _sale_price(c: dict, sgg: str, area: float, ym: str, rng: random.Random, floor: int) -> int:
    ppm = 1150 * LEVEL.get(sgg, 1.0) * c["q"] * (1 + (c["by"] - 2000) / 150) * (1 + (84.97 - area) / 400)
    f = 0.95 if floor <= 3 else (1.02 if floor >= c["top"] * 0.6 else 1.0)
    return max(1000, round(area * ppm * _interp(_IDX, ym) * f * rng.uniform(0.97, 1.03) / 100) * 100)


def _gen(kind: str, sgg: str, ym: str) -> list[dict]:
    today = dt.date.today()
    y, m = int(ym[:4]), int(ym[4:6])
    rng = random.Random(f"{kind}:{sgg}:{ym}")
    vol = _interp(_VOL, ym)
    rows = []
    for c in complexes_for(sgg):
        if c["by"] > y:
            continue
        lam = c["hh"] * 0.0035 * vol * (1.0 if kind == "trade" else 2.2)
        n = int(lam) + (1 if rng.random() < lam - int(lam) else 0)
        for _ in range(n):
            d = dt.date(y, m, rng.randint(1, 28))
            if d > today or ((today - d).days < 30 and rng.random() < 0.5):  # 신고 지연 흉내
                continue
            area = rng.choice(c["types"])
            floor = rng.randint(1, c["top"])
            sale = _sale_price(c, sgg, area, ym, rng, floor)
            base = {"sggCd": sgg, "umdNm": c["umd"], "jibun": c["jibun"], "aptNm": c["name"],
                    "excluUseAr": f"{area}", "floor": str(floor), "buildYear": str(c["by"]),
                    "dealYear": str(y), "dealMonth": str(m), "dealDay": str(d.day)}
            if kind == "trade":
                direct = rng.random() < 0.07
                if direct and rng.random() < 0.35:
                    sale = round(sale * rng.uniform(0.70, 0.78) / 100) * 100
                cancel = rng.random() < 0.03
                reg = rng.random() < 0.6 and (today - d).days > 90
                rows.append({**base, "aptSeq": c["seq"], "umdCd": c["umd_cd"],
                             "dealAmount": f"{sale:,}", "dealingGbn": "직거래" if direct else "중개거래",
                             "cdealType": "O" if cancel else "", "cdealDay": d.strftime("%y.%m.%d") if cancel else "",
                             "rgstDate": (d + dt.timedelta(days=60)).strftime("%y.%m.%d") if reg else "",
                             "aptDong": str(101 + rng.randrange(8)) if reg else "",
                             "slerGbn": "개인", "buyerGbn": "개인",
                             "estateAgentSggNm": "" if direct else "서울 가상구"})
            else:
                jeonse = round(sale * c["jr"] * rng.uniform(0.95, 1.05) / 100) * 100
                renew = rng.random() < 0.3
                if rng.random() < 0.6:
                    dep, mon = jeonse, 0
                else:
                    dep = round(jeonse * rng.uniform(0.2, 0.35) / 100) * 100
                    mon = round((jeonse - dep) * 0.045 / 12)
                rows.append({**base, "deposit": f"{dep:,}", "monthlyRent": str(mon),
                             "contractType": "갱신" if renew else "신규",
                             "contractTerm": f"{y % 100:02d}.{m:02d}~{(y + 2) % 100:02d}.{m:02d}",
                             "useRRRight": "사용" if renew and rng.random() < 0.5 else "",
                             "preDeposit": f"{round(dep * 0.95 / 100) * 100:,}" if renew else "",
                             "preMonthlyRent": str(mon) if renew else ""})
    return rows


def to_xml(items: list[dict], page: int, size: int, total: int) -> str:
    body = "".join("<item>" + "".join(f"<{k}>{escape(str(v))}</{k}>" for k, v in it.items()) + "</item>"
                   for it in items)
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><response><header>'
            "<resultCode>000</resultCode><resultMsg>OK</resultMsg></header><body>"
            f"<items>{body}</items><numOfRows>{size}</numOfRows><pageNo>{page}</pageNo>"
            f"<totalCount>{total}</totalCount></body></response>")


def transport(url: str, timeout: float = 30) -> tuple[int, str]:
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    kind = "rent" if "AptRent" in url else "trade"
    rows = _gen(kind, q["LAWD_CD"][0], q["DEAL_YMD"][0])
    page, size = int(q.get("pageNo", ["1"])[0]), int(q.get("numOfRows", ["10"])[0])
    return 200, to_xml(rows[(page - 1) * size: page * size], page, size, len(rows))


def sample_specs() -> dict:
    """가상 단지의 스펙·좌표(K-apt·카카오 대신). 단지 ID(aptSeq) → 정보"""
    out = {}
    for r in config.regions():
        rng = random.Random(f"spec:{r['sgg']}")
        for c in complexes_for(r["sgg"]):
            out[c["seq"]] = {
                "kapt": f"S{c['seq'].replace('-', '')}", "hh": c["hh"], "dongs": max(1, c["hh"] // 110),
                "used": f"{c['by']}-06-30", "parking": round(c["hh"] * rng.uniform(0.6, 1.4)),
                "heat": rng.choice(["개별난방", "지역난방", "중앙난방"]), "top": c["top"],
                "builder": "가상건설",
                "lat": round((r["lat"] or 37.55) + rng.uniform(-0.012, 0.012), 5),
                "lng": round((r["lng"] or 127.0) + rng.uniform(-0.015, 0.015), 5),
                "subway": {"name": f"가상{rng.randint(1, 9)}호선역", "dist": rng.randint(120, 1400)},
                "school": {"name": "가상초등학교", "dist": rng.randint(80, 900)},
            }
    return out
