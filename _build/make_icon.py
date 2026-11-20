# -*- coding: utf-8 -*-
"""生成程序图标 assets/app.ico（不依赖设计稿）。"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw


def make(size: int = 256) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 圆角底：蓝色 → 紫色渐变
    radius = int(size * 0.22)
    base = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bd = ImageDraw.Draw(base)
    steps = size
    for i in range(steps):
        t = i / max(1, steps - 1)
        r = int(79 + (139 - 79) * t)
        g = int(140 + (92 - 140) * t)
        b = int(255 + (246 - 255) * t)
        bd.line([(0, i), (size, i)], fill=(r, g, b, 255))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1],
                                           radius=radius, fill=255)
    img.paste(base, (0, 0), mask)

    # 向上的箭头（分享/发出）
    cx = size / 2
    w = size * 0.10
    top = size * 0.26
    bottom = size * 0.60
    d.polygon([(cx, top), (cx - size * 0.17, top + size * 0.18),
               (cx + size * 0.17, top + size * 0.18)], fill=(255, 255, 255, 255))
    d.rounded_rectangle([cx - w / 2, top + size * 0.15, cx + w / 2, bottom],
                        radius=w / 2, fill=(255, 255, 255, 255))
    # 底托
    d.rounded_rectangle([size * 0.28, size * 0.68, size * 0.72, size * 0.74],
                        radius=size * 0.03, fill=(255, 255, 255, 210))
    return img


def main() -> None:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.path.join(here, "assets")
    os.makedirs(out_dir, exist_ok=True)
    big = make(256)
    big.save(os.path.join(out_dir, "app.ico"),
             sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                    (128, 128), (256, 256)])
    big.save(os.path.join(out_dir, "app.png"))
    print("icon written:", os.path.join(out_dir, "app.ico"))


if __name__ == "__main__":
    main()
