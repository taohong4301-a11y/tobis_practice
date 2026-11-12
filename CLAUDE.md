# TOBIS 口译练习视频系列 · 项目说明（给 Claude Code 读）

## 这是什么

Ellen 的个人项目：每周生成一期「TOBIS（ビジネス通訳検定）英日双向口译练习视频」，上传到 B站 和 YouTube。
同时也是她自己备考 TOBIS（第35回，2026/12/13）和 JTF ほんやく検定（第86回，2027/1/23）的训练材料。

视频每题的流程模拟 TOBIS 逐次通訳試験：
1. 题号卡 + 原文语音（不显示文字）
2. 提示音 → 倒计时（观众开口口译，时长 = 原文时长 × 1.6 + 3 秒）
3. 显示原文 / 参考译文 / 要点，同时播放参考译文语音作为示范

## TOBIS 考试要点（出题必须遵守）

- 逐次通訳試験约 60 分钟，录音作答：耳机听音频，对麦克风口译。
- Part 1 会話形式（英日混合对话）· Part 2 短文形式（1～数句，英→日、日→英）· Part 3 スピーチ形式。
- Part 1–2 判定 3 级 / 4 级 / 不合格；达到 3 级才用 Part 3 判 2 级。
- 官方 Part 2 出题例的特征：1–3 句、大数字多（億・兆 ↔ billion/trillion）、每个方向最后 3 题是同一话题的连续内容；题材 = 公司业绩、金融市场、人事制度、社会新闻、产业。
- 官方样题有版权：只能参考格式，**绝不把 CAIS 原题做进视频**。

## 目录结构

```
tobis-practice/
├── CLAUDE.md                 # 本文件
├── requirements.txt
├── scripts/
│   ├── make_video.py         # JSON → 视频 + 章节时间戳 + 简介模板
│   ├── upload_youtube.py     # 视频 + 简介 → 上传到 YouTube（私享）
│   └── download_models.sh    # 下载 Kokoro 语音模型
├── docs/
│   └── TOBIS_W1_每日计划.md   # 第1周每日计划（附录 A/B/C 是视频题目的来源）
├── content/
│   ├── ep01_part2_A.json     # 第1期：Part 2 A 套 40 题（= 每日计划 附录 A）
│   ├── w1_numbers.json       # 第1周 数字热身 20 题（= 附录 B）
│   ├── w1_symbols.json       # 第1周 笔记符号 30 个（= 附录 C）
│   └── ep01_w1_full.json     # 第1周完整版合集：数字 + A套 + 符号，带按天章节
├── models/                   # 模型文件（gitignore）
└── output/                   # 生成的视频（gitignore）
```

