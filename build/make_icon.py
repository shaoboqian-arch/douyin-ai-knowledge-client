# -*- coding: utf-8 -*-
"""生成应用图标：深色圆角底 + 抖音红书签 + 青色播放三角。

只依赖 Pillow（构建机 Python 已有）。可复跑；已存在则跳过（--force 重画）。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "src", "app.ico")
BG = (14, 16, 20, 255)
RED = (254, 44, 85, 255)
CYAN = (37, 244, 238, 255)
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def draw(size):
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * 0.22), fill=BG)
    # 书签：两条竖边 + 下方缺口
    w = size * 0.46
    x0, x1 = (size - w) / 2, (size + w) / 2
    top, bottom = size * 0.20, size * 0.80
    notch = size * 0.12
    d.polygon([(x0, top), (x1, top), (x1, bottom), ((x0 + x1) / 2, bottom - notch), (x0, bottom)],
              fill=RED)
    # 播放三角
    cx, cy = size / 2, size * 0.45
    r = size * 0.11
    d.polygon([(cx - r * 0.75, cy - r), (cx - r * 0.75, cy + r), (cx + r, cy)], fill=CYAN)
    return im


def ensure(force=False):
    if os.path.isfile(OUT) and not force:
        return OUT
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    draw(256).save(OUT, format="ICO", sizes=SIZES)
    return OUT


if __name__ == "__main__":
    print(ensure(force="--force" in sys.argv))
