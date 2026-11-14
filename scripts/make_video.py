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
import time
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
    # 小数点后逐位读：0.25 → れい点にご（不读 にじゅうご），14.2 → 14点に
    t = re.sub(r"(\d)\.(\d+)", lambda m: m.group(1) + "点" + "".join(DIGIT_KANA[c] for c in m.group(2)), t)
    t = re.sub(r"(?<!\d)0点", "れい点", t)  # 0.5 → れいてんご（不读 ゼロてんご）
    for k, v in READING_FIXES.items():
        t = t.replace(k, v)
    # 单独的「月末」读 げつまつ（否则 つきまつ）；3月末・今月末・来月末 pyopenjtalk 本来就读对，不能动
    t = re.sub(r"(?<![\d今来先毎])月末", "げつまつ", t)
    return t.replace("%", "パーセント").replace("〜", "から")


DIGIT_KANA = dict(zip("0123456789", ["ゼロ", "いち", "に", "さん", "よん", "ご", "ろく", "なな", "はち", "きゅう"]))

# TTS 读错的词：原文 → 只给语音用的写法（画面上不变）
READING_FIXES = {
    "株買い": "株がい",          # 自社株買い：pyopenjtalk 读成 かぶかい
    "設備投資": "設備とうし",    # 读成 せつびとおし
    "FinOps": "フィンオプス",     # 否则逐字母读
    "7〜9月期": "7月から9月期",  # 否则读成 なな から くがつき
    "間を取って": "あいだを取って",  # 否则读成 まをとって
    "対50": "たい50",            # 50対50：否则读成 ごじゅうつい…
}


def tts(text, lang, idx, voice=None, speed=None):
    """voice 不指定时按题号轮换；对话题按说话人固定声音。speed 不指定时用 TOBIS_SPEED。"""
    if PREVIEW:
        return silence(1.5)
    kokoro, g2p = engines()
    speed = speed or SPEED
    if lang == "ja":
        r = g2p(norm_ja(text))
        ph = r[0] if isinstance(r, tuple) else r
        s, _ = kokoro.create(ph, voice=voice or JA_VOICES[idx % len(JA_VOICES)], speed=speed, is_phonemes=True)
    else:
        voice = voice or EN_VOICES[idx % len(EN_VOICES)]
        s, _ = kokoro.create(text, voice=voice, speed=speed, lang="en-gb" if voice.startswith("b") else "en-us")
    return s.astype(np.float32)


NO_LINE_START = set("）)」』】〕、。，．・：；！？ー…ぁぃぅぇぉっゃゅょァィゥェォッャュョ%")


def fit_size(text, bold, size, maxw, minimum=34):
    """标题太长时缩小字号，尽量一行放下。"""
    d = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    while size > minimum and text_len(d, text, bold, size) > maxw:
        size -= 2
    return size


def wrap(draw, text, bold, size, maxw):
    # \u82f1\u6587\u5355\u8bcd\uff08\u542b\u6570\u5b57\u3001\u6807\u70b9\uff09\u6574\u4f53\u4e0d\u62c6\uff1b\u65e5\u6587/\u7b26\u53f7\u9010\u5b57\u53ef\u65ad\u3002\u65e5\u82f1\u6df7\u6392\u65f6\u82f1\u6587\u4e0d\u4f1a\u88ab\u62c6\u6210 ris / e
    tokens = re.findall(r"[A-Za-z0-9.,:;'\u2019!?%$&()/\-\u2013+=\u00d7\u00f7<>\u2192]+\s*|\s+|.", text)
    lines, cur = [], ""
    for tok in tokens:
        # 禁则：）」、。等不放在行首，宁可让上一行略超出一点
        if text_len(draw, cur + tok, bold, size) > maxw and cur and tok[0] not in NO_LINE_START:
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
    # -threads 2：静态图片不需要多线程，少占内存（内存紧张时 libx264 会报 Generic error）
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", img, "-i", f"{out}.wav",
           "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-pix_fmt", "yuv420p", "-threads", "2",
           "-r", "24", "-c:a", "aac", "-b:a", "128k", "-t", f"{len(audio) / SR:.3f}", f"{out}.mp4"]
    waits = [5, 20, 60]  # 失败后等一会儿再试（内存或文件被占用通常是暂时的），免得 30 分钟的渲染白跑
    for attempt in range(len(waits) + 1):
        if subprocess.run(cmd).returncode == 0:
            break
        if attempt == len(waits):
            sys.exit(f"ffmpeg 连续 {attempt + 1} 次失败: {out}")
        print(f"ffmpeg 失败，{waits[attempt]} 秒后重试（{attempt + 1}/{len(waits)}）: {out}", flush=True)
        time.sleep(waits[attempt])
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


