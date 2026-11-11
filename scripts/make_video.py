"""TOBIS 口译练习视频生成器

用法:
    python scripts/make_video.py content/ep01_part2_A.json output/ep01.mp4
    python scripts/make_video.py content/ep01_w1_full.json output/ep01_w1.mp4
    python scripts/make_video.py content/ep01_w1_full.json output/ep01_w1.mp4 --preview   # 只画卡片，不合成语音/视频

流程（口译题）: 题号卡 + 原文语音 → 提示音 → 倒计时（让观众口译）→ 原文/参考译文/要点 + 参考译文语音
流程（SYMBOL 题）: 显示意思 → 倒计时（观众写出笔记符号）→ 显示符号
同时输出 output/<名字>_chapters.txt（YouTube 章节时间戳）和 _description.txt（简介模板）。
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from fontTools.ttLib import TTCollection, TTFont
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "models" / "kokoro.onnx"
VOICES = ROOT / "models" / "voices.bin"

W, H, SR = 1280, 720, 24000
SPEED = float(os.environ.get("TOBIS_SPEED", "0.95"))        # 语速，1.0 = 正常
PAUSE_FACTOR = float(os.environ.get("TOBIS_PAUSE", "1.6"))  # 倒计时 = 原文时长 × 系数 + 3 秒
EN_VOICES = ["af_heart", "bm_george", "af_bella", "bm_lewis"]  # 英语声音轮换（美/英、女/男）
JA_VOICES = ["jf_alpha", "jm_kumo"]                             # 日语声音轮换
PREVIEW = False

# 主字体：日文字形。第一个存在的文件生效。
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
# 后备字体：主字体缺的字（简体中文的 译/练/时…、特殊符号）逐字改用这里的字体。
FALLBACK_CANDIDATES = {
    "regular": [
        os.environ.get("TOBIS_FONT_FALLBACK", ""),
        "C:/Windows/Fonts/msyh.ttc",                                # 微软雅黑
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "C:/Windows/Fonts/seguisym.ttf",
    ],
    "bold": [
        os.environ.get("TOBIS_FONT_FALLBACK_BOLD", ""),
        "C:/Windows/Fonts/msyhbd.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "C:/Windows/Fonts/seguisym.ttf",
    ],
}


def cmap_of(path):
    f = TTCollection(path, lazy=True).fonts[0] if path.lower().endswith(".ttc") else TTFont(path, lazy=True)
    return set(f.getBestCmap())


def font_stack(kind):
    main = next((p for p in FONT_CANDIDATES[kind] if p and Path(p).exists()), None)
    if not main:
        sys.exit("找不到日文字体，请设置环境变量 TOBIS_FONT / TOBIS_FONT_BOLD 指向一个 .ttc/.ttf 文件")
    paths = [main] + [p for p in FALLBACK_CANDIDATES[kind] if p and p != main and Path(p).exists()]
    return [(p, cmap_of(p)) for p in paths]


STACKS = {"regular": font_stack("regular"), "bold": font_stack("bold")}
WHITE, GREY, GOLD, CYAN, BG = (240, 240, 240), (150, 160, 180), (240, 190, 80), (110, 200, 230), (18, 24, 38)
_fonts = {}


def get_font(path, size):
    if (path, size) not in _fonts:
        _fonts[(path, size)] = ImageFont.truetype(path, size)
    return _fonts[(path, size)]


def runs(text, bold, size):
    """把一行字按「哪个字体有这个字」切成几段，每段用同一个字体画。"""
    stack = STACKS["bold" if bold else "regular"]
    out = []
    for ch in text:
        if ch.isspace() and out:
            path = out[-1][0]
        else:
            path = next((p for p, cm in stack if ord(ch) in cm), stack[0][0])
        if out and out[-1][0] == path:
            out[-1][1] += ch
        else:
            out.append([path, ch])
    return [(get_font(p, size), t) for p, t in out]


def text_len(d, text, bold, size):
    return sum(d.textlength(t, font=f) for f, t in runs(text, bold, size))


def draw_text(d, x, y, text, bold, size, fill):
    base = y + size  # 不同字体按同一条基线对齐
    for f, t in runs(text, bold, size):
        d.text((x, base), t, font=f, fill=fill, anchor="ls")
        x += d.textlength(t, font=f)


_engines = None


def engines():
    global _engines
    if _engines is None:
        from kokoro_onnx import Kokoro
        from misaki import ja
        # pyopenjtalk 模式：不需要 fugashi/unidic 词典；Windows 用 pyopenjtalk-plus 的预编译包
        _engines = (Kokoro(str(MODEL), str(VOICES)), ja.JAG2P(version="pyopenjtalk"))
    return _engines


def norm_ja(t):
    """让日语 TTS 读对数字: 去掉千分位逗号、小数点读成「点」、% 读成パーセント。"""
    t = re.sub(r"(?<=\d),(?=\d)", "", t)
    t = re.sub(r"(?<=[\d%])\s+|\s+(?=\d)", "", t)
    t = re.sub(r"(\d)\.(\d)", r"\1点\2", t)
    for k, v in READING_FIXES.items():
        t = t.replace(k, v)
    return t.replace("%", "パーセント").replace("〜", "から")


# TTS 读错的词：原文 → 只给语音用的写法（画面上不变）
READING_FIXES = {
    "株買い": "株がい",          # 自社株買い：pyopenjtalk 读成 かぶかい
    "設備投資": "設備とうし",    # 读成 せつびとおし
    "FinOps": "フィンオプス",     # 否则逐字母读
    "7〜9月期": "7月から9月期",  # 否则读成 なな から くがつき
}


def tts(text, lang, idx):
    if PREVIEW:
        return silence(1.5)
    kokoro, g2p = engines()
    if lang == "ja":
        r = g2p(norm_ja(text))
        ph = r[0] if isinstance(r, tuple) else r
        s, _ = kokoro.create(ph, voice=JA_VOICES[idx % len(JA_VOICES)], speed=SPEED, is_phonemes=True)
    else:
        voice = EN_VOICES[idx % len(EN_VOICES)]
        s, _ = kokoro.create(text, voice=voice, speed=SPEED, lang="en-gb" if voice.startswith("b") else "en-us")
    return s.astype(np.float32)


def wrap(draw, text, bold, size, maxw):
    is_cjk = re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", text)
    tokens = list(text) if is_cjk else re.findall(r"\S+\s*", text)
    lines, cur = [], ""
    for tok in tokens:
        if text_len(draw, cur + tok, bold, size) > maxw and cur:
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
        for line in text.split("\n"):
            for wl in wrap(d, line, bold, size, W - 160):
                draw_text(d, 80, y, wl, bold, size, color)
                y += int(size * 1.45)
        y += gap
    img.save(path)


def seg(img, audio, out):
    if PREVIEW:
        return img, len(audio) / SR
    import soundfile as sf
    sf.write(f"{out}.wav", audio, SR)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", img, "-i", f"{out}.wav",
                    "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-pix_fmt", "yuv420p",
                    "-r", "24", "-c:a", "aac", "-b:a", "128k", "-t", f"{len(audio) / SR:.3f}", f"{out}.mp4"],
                   check=True)
    # 用编码后的真实时长（视频按帧取整会略长），否则章节时间越往后越早
    real = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                           f"{out}.mp4"], check=True, capture_output=True, text=True).stdout.strip()
    return f"{out}.mp4", float(real)


def silence(sec):
    return np.zeros(int(SR * sec), np.float32)


def beep():
    t = np.arange(int(SR * 0.25)) / SR
    return (0.25 * np.sin(2 * np.pi * 880 * t)).astype(np.float32)


def stamp(sec):
    m, s = divmod(int(np.ceil(sec + 0.5)), 60) if sec else (0, 0)  # 落在 3 秒章节卡的 0.5–1.5 秒处，不会停在上一题末尾
    return f"{m}:{s:02d}"


def load_spec(path):
    """单个题目文件，或带 "sources" 的合集文件（把多个题目文件按顺序拼起来）。"""
    path = Path(path)
    spec = json.load(open(path, encoding="utf-8"))
    if "sources" not in spec:
        return spec, [dict(it, _prefix="") for it in spec["items"]]
    items = []
    for src in spec["sources"]:
        sub = json.load(open(path.parent / src["file"], encoding="utf-8"))
        chapters = src.get("chapters", {})
        for j, it in enumerate(sub["items"], 1):
            it = dict(it, _prefix=src.get("label", ""))
            if str(j) in chapters:
                it["chapter"] = chapters[str(j)]
            if "countdown" in src:
                it.setdefault("countdown", src["countdown"])
            items.append(it)
    return spec, items


def build(spec, items, outname):
    out = Path(outname)
    if PREVIEW:
        work = out.with_name(out.stem + "_preview")
        work.mkdir(parents=True, exist_ok=True)
    else:
        work = Path(tempfile.mkdtemp(prefix="tobis_"))
    parts, chapters, t = [], ["0:00 开场"], 0.0
    use_chapters = any("chapter" in it for it in items)
    seen = set()  # 预览模式下每种题只画第一题

    def add(p):
        nonlocal t
        parts.append(p[0])
        t += p[1]

    def countdown(n, blocks_for, key):
        for s in range(n, 0, -1):
            if PREVIEW and s != n:
                break
            card(work / f"{key}c{s}.png", blocks_for(s))
            add(seg(str(work / f"{key}c{s}.png"), silence(1.0), str(work / f"{key}c{s}")))

    card(work / "intro.png", [(spec["title"], 44, WHITE, True, 30),
                              ("听到提示音后，在倒计时内开口口译，然后看答案。", 30, GREY, False, 10),
                              ("Listen → beep → interpret during the countdown → check the answer.", 26, GREY, False, 10),
                              ("语音为 AI 合成，题目为原创模拟题。", 22, GREY, False, 0)])
    add(seg(str(work / "intro.png"), silence(5), str(work / "p00")))

    if spec.get("day_guide"):
        card(work / "guide.png", [("按天练习建议 · 用章节跳到当天的部分", 38, GOLD, True, 30),
                                  ("\n".join(spec["day_guide"]), 26, WHITE, False, 0)])
        add(seg(str(work / "guide.png"), silence(10), str(work / "p01")))

    counters = {}
    for i, it in enumerate(items, 1):
        key = (it["_prefix"], it["dir"])
        counters[key] = counters.get(key, 0) + 1
        num = it.get("num", counters[key])
        label = f"{it['_prefix']}Q{num}  {it['dir'] if it['dir'] != 'SYMBOL' else '笔记符号'}  {it.get('tag', '')}".strip()

        if "chapter" in it:
            chapters.append(f"{stamp(t)} {it['chapter']}")
            card(work / f"ch{i}.png", [(it["chapter"], 48, GOLD, True, 30),
                                       ("Section start", 26, GREY, False, 0)])
            add(seg(str(work / f"ch{i}.png"), silence(3), str(work / f"ch{i}")))
        elif not use_chapters:
            chapters.append(f"{stamp(t)} {it['_prefix']}Q{num} {it['dir']}")

        if PREVIEW and key in seen and "chapter" not in it:
            continue
        seen.add(key)

        if it["dir"] == "SYMBOL":
            card(work / f"q{i}a.png", [(label, 40, GOLD, True, 40),
                                       ("写出笔记符号  ·  Write the symbol", 44, WHITE, True, 40),
                                       (it["src"], 64, CYAN, True, 0)])
            add(seg(str(work / f"q{i}a.png"), silence(2.0), str(work / f"q{i}a")))
            countdown(int(it.get("countdown", 4)),
                      lambda s: [(label, 40, GOLD, True, 40), (it["src"], 52, CYAN, True, 40),
                                 (str(s), 120, WHITE, True, 0)], f"q{i}")
            blocks = [(label, 34, GOLD, True, 20), ("意思", 24, GREY, False, 0), (it["src"], 40, WHITE, False, 24),
                      ("符号", 24, GREY, False, 0), (it["ref"], 150, CYAN, True, 24)]
            if it.get("note"):
                blocks.append(("要点：" + it["note"], 26, GOLD, False, 0))
            card(work / f"q{i}r.png", blocks)
            add(seg(str(work / f"q{i}r.png"), silence(3.0), str(work / f"q{i}r")))
            print(f"{i}/{len(items)} done", flush=True)
            continue

        src_lang = "en" if it["dir"] == "EN→JA" else "ja"
        tgt_lang = "ja" if src_lang == "en" else "en"
        a_src = tts(it["src"], src_lang, i)
        card(work / f"q{i}a.png", [(label, 40, GOLD, True, 40), ("LISTEN  ·  聞いてください", 56, WHITE, True, 0)])
        add(seg(str(work / f"q{i}a.png"), np.concatenate([silence(1.0), a_src, silence(0.4), beep()]), str(work / f"q{i}a")))

        n = int(it.get("countdown") or np.ceil(len(a_src) / SR * PAUSE_FACTOR + 3))
        countdown(n, lambda s: [(label, 40, GOLD, True, 40), ("INTERPRET  ·  通訳してください", 52, CYAN, True, 40),
                                (str(s), 120, WHITE, True, 0)], f"q{i}")

        a_ref = tts(it["ref"], tgt_lang, i + 1)
        card(work / f"q{i}r.png", [(label, 34, GOLD, True, 20),
                                   ("原文", 24, GREY, False, 0), (it["src"], 30, WHITE, False, 24),
                                   ("参考译文", 24, GREY, False, 0), (it["ref"], 32, CYAN, True, 24),
                                   ("要点：" + it["note"], 26, GOLD, False, 0)])
        add(seg(str(work / f"q{i}r.png"), np.concatenate([silence(0.5), a_ref, silence(2.5)]), str(work / f"q{i}r")))
        print(f"{i}/{len(items)} done", flush=True)

    if PREVIEW:
        print(f"预览卡片: {work}")
        return

    with open(work / "list.txt", "w", encoding="utf-8") as f:
        for p in parts:
            f.write(f"file '{Path(p).as_posix()}'\n")
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(work / "list.txt"), "-c", "copy", str(out)], check=True)
    shutil.rmtree(work, ignore_errors=True)  # 约 1000 个临时片段

    chap = out.with_name(out.stem + "_chapters.txt")
    chap.write_text("\n".join(chapters) + "\n", encoding="utf-8")
    guide = ""
    if spec.get("day_guide"):
        guide = "按天练习建议（用下面的章节跳到当天的部分）\n" + "\n".join(spec["day_guide"]) + "\n\n"
    desc = out.with_name(out.stem + "_description.txt")
    desc.write_text(
        f"{spec['title']}\n\n"
        f"TOBIS（ビジネス通訳検定）逐次通訳 {spec.get('part', 'Part 2 短文形式')}の練習用。\n"
        "听到提示音后在倒计时内口译，再对照参考译文。建议边做边录音，回听打分。\n\n"
        + guide +
        "※ 语音为 AI 合成（Kokoro TTS），题目为原创模拟题，与 CAIS 官方试题无关。\n\n"
        "章节 / Chapters\n" + "\n".join(chapters) + "\n",
        encoding="utf-8")
    print(f"视频: {out}\n章节: {chap}\n简介: {desc}\n总时长: {stamp(t)}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--preview"]
    PREVIEW = "--preview" in sys.argv[1:]
    if len(args) != 2:
        sys.exit("用法: python scripts/make_video.py <题目.json> <输出.mp4> [--preview]")
    spec, items = load_spec(args[0])
    build(spec, items, args[1])
