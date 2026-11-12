"""把题目 JSON 转成每日计划里的附录表格（Markdown），保证计划文档和视频用的是同一份题目。

用法:
    python scripts/make_appendix.py content/w2_part1_B.json      # 打印到终端
    python scripts/make_appendix.py content/w2_numbers.json --numbers
"""
import json
import sys


def cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def dialogue_tables(d):
    out = []
    for key, meta in d["dialogues"].items():
        out.append(f"### {meta['scene']}\n")
        for sid, sp in meta["speakers"].items():
            out.append(f"- **{sid}**：{sp['name']}（{'English' if sp['lang'] == 'en' else '日本語'}）")
        out.append("\n| # | 话者 | 方向 | 原文 | 参考译文 | 要点 |\n| --- | --- | --- | --- | --- | --- |")
        n = 0
        for it in d["items"]:
            if it["dialogue"] != key:
                continue
            n += 1
            out.append(f"| {n} | {it['speaker']} | {it['dir']} | {cell(it['src'])} | {cell(it['ref'])} | {cell(it['note'])} |")
        out.append("")
    return "\n".join(out)


def item_tables(d, short=False):
    out = []
    for direction in ("EN→JA", "JA→EN"):
        rows = [it for it in d["items"] if it["dir"] == direction]
        if not rows:
            continue
        head = "英→日" if direction == "EN→JA" else "日→英"
        out.append(f"**{head}**\n")
        if short:
            out.append("| # | 原文 | 答案 | 要点 |\n| --- | --- | --- | --- |")
        else:
            out.append("| # | 原文 | 参考译文 | 要点 |\n| --- | --- | --- | --- |")
        for n, it in enumerate(rows, 1):
            out.append(f"| {n} | {cell(it['src'])} | {cell(it['ref'])} | {cell(it['note'])} |")
        out.append("")
    return "\n".join(out)


def render(path, numbers=False):
    d = json.load(open(path, encoding="utf-8"))
    return dialogue_tables(d) if "dialogues" in d else item_tables(d, short=numbers)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        sys.exit("用法: python scripts/make_appendix.py <题目.json> [--numbers]")
    sys.stdout.reconfigure(encoding="utf-8")
    print(render(args[0], numbers="--numbers" in sys.argv))