def with_dialogue(it, data):
    """对话题（有 "dialogue" 字段）：挂上场景名、说话人和对方的信息，并检查说话人语言和方向一致。"""
    if "dialogue" not in it:
        return it
    meta = data["dialogues"][it["dialogue"]]
    speakers = meta["speakers"]
    me = speakers[it["speaker"]]
    other = next(sp for sid, sp in speakers.items() if sid != it["speaker"])
    if me["lang"] != ("en" if it["dir"] == "EN→JA" else "ja"):
        sys.exit(f"说话人语言和方向不一致：{it['dialogue']} {it['speaker']} {it['src'][:30]}")
    return dict(it, _scene=meta["scene"], _speakers=speakers, _me=me, _other=other)


def load_spec(path):
    """单个题目文件，或带 "sources" 的合集文件（把多个题目文件按顺序拼起来）。"""
    path = Path(path)
    spec = json.load(open(path, encoding="utf-8"))
    if "sources" not in spec:
        return spec, [with_dialogue(dict(it, _prefix=""), spec) for it in spec["items"]]
    items = []
    for src in spec["sources"]:
        sub = json.load(open(path.parent / src["file"], encoding="utf-8"))
        chapters = src.get("chapters", {})
        first, last = src.get("range", [1, len(sub["items"])])  # 可选：只取第 first–last 题（从 1 起）
        for j, it in enumerate(sub["items"], 1):
            if not first <= j <= last:
                continue
            it = with_dialogue(dict(it, _prefix=src.get("label", "")), sub)
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
    parts, chapters, t = [], ["0:00 オープニング / Intro"], 0.0
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

    summary = spec.get("summary", [])  # 可选：内容概要（日文、英文各一段），显示在开头卡和简介里
    mode = spec.get("mode", "practice")  # practice（默认）/ shadow（跟读）/ exam（模考，待实现）
    if mode == "shadow":
        how = ("① ゆっくり聞く → ② 声に出してくり返す → ③ 音声に重ねて読む（シャドーイング）",
               "Listen (slow) → repeat aloud → shadow along at normal speed.")
    else:
        how = ("合図音のあと、カウントダウン中に通訳し、答えを確認してください。",
               "Listen → beep → interpret during the countdown → check the answer.")
    card(work / "intro.png", [(spec["title"], 44 if not summary else 38, WHITE, True, 24)]
         + [(s, 26, CYAN, False, 10) for s in summary] + ([("", 10, GREY, False, 10)] if summary else [])
         + [(how[0], 30 if not summary else 26, GREY, False, 10),
            (how[1], 26 if not summary else 22, GREY, False, 10),
            ("音声は AI 合成、問題はオリジナルの模擬問題です。 / AI-generated voice; original practice questions.", 22, GREY, False, 0)])
    add(seg(str(work / "intro.png"), silence(10 if summary else 5), str(work / "p00")))

    if spec.get("day_guide"):
        card(work / "guide.png", [("日ごとの練習プラン · Daily plan", 38, GOLD, True, 10),
                                  ("チャプターで当日の部分へ移動 / Use the chapters to jump to your day", 24, GREY, False, 24),
                                  ("\n".join(spec["day_guide"]), 26, WHITE, False, 0)])
        add(seg(str(work / "guide.png"), silence(10), str(work / "p01")))

    counters, turns = {}, {}
    turn_totals = {}
    for it in items:
        if "_scene" in it:
            dk = it["_prefix"] + it["dialogue"]
            turn_totals[dk] = turn_totals.get(dk, 0) + 1

    for i, it in enumerate(items, 1):
        key = (it["_prefix"], it["dir"])
        counters[key] = counters.get(key, 0) + 1
        num = it.get("num", counters[key])
        label = f"{it['_prefix']}Q{num}  {it['dir'] if it['dir'] != 'SYMBOL' else 'Symbol'}  {it.get('tag', '')}".strip()
        scene = it.get("_scene")
        who = ""
        if scene:  # 对话：标签写「会話1 · 3/10  EN→JA · Mark Davis」
            dk = it["_prefix"] + it["dialogue"]
            turns[dk] = turns.get(dk, 0) + 1
            who = it["_me"]["name"].split(" · ")[0]
            label = f"{scene.split(' ')[0]} · {turns[dk]}/{turn_totals[dk]}  {it['dir']} · {who}"
        starts_dialogue = bool(scene) and turns[dk] == 1

        if "chapter" in it:
            chapters.append(f"{stamp(t)} {it['chapter']}")
        elif not use_chapters:
            chapters.append(f"{stamp(t)} {label if scene else it['_prefix'] + 'Q' + str(num) + ' ' + it['dir']}")
        if "chapter" in it or starts_dialogue:
            title = it.get("chapter") or scene
            blocks = [(title, fit_size(title, True, 48, W - 160), GOLD, True, 30)]
            if starts_dialogue:  # 场景卡：列出两位说话人
                for sid, sp in it["_speakers"].items():
                    lang = "English" if sp["lang"] == "en" else "日本語"
                    blocks.append((f"{sid}  {sp['name']}（{lang}）", 28, WHITE, False, 14))
            else:
                blocks.append(("セクション開始 · Section start", 26, GREY, False, 0))
            card(work / f"ch{i}.png", blocks)
            add(seg(str(work / f"ch{i}.png"), silence(6 if starts_dialogue else 3), str(work / f"ch{i}")))

        if PREVIEW and key in seen and "chapter" not in it:
            continue
        seen.add(key)

        if mode == "shadow":  # 跟读：只用日语那一句 ① 慢速听 → ② 停顿跟读 → ③ 正常速度重叠跟读
            ja, en = (it["src"], it["ref"]) if it["dir"] == "JA→EN" else (it["ref"], it["src"])
            voice = None
            sh_label = f"{it['_prefix']}{num}"
            if scene:  # 对话里的日语句子用日语说话人的声音（原话或口译示范）
                ja_sp = it["_me"] if it["dir"] == "JA→EN" else it["_other"]
                voice = ja_sp["voice"]
                sh_label = (f"{scene.split(' ')[0]} · {turns[dk]}/{turn_totals[dk]} · "
                            + (who if it["dir"] == "JA→EN" else "通訳例 / interpretation"))
            a_slow = tts(ja, "ja", i, voice=voice, speed=0.8)
            a_norm = tts(ja, "ja", i, voice=voice)

            def sh_blocks(step):
                b = [(sh_label, 32, GOLD, True, 16), (step, 30, CYAN, True, 24),
                     (ja, 40, WHITE, True, 20), (en, 24, GREY, False, 16)]
                if it.get("note"):
                    b.append(("ポイント · Notes：" + it["note"], 22, GOLD, False, 0))
                return b

            card(work / f"q{i}a.png", sh_blocks("① 聞く · Listen"))
            add(seg(str(work / f"q{i}a.png"), np.concatenate([silence(0.8), a_slow, silence(0.6)]), str(work / f"q{i}a")))
            card(work / f"q{i}b.png", sh_blocks("② くり返す · Repeat"))
            add(seg(str(work / f"q{i}b.png"), silence(len(a_norm) / SR * 1.3 + 1.5), str(work / f"q{i}b")))
            card(work / f"q{i}c.png", sh_blocks("③ 重ねて読む · Shadow"))
            add(seg(str(work / f"q{i}c.png"), np.concatenate([silence(0.6), a_norm, silence(1.5)]), str(work / f"q{i}c")))
            print(f"{i}/{len(items)} done", flush=True)
            continue

        if it["dir"] == "SYMBOL":
            card(work / f"q{i}a.png", [(label, 40, GOLD, True, 40),
                                       ("ノート記号を書いてください  ·  Write the symbol", 44, WHITE, True, 40),
                                       (it["src"], 64, CYAN, True, 0)])
            add(seg(str(work / f"q{i}a.png"), silence(2.0), str(work / f"q{i}a")))
            countdown(int(it.get("countdown", 4)),
                      lambda s: [(label, 40, GOLD, True, 40), (it["src"], 52, CYAN, True, 40),
                                 (str(s), 120, WHITE, True, 0)], f"q{i}")
            blocks = [(label, 34, GOLD, True, 20), ("意味 · Meaning", 24, GREY, False, 0), (it["src"], 40, WHITE, False, 24),
                      ("記号 · Symbol", 24, GREY, False, 0), (it["ref"], 150, CYAN, True, 24)]
            if it.get("note"):
                blocks.append(("ポイント · Notes：" + it["note"], 26, GOLD, False, 0))
            card(work / f"q{i}r.png", blocks)
            add(seg(str(work / f"q{i}r.png"), silence(3.0), str(work / f"q{i}r")))
            print(f"{i}/{len(items)} done", flush=True)
            continue

        src_lang = "en" if it["dir"] == "EN→JA" else "ja"
        tgt_lang = "ja" if src_lang == "en" else "en"
        # 对话：原文用说话人本人的声音，参考译文用对方（另一种语言）的声音
        a_src = tts(it["src"], src_lang, i, voice=it["_me"]["voice"] if scene else None)
        card(work / f"q{i}a.png", [(label, 40, GOLD, True, 40), ("LISTEN  ·  聞いてください", 56, WHITE, True, 0)])
        add(seg(str(work / f"q{i}a.png"), np.concatenate([silence(1.0), a_src, silence(0.4), beep()]), str(work / f"q{i}a")))

        n = int(it.get("countdown") or np.ceil(len(a_src) / SR * PAUSE_FACTOR + 3))
        countdown(n, lambda s: [(label, 40, GOLD, True, 40), ("INTERPRET  ·  通訳してください", 52, CYAN, True, 40),
                                (str(s), 120, WHITE, True, 0)], f"q{i}")

        a_ref = tts(it["ref"], tgt_lang, i + 1, voice=it["_other"]["voice"] if scene else None)
        src_head = f"原文 · Source（{who}）" if scene else "原文 · Source"
        card(work / f"q{i}r.png", [(label, 34, GOLD, True, 20),
                                   (src_head, 24, GREY, False, 0), (it["src"], 30, WHITE, False, 24),
                                   ("参考訳 · Reference", 24, GREY, False, 0), (it["ref"], 32, CYAN, True, 24),
                                   ("ポイント · Notes：" + it["note"], 26, GOLD, False, 0)])
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
        guide = ("日ごとの練習プラン / Daily plan（チャプターで当日の部分へ / jump with the chapters）\n"
                 + "\n".join(spec["day_guide"]) + "\n\n")
    desc = out.with_name(out.stem + "_description.txt")
    desc.write_text(
        f"{spec['title']}\n\n"
        + (f"{spec['series']}\n\n" if spec.get("series") else "")
        + "".join(s + "\n" for s in summary) + ("\n" if summary else "") +
        f"TOBIS（ビジネス通訳検定）逐次通訳 {spec.get('part', 'Part 2 短文形式')}の練習用です。\n"
        f"Practice for the TOBIS business interpreting test (consecutive, {spec.get('part', 'Part 2')}).\n\n"
        + ("各文を ① ゆっくり聞く → ② 声に出してくり返す → ③ 音声に重ねて読む、の3ステップで練習します。画面の日本語を見ながらで大丈夫です。\n"
           "Each sentence: listen at slow speed → repeat aloud → shadow along at normal speed. It's fine to read the text on screen.\n\n"
           if mode == "shadow" else
           "合図音のあと、カウントダウン中に通訳し、参考訳と比べてください。録音して聞き直すのがおすすめです。\n"
           "After the beep, interpret during the countdown, then compare with the reference. Record yourself and review.\n\n")
        + guide +
        "※ 音声は AI 合成（Kokoro TTS）です。問題はオリジナルの模擬問題で、CAIS の公式試験問題とは関係ありません。\n"
        "※ AI-generated voice (Kokoro TTS). Original practice questions, not affiliated with CAIS.\n\n"
        "チャプター / Chapters\n" + "\n".join(chapters) + "\n",
        encoding="utf-8")
    print(f"视频: {out}\n章节: {chap}\n简介: {desc}\n总时长: {stamp(t)}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--preview"]
    PREVIEW = "--preview" in sys.argv[1:]
    if len(args) != 2:
        sys.exit("用法: python scripts/make_video.py <题目.json> <输出.mp4> [--preview]")
    spec, items = load_spec(args[0])
    build(spec, items, args[1])
