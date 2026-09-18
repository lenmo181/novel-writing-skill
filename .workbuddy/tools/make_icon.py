# -*- coding: utf-8 -*-
"""
平台头像图标生成器：512×512 PNG（≤500KB）
设计：靛紫对角渐变底 + 暖光晕 + 「文」+ 金色钢笔尖 + 星光
输出：dist/icon_512.png
"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = r"C:\Users\lenmo\Desktop\网络小说创作技能"
OUT = os.path.join(ROOT, "dist", "icon_512.png")
FONT = r"C:\Windows\Fonts\msyhbd.ttc"
S = 512

# ---------- 1. 对角渐变底（左上深靛 → 右下亮紫） ----------
c1 = (30, 27, 75)      # 深靛 #1E1B4B
c2 = (109, 40, 217)    # 亮紫 #6D28D9
img = Image.new("RGB", (S, S))
px = img.load()
for y in range(S):
    for x in range(S):
        t = (x + y) / (2 * S - 2)
        px[x, y] = tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))

# ---------- 2. 中央暖光晕 ----------
glow = Image.new("L", (S, S), 0)
gd = ImageDraw.Draw(glow)
gd.ellipse([96, 66, 416, 386], fill=110)
glow = glow.filter(ImageFilter.GaussianBlur(70))
violet_layer = Image.new("RGB", (S, S), (139, 92, 246))  # #8B5CF6
img = Image.composite(violet_layer, img, glow)

draw = ImageDraw.Draw(img)

# ---------- 3. 「文」主字 ----------
f = ImageFont.truetype(FONT, 300)
draw.text((248, 232), "文", font=f, fill=(255, 250, 240), anchor="mm")

# ---------- 4. 金色钢笔尖（右下，斜置，笔尖朝向字心） ----------
NW, NH = 168, 240                     # 最终尺寸
nib = Image.new("RGBA", (NW * 2, NH * 2), (0, 0, 0, 0))
nd = ImageDraw.Draw(nib)
cx = NW                                # 2x 画布中轴
GOLD, DARK, CREAM = (245, 158, 11, 255), (124, 45, 18, 255), (255, 251, 235, 255)
pts = []
for a in range(175, 366, 5):           # 顶部圆弧：左→上→右
    rad = math.radians(a)
    pts.append((cx + 80 * math.cos(rad), 140 + 80 * math.sin(rad)))
pts += [(cx + 80, 140), (cx + 56, 230), (cx + 20, 322), (cx, 356),
        (cx - 20, 322), (cx - 56, 230), (cx - 80, 140)]
nd.polygon(pts, fill=GOLD, outline=DARK, width=8)
nd.arc([cx - 62, 78, cx + 26, 162], 160, 268, fill=(253, 230, 138, 255), width=10)  # 高光弧
nd.line([(cx, 186), (cx, 306)], fill=CREAM, width=12)                                # 中缝
nd.ellipse([cx - 22, 308, cx + 22, 352], fill=CREAM)                                 # 通气孔白环
nd.ellipse([cx - 13, 317, cx + 13, 343], fill=DARK)                                  # 通气孔
nib = nib.resize((NW, NH), Image.LANCZOS).rotate(-40, expand=True, resample=Image.BICUBIC)
img.paste(nib, (222, 208), nib)

# ---------- 5. 星光 ----------
def sparkle(d, x, y, r, color):
    k = 0.22
    d.polygon([(x, y - r), (x + r * k, y - r * k), (x + r, y), (x + r * k, y + r * k),
               (x, y + r), (x - r * k, y + r * k), (x - r, y), (x - r * k, y - r * k)],
              fill=color)

sparkle(draw, 110, 112, 34, (252, 211, 77))
sparkle(draw, 408, 148, 20, (254, 243, 199))
sparkle(draw, 96, 388, 16, (252, 211, 77))

img.save(OUT, "PNG", optimize=True)
print("saved:", OUT, os.path.getsize(OUT), "bytes")
