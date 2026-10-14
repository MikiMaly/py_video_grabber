#!/usr/bin/env python3
"""Vygeneruje icon.png, icon.ico a icons/icon_*.png z icon.svg (logo hubu mmaly.cz).

    pip install cairosvg pillow
    python scripts/make_icons.py
"""
import io
from pathlib import Path

import cairosvg
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SIZES = [16, 32, 48, 64, 128, 256, 512]


def render(size: int) -> Image.Image:
    png = cairosvg.svg2png(url=str(ROOT / "icon.svg"), output_width=size, output_height=size)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def main():
    images = {s: render(s) for s in SIZES}
    (ROOT / "icons").mkdir(exist_ok=True)
    for s, img in images.items():
        img.save(ROOT / "icons" / f"icon_{s}.png", optimize=True)
    images[512].save(ROOT / "icon.png", optimize=True)
    # .ico: každá velikost vyrenderovaná zvlášť, ať jsou malé ikony ostré
    images[256].save(ROOT / "icon.ico", sizes=[(s, s) for s in SIZES if s <= 256],
                     append_images=[images[s] for s in SIZES if s < 256])
    print("hotovo:", ", ".join(f"{s}px" for s in SIZES), "+ icon.ico")


if __name__ == "__main__":
    main()
