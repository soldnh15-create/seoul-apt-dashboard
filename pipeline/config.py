"""설정 파일 읽기와 경로 규칙."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
SITE = ROOT / "site"


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=None)
def settings() -> dict:
    return load_yaml(CONFIG / "settings.yaml")


@lru_cache(maxsize=None)
def site_config() -> dict:
    return load_yaml(CONFIG / "site.yaml")


@lru_cache(maxsize=None)
def overrides() -> dict:
    o = load_yaml(CONFIG / "complex_overrides.yaml")
    return {k: (o.get(k) or {}) for k in ("rent_to_complex", "kapt", "rename")}


def regions(only_enabled: bool = True) -> list[dict]:
    """시군구 목록. 각 항목: sgg, name, sido, sido_name, sido_short, lat, lng"""
    out = []
    for sido in load_yaml(CONFIG / "regions.yaml").get("sidos", []):
        if only_enabled and not sido.get("enabled"):
            continue
        for g in sido.get("sigungu", []):
            out.append({
                "sgg": str(g["code"]), "name": g["name"],
                "sido": str(sido["code"]), "sido_name": sido["name"],
                "sido_short": sido.get("short", sido["name"]),
                "lat": g.get("lat"), "lng": g.get("lng"),
            })
    return out


def is_sample() -> bool:
    return os.environ.get("APT_SAMPLE", "") == "1"


def data_base(sample: bool | None = None) -> Path:
    """실제 데이터는 data/, 가상 샘플은 data/sample/ — 절대 섞이지 않게 분리한다."""
    if sample is None:
        sample = is_sample()
    return ROOT / "data" / "sample" if sample else ROOT / "data"
