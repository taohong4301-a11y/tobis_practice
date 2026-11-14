"""TOBIS 词块 → Anki 卡组（.apkg，带日语读音和语音）

用法:
    python scripts/make_anki.py              # 生成 output/anki/TOBIS_chunks.apkg
    python scripts/make_anki.py --check      # 只检查读音和例句，不合成语音、不打包

数据: anki/chunks.tsv（手工整理的词块）+ content/*.json（自动取每个词块所在的那一题当例句）
      anki/topics.tsv（10 个 TOBIS 话题的扩充词块，没有例句）
每个词块做两张卡:
  卡1 听→意思（JA→EN）: 正面 日语 + 自动播放语音；背面 英语、读音、例句
  卡2 说出日语（EN→JA）: 正面 英语 + 英语例句；背面 日语、读音、语音、日语例句
两个子卡组:
  TOBIS 词块::1 已有素材（数字 + A 套 + B 套 + 会议定型表現）
  TOBIS 词块::2 扩充 Vol.3（出力テンプレート + C 套 + D 套 + 数字 3 + Part 3 入门）
  TOBIS 词块::3 话题扩充（topics.tsv）
新卡顺序 = ORDER（「下一次要在视频里听到的先学」），同一来源内按 chunks.tsv 的顺序。
Anki 里要把父卡组的「新卡片收集顺序 / New card gather order」设为「位置升序 / Ascending position」，
否则 Anki 会先学完 deck 1 再学 deck 2。
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

SOURCES = {
    "A": "ep01_part2_A.json", "B": "part1_B.json", "P": "phrases_01.json",
    "T": "templates_01.json", "C": "part2_C.json", "D": "part1_D.json",
    "N3": "numbers_03.json", "S": "part3_intro.json",
}
SOURCE_LABEL = {
    "N": "数字の単位", "A": "Vol.1 Part 2 A", "B": "Vol.2 Part 1 B", "P": "Vol.2 定型表現",
    "T": "Vol.3 出力テンプレート", "C": "Vol.3 Part 2 C", "D": "Vol.3 Part 1 D",
    "N3": "Vol.3 数字", "S": "Vol.3 Part 3 入門",
}
DECK1 = {"N", "A", "B", "P"}
# 第 2 周（11/16–）用 B 套和定型表現，第 3 周（11/23–）用 Vol.3；A 套第 1 周已练过，放在视频素材最后巩固；
# X = topics.tsv 的话题扩充，最后学
ORDER = ["N", "B", "P", "T", "C", "D", "N3", "S", "A", "X"]
DECK_NAMES = {1: "TOBIS 词块::1 已有素材 A·B", 2: "TOBIS 词块::2 扩充 Vol.3 C·D", 3: "TOBIS 词块::3 话题扩充"}
DECK_IDS = {1: 1731470001, 2: 1731470002, 3: 1731470003}


def deck_of(r):
    return 1 if r["src"] in DECK1 else 3 if r["src"] == "X" else 2


def label_of(r):
    if r["src"] == "X":
        return f"話題 · {r['topic']}"
    return SOURCE_LABEL[r["src"]] + (f" #{r['item']}" if r["item"] else "")
MODEL_ID = 1731470100
VOICE, SPEED = "jf_alpha", 0.9
OUT = ROOT / "output" / "anki"
AUDIO = OUT / "audio"


def load_chunks():
    rows = []
    for n, line in enumerate((ROOT / "anki" / "chunks.tsv").read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 5:
            sys.exit(f"chunks.tsv 第 {n} 行应有 5 列，实际 {len(parts)} 列: {line}")
        src, item, ja, reading, en = parts
        rows.append({"src": src, "item": int(item), "ja": ja, "reading": reading, "en": en})
    for n, line in enumerate((ROOT / "anki" / "topics.tsv").read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 4:
            sys.exit(f"topics.tsv 第 {n} 行应有 4 列，实际 {len(parts)} 列: {line}")
        topic, ja, reading, en = parts
        rows.append({"src": "X", "item": 0, "topic": topic, "ja": ja, "reading": reading, "en": en})
    return rows


def attach_examples(rows):
    data = {k: json.loads((ROOT / "content" / f).read_text(encoding="utf-8"))["items"] for k, f in SOURCES.items()}
    for r in rows:
        r["ex_ja"] = r["ex_en"] = ""
        if r["item"] and r["src"] in data:
            it = data[r["src"]][r["item"] - 1]
            ja_side = it["src"] if it["dir"] == "JA→EN" else it["ref"]
            en_side = it["ref"] if it["dir"] == "JA→EN" else it["src"]
            r["ex_ja"], r["ex_en"] = ja_side, en_side


# ---------- 读音检查：把我写的平假名和 pyopenjtalk 的读法统一成同一种片假名再比 ----------
VOWEL = {}
for row, v in zip(["アカガサザタダナハバパマヤャラワ", "イキギシジチヂニヒビピミリ", "ウクグスズツヅヌフブプムユュルッ",
                   "エケゲセゼテデネヘベペメレ", "オコゴソゾトドノホボポモヨョロヲ"], "アイウエオ"):
    for ch in row:
        VOWEL[ch] = v


def to_kata(s):
    return "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in s)


def canon(kata):
    """长音・助词・ヂヅ 的写法差异抹平，只用来比较。"""
    out = []
    for c in kata:
        if c == "ー" and out:  # セー → セイ、ソー → ソウ（和平假名写法一致）
            c = {"エ": "イ", "オ": "ウ"}.get(VOWEL.get(out[-1], ""), VOWEL.get(out[-1], ""))
        out.append(c)
    s = "".join(out)
    s = re.sub(r"([ケゲセゼテデネヘベペメレエ])イ", r"\1エ", s)  # 不重叠匹配：説明いただ 的第二个イ不动
    s = re.sub(r"([コゴソゾトドノホボポモヨョロオ])ウ", r"\1オ", s)
    return s.translate(str.maketrans({"ハ": "ワ", "ヘ": "エ", "ヲ": "オ", "ヂ": "ジ", "ヅ": "ズ"}))


def core(text):
    """去掉占位符和标点，留下可以拿去比较/朗读的部分。"""
    return re.sub(r"[〜XY、。，,？?\s]", "", text)


def has_placeholder(ja):
    return "〜" in ja or re.search(r"[XY]", ja) is not None


def check(rows):
    import pyopenjtalk
    from make_video import norm_ja
    bad_reading, not_in_example = [], []
    for r in rows:
        if r["ex_ja"] and "<b>" not in highlight(r["ex_ja"], r["ja"]):
            not_in_example.append(r)
        if has_placeholder(r["ja"]) or not re.search(r"[一-鿿]", r["ja"]):
            r["tts_ok"] = True
            continue
        mine = canon(to_kata(core(r["reading"])))
        theirs = canon(pyopenjtalk.g2p(norm_ja(core(r["ja"])), kana=True))
        r["tts_ok"] = mine == theirs
        if not r["tts_ok"]:
            bad_reading.append((r, theirs, mine))
    return bad_reading, not_in_example


# ---------- 语音 ----------
def tts_text(r):
    """有占位符的句型读例句；TTS 读法和标注读音不一致时，直接读平假名（保证读音对）。"""
    if has_placeholder(r["ja"]):
        return r["ex_ja"] or core(r["reading"]), False
    if not r.get("tts_ok", True):
        return core(r["reading"]), True
    return r["ja"], False


def make_audio(rows):
    import soundfile as sf
    from make_video import engines, norm_ja
    AUDIO.mkdir(parents=True, exist_ok=True)
    kokoro, g2p = engines()
    todo = []
    for r in rows:
        text, kana = tts_text(r)
        name = "tobis_" + hashlib.md5(f"{VOICE}|{SPEED}|{text}".encode()).hexdigest()[:12] + ".mp3"
        r["audio"] = name
        if not (AUDIO / name).exists():
            todo.append((text, kana, AUDIO / name))
    print(f"语音: {len(rows)} 条，其中 {len(todo)} 条需要新合成")
    with tempfile.TemporaryDirectory() as tmp:
        for i, (text, kana, path) in enumerate(todo, 1):
            r = g2p(text if kana else norm_ja(text))
            ph = r[0] if isinstance(r, tuple) else r
            samples, sr = kokoro.create(ph, voice=VOICE, speed=SPEED, is_phonemes=True)
            wav = Path(tmp) / "a.wav"
            sf.write(wav, samples, sr)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-ac", "1", "-b:a", "64k", str(path)],
                           check=True)
            if i % 50 == 0:
                print(f"  {i}/{len(todo)}")


# ---------- 卡组 ----------
CSS = """
.card { font-family: "Yu Gothic UI", "Hiragino Sans", "Noto Sans CJK JP", sans-serif; font-size: 22px;
        text-align: center; color: #1d2433; background: #fbfaf7; line-height: 1.5; }
.nightMode.card, .night_mode .card { color: #e8e6e1; background: #1e2128; }
.tag { font-size: 13px; color: #8a8f99; letter-spacing: .05em; }
.ja { font-size: 34px; font-weight: 600; margin: 14px 0 4px; }
.en { font-size: 28px; font-weight: 600; margin: 14px 0 4px; }
.reading { font-size: 20px; color: #3f7fbf; }
.prompt { font-size: 14px; color: #8a8f99; margin-top: 10px; }
.ex { font-size: 17px; text-align: left; max-width: 640px; margin: 14px auto 0; padding: 10px 14px;
      border-left: 3px solid #d9b45a; background: rgba(217,180,90,.08); }
.ex .exen { color: #6b7180; margin-top: 4px; }
.ex b { color: #b5651d; }
.nightMode .ex b, .night_mode .ex b { color: #f0b860; }
.nightMode .reading, .night_mode .reading { color: #7fb3e6; }
"""

LISTEN_FRONT = """<div class="tag">{{Source}} · 聞く → 意味</div>
<div class="ja">{{Japanese}}</div>{{Audio}}
<div class="prompt">意味を英語で言う / Say it in English</div>"""
LISTEN_BACK = """{{FrontSide}}<hr id="answer">
<div class="en">{{English}}</div><div class="reading">{{Reading}}</div>
{{#ExampleJA}}<div class="ex"><div>{{ExampleJA}}</div><div class="exen">{{ExampleEN}}</div></div>{{/ExampleJA}}"""
SPEAK_FRONT = """<div class="tag">{{Source}} · 英 → 日（声に出す）</div>
<div class="en">{{English}}</div>
{{#ExampleEN}}<div class="ex"><div class="exen">{{ExampleEN}}</div></div>{{/ExampleEN}}
<div class="prompt">日本語で言う / Say it in Japanese</div>"""
SPEAK_BACK = """{{FrontSide}}<hr id="answer">
<div class="ja">{{Japanese}}</div><div class="reading">{{Reading}}</div>{{Audio}}
{{#ExampleJA}}<div class="ex"><div>{{ExampleJA}}</div></div>{{/ExampleJA}}"""


def highlight(sentence, ja):
    """例句里把词块（去掉〜后最长的一段）标粗。"""
    pieces = sorted((p for p in re.split(r"[〜XY、。]", ja) if len(p) >= 2), key=len, reverse=True)
    for p in pieces:
        p = p.lstrip("をにがはでのへと")  # 〜を開設する → 開設する
        # 动词变位：示唆する → 示唆しました，所以从词尾逐字缩短再找
        while len(p) >= 2:
            if p in sentence:
                return sentence.replace(p, f"<b>{p}</b>", 1)
            if not re.search(r"[ぁ-ゖ]$", p):
                break
            p = p[:-1]
    return sentence


def build(rows):
    import genanki
    model = genanki.Model(
        MODEL_ID, "TOBIS 词块（双向）",
        fields=[{"name": n} for n in ["Japanese", "Reading", "English", "ExampleJA", "ExampleEN", "Audio", "Source", "Key"]],
        templates=[
            {"name": "1 聞く→意味 JA→EN", "qfmt": LISTEN_FRONT, "afmt": LISTEN_BACK},
            {"name": "2 英→日 EN→JA", "qfmt": SPEAK_FRONT, "afmt": SPEAK_BACK},
        ],
        css=CSS, sort_field_index=7,
    )
    decks = {k: genanki.Deck(DECK_IDS[k], v) for k, v in DECK_NAMES.items()}
    media = []
    for pos, r in enumerate(rows, 1):
        key = f"{r['src']}-{r['item']:02d}-{r['ja']}"
        note = genanki.Note(
            model=model,
            fields=[r["ja"], r["reading"], r["en"], highlight(r["ex_ja"], r["ja"]), r["ex_en"],
                    f"[sound:{r['audio']}]", label_of(r), key],
            guid=genanki.guid_for("tobis-chunk", key),
            tags=[f"tobis::{r['src']}", f"tobis::deck{deck_of(r)}"]
                 + ([f"tobis::topic::{r['topic'].replace(' ', '_')}"] if r["src"] == "X" else []),
            due=pos,
        )
        decks[deck_of(r)].add_note(note)
        media.append(str(AUDIO / r["audio"]))
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "TOBIS_chunks.apkg"
    genanki.Package(list(decks.values()), media_files=sorted(set(media))).write_to_file(str(path))
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只检查读音和例句")
    args = ap.parse_args()
    rows = sorted(load_chunks(), key=lambda r: ORDER.index(r["src"]))  # sorted 是稳定排序
    attach_examples(rows)
    dupes = {r["ja"] for r in rows if sum(x["ja"] == r["ja"] for x in rows) > 1}
    if dupes:
        print("重复的词块:", "、".join(sorted(dupes)))
    bad, missing = check(rows)
    per = {k: sum(deck_of(r) == k for r in rows) for k in DECK_NAMES}
    print(f"词块 {len(rows)} 个（" + "，".join(f"deck {k}: {v}" for k, v in per.items()) + f"）→ 卡片 {2 * len(rows)} 张")
    print(f"\n标注读音 ≠ TTS 读法（共 {len(bad)} 个；语音会改读平假名，请确认标注读音是对的）:")
    for r, theirs, mine in bad:
        print(f"  {r['src']}{r['item']:>3}  {r['ja']}  标注={mine}  TTS={theirs}")
    print(f"\n词块不在例句里（共 {len(missing)} 个，例句仍会显示，只是不会标粗）:")
    for r in missing:
        print(f"  {r['src']}{r['item']:>3}  {r['ja']}  ←  {r['ex_ja'][:50]}")
    if args.check:
        return
    make_audio(rows)
    print("已生成:", build(rows))


if __name__ == "__main__":
    main()
