"""TOBIS 口译练习视频生成器

用法:
    python scripts/make_video.py content/ep01_part2_A.json output/ep01.mp4

流程（每题）: 题号卡 + 原文语音 → 提示音 → 倒计时（让观众口译）→ 原文/参考译文/要点 + 参考译文语音
同时输出 output/<名字>_chapters.txt（YouTube 章节时间戳）和 _description.txt（简介模板）。
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro
from misaki import ja
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "models" / "kokoro.onnx"
VOICES = ROOT / "models" / "voices.bin"

W, H, SR = 1280, 720, 24000
SPEED = float(os.environ.get("TOBIS_SPEED", "0.95"))        # 语速，1.0 = 正常
PAUSE_FACTOR = float(os.environ.get("TOBIS_PAUSE", "1.6"))  # 倒计时 = 原文时长 × 系数 + 3 秒
EN_VOICES = ["af_heart", "bm_george", "af_bella", "bm_lewis"]  # 英语声音轮换（美/英、女/男）
JA_VOICES = ["jf_alpha", "jm_kumo"]                             # 日语声音轮换

FONT_CANDIDATES = {
    "regular": [
        os.environ.get("TOBIS_FONT", ""),
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",          # macOS
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "C:/Windows/Fonts/YuGothM.ttc",                             # Windows
        "C:/Windows/Fonts/meiryo.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",   # Linux
    ],
    "bold": [
        os.environ.get("TOBIS_FONT_BOLD", ""),
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        "C:/Windows/Fonts/YuGothB.ttc",
        "C:/Windows/Fonts/meiryob.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    ],
}


def pick_font(kind):
    for p in FONT_CANDIDATES[kind]:
        if p and Path(p).exists():
            return p
    sys.exit(f"找不到日文字体，请设置环境变量 TOBIS_FONT / TOBIS_FONT_BOLD 指向一个 .ttc/.ttf 文件")


FONT, FONTB = pick_font("regular"), pick_font("bold")
WHITE, GREY, GOLD, CYAN, BG = (240, 240, 240), (150, 160, 180), (240, 190, 80), (110, 200, 230), (18, 24, 38)

kokoro = Kokoro(str(MODEL), str(VOICES))
g2p = ja.JAG2P()


def norm_ja(t):
    """让日语 TTS 读对数字: 去掉千分位逗号、小数点读成「点」、% 读成パーセント。"""
    t = re.sub(r"(?<=\d),(?=\d)", "", t)
    t = re.sub(r"(?<=[\d%])\s+|\s+(?=\d)", "", t)
    t = re.sub(r"(\d)\.(\d)", r"\1点\2", t)
    return t.replace("%", "パーセント").replace("〜", "から")


def tts(text, lang, idx):
    if lang == "ja":
        r = g2p(norm_ja(text))
        ph = r[0] if isinstance(r, tuple) else r
        s, _ = kokoro.create(ph, voice=JA_VOICES[idx % len(JA_VOICES)], speed=SPEED, is_phonemes=True)
    else:
        voice = EN_VOICES[idx % len(EN_VOICES)]
        s, _ = kokoro.create(text, voice=voice, speed=SPEED, lang="en-gb" if voice.startswith("b") else "en-us")
    return s.astype(np.float32)


def wrap(draw, text, font, maxw):
    is_cjk = re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", text)
    tokens = list(text) if is_cjk else re.findall(r"\S+\s*", text)
    lines, cur = [], ""
    for tok in tokens:
        if draw.textlength(cur + tok, font=font) > maxw and cur:
            lines.append(cur.rstrip())
            cur = tok.lstrip()
        else:
            cur += tok
    if cur:
        lines.append(cur.rstrip())
    return lines


def card(path, blocks):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    y = 60
    for text, size, color, bold, gap in blocks:
        f = ImageFont.truetype(FONTB if bold else FONT, size)
        for line in wrap(d, text, f, W - 160):
            d.text((80, y), line, font=f, fill=color)
            y += int(size * 1.45)
        y += gap
    img.save(path)


def seg(img, audio, out):
    sf.write(f"{out}.wav", audio, SR)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", img, "-i", f"{out}.wav",
                    "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-pix_fmt", "yuv420p",
                    "-r", "24", "-c:a", "aac", "-b:a", "128k", "-t", f"{len(audio) / SR:.3f}", f"{out}.mp4"],
                   check=True)
    return f"{out}.mp4", len(audio) / SR


def silence(sec):
    return np.zeros(int(SR * sec), np.float32)


def beep():
    t = np.arange(int(SR * 0.25)) / SR
    return (0.25 * np.sin(2 * np.pi * 880 * t)).astype(np.float32)


def stamp(sec):
    m, s = divmod(int(sec), 60)
    return f"{m}:{s:02d}"


def build(spec, outname):
    out = Path(outname)
    work = Path(tempfile.mkdtemp(prefix="tobis_"))
    parts, chapters, t = [], [], 0.0

    def add(p):
        nonlocal t
        parts.append(p[0])
        t += p[1]

    card(work / "intro.png", [(spec["title"], 44, WHITE, True, 30),
                              ("听到提示音后，在倒计时内开口口译，然后看答案。", 30, GREY, False, 10),
                              ("Listen → beep → interpret during the countdown → check the answer.", 26, GREY, False, 10),
                              ("语音为 AI 合成，题目为原创模拟题。", 22, GREY, False, 0)])
    add(seg(str(work / "intro.png"), silence(5), str(work / "p00")))

    for i, it in enumerate(spec["items"], 1):
        src_lang = "en" if it["dir"] == "EN→JA" else "ja"
        tgt_lang = "ja" if src_lang == "en" else "en"
        label = f"Q{i}  {it['dir']}  {it.get('tag', '')}".strip()
        chapters.append(f"{stamp(t)} Q{i} {it['dir']}")

        a_src = tts(it["src"], src_lang, i)
        card(work / f"q{i}a.png", [(label, 40, GOLD, True, 40), ("LISTEN  ·  聞いてください", 56, WHITE, True, 0)])
        add(seg(str(work / f"q{i}a.png"), np.concatenate([silence(1.0), a_src, silence(0.4), beep()]), str(work / f"q{i}a")))

        n = int(np.ceil(len(a_src) / SR * PAUSE_FACTOR + 3))
        for s in range(n, 0, -1):
            card(work / f"q{i}c{s}.png", [(label, 40, GOLD, True, 40),
                                          ("INTERPRET  ·  通訳してください", 52, CYAN, True, 40),
                                          (str(s), 120, WHITE, True, 0)])
            add(seg(str(work / f"q{i}c{s}.png"), silence(1.0), str(work / f"q{i}c{s}")))

        a_ref = tts(it["ref"], tgt_lang, i + 1)
        card(work / f"q{i}r.png", [(label, 34, GOLD, True, 20),
                                   ("原文", 24, GREY, False, 0), (it["src"], 30, WHITE, False, 24),
                                   ("参考译文", 24, GREY, False, 0), (it["ref"], 32, CYAN, True, 24),
                                   ("要点：" + it["note"], 26, GOLD, False, 0)])
        add(seg(str(work / f"q{i}r.png"), np.concatenate([silence(0.5), a_ref, silence(2.5)]), str(work / f"q{i}r")))
        print(f"Q{i}/{len(spec['items'])} done", flush=True)

    with open(work / "list.txt", "w") as f:
        for p in parts:
            f.write(f"file '{p}'\n")
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(work / "list.txt"), "-c", "copy", str(out)], check=True)

    chap = out.with_name(out.stem + "_chapters.txt")
    chap.write_text("\n".join(chapters) + "\n", encoding="utf-8")
    desc = out.with_name(out.stem + "_description.txt")
    desc.write_text(
        f"{spec['title']}\n\n"
        "TOBIS（ビジネス通訳検定）逐次通訳 Part 2 短文形式の練習用。\n"
        "听到提示音后在倒计时内口译，再对照参考译文。建议边做边录音，回听打分。\n\n"
        "※ 语音为 AI 合成（Kokoro TTS），题目为原创模拟题，与 CAIS 官方试题无关。\n\n"
        "章节 / Chapters\n" + "\n".join(chapters) + "\n",
        encoding="utf-8")
    print(f"视频: {out}\n章节: {chap}\n简介: {desc}\n总时长: {stamp(t)}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("用法: python scripts/make_video.py <题目.json> <输出.mp4>")
    build(json.load(open(sys.argv[1], encoding="utf-8")), sys.argv[2])
