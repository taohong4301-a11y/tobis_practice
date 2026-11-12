"""生成 YouTube 封面图（1280×720 PNG），文字只用日语＋英语。

用法:
    python scripts/make_thumbnail.py content/ep01_w1_full.json output/ep01_w1_thumb.png

封面文字来自合集 JSON 的 "thumbnail" 字段:
    "thumbnail": {"badge": "第1週", "badge_en": "Week 1",
                  "headline": "ビジネス通訳 練習", "lines": ["数字 20問", "英⇔日 40問", "ノート記号 30"]}
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_video as mv  # 复用同一套字体后备和配色

W, H = 1280, 720
NAVY, PANEL = mv.BG, (30, 40, 62)
GOLD, CYAN, WHITE, GREY = mv.GOLD, mv.CYAN, mv.WHITE, mv.GREY


def centered(d, cx, y, text, bold, size, fill):
    mv.draw_text(d, cx - mv.text_len(d, text, bold, size) / 2, y, text, bold, size, fill)


def fit(d, text, bold, size, maxw):
    """字号自动缩小，保证一行放得下。"""
    while size > 20 and mv.text_len(d, text, bold, size) > maxw:
        size -= 2
    return size


def make(spec, out):
    t = spec["thumbnail"]
    img = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(img)

    # 左侧金色竖条 + 右侧周数面板
    d.rectangle([0, 0, 22, H], fill=GOLD)
    px0 = 820
    d.rounded_rectangle([px0, 70, W - 60, 470], radius=36, fill=PANEL, outline=GOLD, width=6)
    pcx = (px0 + W - 60) / 2
    bs = fit(d, t["badge"], True, 150, W - 60 - px0 - 40)
    centered(d, pcx, 120, t["badge"], True, bs, GOLD)
    centered(d, pcx, 120 + int(bs * 1.25), t["badge_en"], True, 56, WHITE)
    centered(d, pcx, 120 + int(bs * 1.25) + 90, "EN ⇔ JA", True, 44, CYAN)

    # 左侧标题
    mv.draw_text(d, 70, 64, "ビジネス通訳検定 対策", False, 36, GREY)
    mv.draw_text(d, 64, 110, "TOBIS", True, 190, WHITE)
    hs = fit(d, t["headline"], True, 68, px0 - 70 - 40)
    mv.draw_text(d, 70, 340, t["headline"], True, hs, CYAN)
    mv.draw_text(d, 70, 340 + int(hs * 1.35), "Interpreting Practice", True, 40, GREY)

    # 底部：内容标签
    x, y = 70, 560
    for line in t["lines"]:
        size = 40
        w = mv.text_len(d, line, True, size)
        d.rounded_rectangle([x, y, x + w + 56, y + 92], radius=46, fill=PANEL, outline=CYAN, width=3)
        mv.draw_text(d, x + 28, y + 18, line, True, size, WHITE)
        x += w + 56 + 24

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"封面: {out}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("用法: python scripts/make_thumbnail.py <合集.json> <输出.png>")
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    if "thumbnail" not in spec:
        sys.exit('合集 JSON 里没有 "thumbnail" 字段（格式见本文件开头）')
    make(spec, sys.argv[2])
