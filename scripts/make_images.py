"""공유용 대표 이미지(og.png)와 홈 화면 아이콘(PNG)을 만든다. 한 번만 실행하면 된다.

    pip install Pillow
    python scripts/make_images.py

글꼴은 PC에 있는 맑은 고딕을 쓴다(없으면 기본 글꼴). 브랜드 이름은 config/site.yaml 에서 읽는다.
"""
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline import config  # noqa: E402

NAVY, WHITE, ORANGE, SOFT = "#14284b", "#ffffff", "#f08c00", "#b9c4d6"


def font(size: int, bold: bool = True):
    for p in (r"C:\Windows\Fonts\malgunbd.ttf" if bold else r"C:\Windows\Fonts\malgun.ttf",
              "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def bars(d: ImageDraw.ImageDraw, x: int, base: int, w: int, gap: int, heights: list[int], r: int):
    for i, h in enumerate(heights):
        d.rounded_rectangle([x + i * (w + gap), base - h, x + i * (w + gap) + w, base], radius=r, fill=WHITE)


def icon(size: int) -> Image.Image:
    im = Image.new("RGB", (size, size), NAVY)
    d = ImageDraw.Draw(im)
    u = size / 512
    bars(d, int(96 * u), int(400 * u), int(72 * u), int(28 * u), [int(150 * u), int(220 * u), int(290 * u)], int(8 * u))
    d.ellipse([int(374 * u), int(86 * u), int(442 * u), int(154 * u)], fill=ORANGE)
    return im


def og() -> Image.Image:
    sc = config.site_config()
    im = Image.new("RGB", (1200, 630), NAVY)
    d = ImageDraw.Draw(im)
    bars(d, 820, 520, 70, 28, [150, 240, 330], 10)
    d.ellipse([1100, 150, 1150, 200], fill=ORANGE)
    d.text((80, 90), sc.get("brand", ""), font=font(64), fill=ORANGE)
    d.text((80, 200), "서울 아파트", font=font(84), fill=WHITE)
    d.text((80, 315), "실거래 추적시스템", font=font(84), fill=WHITE)
    d.text((80, 470), "매일 자동 갱신 · 신고가 · 전세가율 · 무료", font=font(36, False), fill=SOFT)
    return im


if __name__ == "__main__":
    site = ROOT / "site"
    (site / "icons").mkdir(parents=True, exist_ok=True)
    icon(192).save(site / "icons" / "icon-192.png")
    icon(512).save(site / "icons" / "icon-512.png")
    og().save(site / "og.png", optimize=True)
    print("만들었어요: site/og.png, site/icons/icon-192.png, site/icons/icon-512.png")