## 环境搭建（第一次）

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
brew install ffmpeg            # macOS；Windows 用 winget install ffmpeg
bash scripts/download_models.sh
python scripts/make_video.py content/ep01_part2_A.json output/ep01.mp4
```

Windows：kokoro-onnx 需要 Python 3.10–3.12，用 `py -3.12` 或 pyenv 的 3.12 建 venv（Anaconda 的 3.9 太旧）；用 `.venv\Scripts\activate`。

字体：主字体自动找 macOS 的ヒラギノ、Windows 的游ゴシック/メイリオ、Linux 的 Noto CJK。都找不到时设置 `TOBIS_FONT` 和 `TOBIS_FONT_BOLD`。
主字体缺的字（游ゴシック没有简体字 译/练/时 等）逐字改用后备字体（Windows 微软雅黑、macOS 苹方），可用 `TOBIS_FONT_FALLBACK(_BOLD)` 覆盖。
不装语音模型也能先看画面：加 `--preview`，只把每种题的卡片画到 `output/<名字>_preview/`。
可调参数（环境变量）：`TOBIS_SPEED`（语速，默认 0.95）、`TOBIS_PAUSE`（倒计时系数，默认 1.6）。

## 题目 JSON 格式

```json
{
  "episode": 2,
  "week": "2026-W47",
  "part": "Part 2 短文形式",
  "set": "B",
  "title": "TOBIS 商务口译短句训练 第2期 · 英日双向40题",
  "items": [
    {"dir": "EN→JA", "src": "英文原文", "ref": "日文参考译文", "note": "要点（难词读音、数字换算）", "tag": ""},
    {"dir": "JA→EN", "src": "日文原文", "ref": "English reference", "note": "要点", "tag": "连续 1/3"}
  ]
}
```

- `dir` 只能是 `EN→JA` 或 `JA→EN`。
- `note` 里的日语难词要带读音，例：`削減（さくげん）`；数字给换算，例：`342 billion = 3,420億`。
- `tag` 用于连续题：`连续 1/3`、`连续 2/3`、`连续 3/3`，其余留空。
- 每期 40 题：英→日 20 + 日→英 20，各含 2 组连续题（第 11–13、18–20 题）。
- 题号按「方向」分别从 1 数起（和每日计划里的编号一致）；可选 `countdown`（秒）覆盖默认倒计时。
- `dir` 为 `SYMBOL` 时是笔记符号题：`src` = 意思，`ref` = 符号，没有语音，倒计时让观众写符号。

### 合集文件（一个视频里放多套题，观众按章节自己选当天的部分）

```json
{
  "title": "...", "part": "Part 2 短文形式",
  "sources": [
    {"file": "w1_numbers.json", "label": "数字 ", "countdown": 4,
     "chapters": {"1": "数字热身 · 英→日 1–10（Day 1）", "11": "数字热身 · 日→英 1–10（Day 2）"}}
  ],
  "day_guide": ["Day 1：……", "Day 2：……"]
}
```

- `sources` 按顺序拼接；`chapters` 的键是该文件里第几题（从 1 起），在那一题前插入章节标题卡并记 YouTube 章节。
- 有章节时只输出章节级时间戳（不再每题一个）；`day_guide` 会做成开头的「按天练习建议」卡，并写进简介。
- 每周的视频建议做成这种完整版：一次生成全部内容，用 Day 1/2/3… 标注，不写具体日期。

## 每周工作流

1. **出题**：按上面的格式和 TOBIS 出题特征生成新一期 JSON，存为 `content/epNN_<part>_<set>.json`。题材轮换：金融市场 / 企业业绩 / IT·数据 / 人事·劳动 / 能源·ESG / 制造·供应链 / 日常商务用语。每期至少 10 题含大数字。
2. **校对**：检查参考译文准确、数字换算正确、日语读音正确。
3. **生成**：`python scripts/make_video.py content/epNN_....json output/epNN.mp4`
4. **抽查**：至少听 5 题，重点检查日语 TTS 有没有读错汉字和数字。读错的地方：在 `make_video.py` 的 `READING_FIXES` 里加一条（原文 → 语音用写法）。
5. **上传**：
   - YouTube：`python scripts/upload_youtube.py output/epNN.mp4`（先加 `--dry-run` 看一眼）。自动填标题、简介（含章节）、标签，并标注 AI 合成内容；上传为私享。**API 项目通过 YouTube 审核之前，这样上传的视频会被锁成私享、可能无法改公开**——在那之前 YouTube 也手动上传（拖进 YouTube Studio，简介粘贴 `_description.txt`）。
   - B站：手动上传，用 `_description.txt` 作简介，并勾选「AI 生成内容」。B站没有给个人的官方上传 API，不要用基于登录 Cookie 的第三方工具。

## 上传到 YouTube（准备只做一次）

1. 打开 https://console.cloud.google.com/ ，新建项目（例如 tobis-uploader）。
2. 「API とサービス / APIs & Services」→ 启用 **YouTube Data API v3**。
3. 「OAuth 同意画面 / OAuth consent screen」：User type 选 External，填应用名和自己的邮箱；在 Test users 里加上自己的 Google 账号。
4. 「認証情報 / Credentials」→ 创建 OAuth クライアント ID，类型选 **Desktop app**，下载 JSON，改名为 `client_secret.json` 放到项目根目录。
5. 第一次运行上传脚本时会打开浏览器，用 YouTube 频道所在的账号登录并允许。授权保存在 `.youtube_token.json`。

- `client_secret*.json` 和 `.youtube_token.json` 已 gitignore，**绝不提交**。
- **最大的限制**：2020-07-28 之后建的 API 项目，在通过 YouTube API 审核（audit）之前，用 API 上传的视频会被锁成私享（Studio 里显示 "locked as private"），开发者反映**无法改成公开**。
  - 第一次先用 1 分钟的测试视频上传，确认是否被锁；被锁就删掉测试视频。
  - 解除方法：提交 Google 的「YouTube API Services – Audit and Quota Extension Form」，说明用途（个人频道每周上传 1 个自制教学视频）；可能要求提供隐私政策页面。审核通过前，YouTube 也手动上传。
  - 审核结果（是否已通过、哪天提交）记在这里：_尚未提交_
- 配额：每天默认 10,000 单位，一次上传约 1,600，每周 1 个视频足够。
- OAuth 同意画面处于「测试」状态时，授权大约 7 天过期；脚本会自动重新打开浏览器让你再授权一次。

## 已知问题与经验

- 日语 TTS 用 misaki 的 `JAG2P(version="pyopenjtalk")` → Kokoro。不用默认的 cutlet 模式（要 fugashi + 约 770MB 的 unidic 词典）；`pyopenjtalk-plus` 在 Windows/macOS 有预编译包（原版 pyopenjtalk 在 Windows 要 cmake 编译，会装失败）。
- `norm_ja()` 已处理：千分位逗号、小数点（8.5 → 8点5）、% → パーセント、〜 → から；读错的词写进 `READING_FIXES`（只改语音，画面不变）。已收录：自社株買い、設備投資、FinOps、7〜9月期。
- 抽查读音最快的方法：对所有日语句子跑 `pyopenjtalk.g2p(norm_ja(text), kana=True)`，看片假名，不用一题题听。
- Windows 上 winget 装的 ffmpeg 要开新终端才在 PATH 里。
- 日语声音偶尔会读错多音汉字，上传前必须抽查。
- 英语声音在美式和英式之间轮换，日语在女声 jf_alpha 和男声 jm_kumo 之间轮换。
- 40 题一期约 25–30 分钟，生成耗时约 10–15 分钟（CPU）。

## 待办（按优先级）

1. 生成第 1 期完整视频并抽查（content/ep01_part2_A.json 已就绪）。
2. 第 2 期：Part 2 B 套 40 题（新题材，难度略升）。
3. 新增 Part 1 模式：英日混合对话，一个人说英语、一个人说日语，每轮之后倒计时。JSON 增加 `speaker` 字段。
4. 新增 Part 3 模式：60–90 秒演讲，分 2–3 段播放。
5. 生成 SRT 字幕文件（只在答案阶段显示）；自动生成封面图（1280×720，期数 + 主题）。
6. 可选：接入商用 TTS（Azure / Google，用 Ellen 自己的 API key）作为第二种语音引擎，提高日语自然度。

## 备考时间线（供出题节奏参考）

- 11/9–11/15 第 1 周 Part 2 短文 · 11/16–22 Part 1 对话 · 11/23–29 Part 3 演讲 + 数字 · 11/30–12/6 全真模考 · 12/7–12/13 考试周
- 12/14 起转入 JTF 笔译冲刺（领域：金融・証券，备选 情報処理）
