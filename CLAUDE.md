# TOBIS 口译练习视频系列 · 项目说明（给 Claude Code 读）

## 这是什么

Ellen 的个人项目：每周生成一期「TOBIS（ビジネス通訳検定）英日双向口译练习视频」，上传到 B站 和 YouTube。
同时也是她自己备考 TOBIS（第35回，2026/12/13）和 JTF ほんやく検定（第86回，2027/1/23）的训练材料。

视频每题的流程模拟 TOBIS 逐次通訳試験：
1. 题号卡 + 原文语音（不显示文字）
2. 提示音 → 倒计时（观众开口口译，时长 = 原文时长 × 1.6 + 3 秒）
3. 显示原文 / 参考译文 / 要点，同时播放参考译文语音作为示范

**视频语言规则：视频里出现的所有文字（卡片、章节、简介、标题、题目要点）只用日语＋英语对照，不出现中文。** 只有这份 CLAUDE.md、每日计划和终端提示用中文。

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
│   ├── TOBIS_W1_每日计划.md   # 第1周每日计划（附录 A/B/C 是视频题目的来源）
│   ├── TOBIS_冲刺总计划.md     # ★ 总计划：目标 3 級、只靠 Part 1・2、每天 2 小时、制作时间表
│   ├── TOBIS_W2_每日计划.md   # 第2周 11/16–22 基础周（附录由 make_appendix.py 从 JSON 生成）
│   ├── TOBIS_W3_每日计划.md   # 第3周 11/23–29 强化周（Vol.3 题目待写）
│   ├── TOBIS_W4_每日计划.md   # 第4周 11/30–12/6 模考周
│   ├── TOBIS_冲刺周_每日计划.md # 12/7–12/12 考前冲刺 + 考试当天策略卡
│   └── 视频设计_对话模式.md    # Part 1 对话模式的视频设计（Vol.2 起，待审）
├── content/
│   ├── ep01_part2_A.json     # 第1期：Part 2 A 套 40 题（= 每日计划 附录 A）
│   ├── w1_numbers.json       # 第1周 数字热身 20 题（= 附录 B）
│   ├── w1_symbols.json       # 第1周 笔记符号 30 个（= 附录 C）
│   ├── ep01_w1_full.json     # 第1周完整版合集：数字 + A套 + 符号，带按天章节
│   ├── part1_B.json          # Vol.2：Part 1 B 套 4 段对话 40 轮（带 dialogue/speaker）
│   ├── numbers_02.json       # Vol.2：数字热身 20 题
│   ├── phrases_01.json       # Vol.2：会议定型表現 20 句
│   ├── ep02_full.json        # Vol.2 第2週 完全版合集（已上传）
│   ├── ex01_full.json        # 【お試し】会話1 示例（已上传）
│   ├── part2_C.json / part1_D.json / templates_01.json / numbers_03.json / part3_intro.json  # Vol.3 素材
│   ├── ep03_full.json        # Vol.3 第3週 合集（待审，11/22 生成）
│   ├── mock{E,F,G}_part{1,2,3}.json  # 模考 E/F/G：Part 1 对话 2 段 · Part 2 20 题 · Part 3 演讲 2 段
│   └── mock{E,F,G}_full.json # 模考合集（"mode": "exam" = 不出答案卡，模考模式待实现）
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
    {"dir": "EN→JA", "src": "英文原文", "ref": "日文参考译文", "note": "日语/英语写的要点（难词读音、数字换算）", "tag": ""},
    {"dir": "JA→EN", "src": "日文原文", "ref": "English reference", "note": "日语/英语写的要点", "tag": "連続 1/3"}
  ]
}
```

- `dir` 只能是 `EN→JA` 或 `JA→EN`。
- `note` 用日语（可加 `/ English`）写，不要中文；日语难词带读音，例：`削減（さくげん）`；数字给换算，例：`342 billion = 3,420億`。
- `tag` 用于连续题：`連続 1/3`、`連続 2/3`、`連続 3/3`（日文写法），其余留空。
- 每期 40 题：英→日 20 + 日→英 20，各含 2 组连续题（第 11–13、18–20 题）。
- 题号按「方向」分别从 1 数起（和每日计划里的编号一致）；可选 `countdown`（秒）覆盖默认倒计时。
- `dir` 为 `SYMBOL` 时是笔记符号题：`src` = 意思，`ref` = 符号，没有语音，倒计时让观众写符号。

### 合集文件（一个视频里放多套题，观众按章节自己选当天的部分）

```json
{
  "title": "...", "part": "Part 2 短文形式",
  "sources": [
    {"file": "w1_numbers.json", "label": "数字 ", "countdown": 4,
     "chapters": {"1": "数字 英→日 1–10 · Numbers EN→JA（Day 1）", "11": "数字 日→英 1–10 · Numbers JA→EN（Day 2）"}}
  ],
  "day_guide": ["Day 1：……", "Day 2：……"]
}
```

- `sources` 按顺序拼接；`chapters` 的键是该文件里第几题（从 1 起），在那一题前插入章节标题卡并记 YouTube 章节。
- 有章节时只输出章节级时间戳（不再每题一个）；`day_guide` 会做成开头的「按天练习建议」卡，并写进简介。
- 每周的视频建议做成这种完整版：一次生成全部内容，用 Day 1/2/3… 标注，不写具体日期。

### 对话题（Part 1，Vol.2 起）

题目文件里加 `dialogues`（场景名 + 两位说话人的名字、语言、声音），每题加 `dialogue` 和 `speaker`，见 `content/part1_B.json`。
- 每段对话开头自动插入场景卡（列出两位说话人，6 秒）；标签显示「会話1 · 3/10  EN→JA · Mark Davis」。
- 原文用说话人本人的声音，参考译文用对方的声音（同一个人全程同一个声音）。
- 说话人的 `lang` 必须和 `dir` 一致，不一致时脚本直接报错。
- 新声音先用一段对话出样片试听（10 轮约 7 分钟，生成约 4 分钟）。

### 封面和附录

- 封面：合集 JSON 加 `thumbnail` 字段，`python scripts/make_thumbnail.py content/epNN_full.json output/epNN_thumb.png`。
- 每日计划的附录表格：`python scripts/make_appendix.py content/xxx.json`（从 JSON 生成，计划和视频永远一致）。

## 每周工作流

1. **出题**：按上面的格式和 TOBIS 出题特征生成新一期 JSON，存为 `content/epNN_<part>_<set>.json`。题材轮换：金融市场 / 企业业绩 / IT·数据 / 人事·劳动 / 能源·ESG / 制造·供应链 / 日常商务用语。每期至少 10 题含大数字。
2. **校对**：检查参考译文准确、数字换算正确、日语读音正确。
3. **生成**：`python scripts/make_video.py content/epNN_....json output/epNN.mp4`
4. **抽查**：至少听 5 题，重点检查日语 TTS 有没有读错汉字和数字。读错的地方：在 `make_video.py` 的 `READING_FIXES` 里加一条（原文 → 语音用写法）。
5. **上传**：
   - YouTube：`python scripts/upload_youtube.py output/epNN.mp4`（先加 `--dry-run` 看一眼）。自动填标题、简介（含章节）、标签，并标注 AI 合成内容；上传为私享，Ellen 在 YouTube Studio 检查后改公开（2026-11-12 已实测可以改公开）。
   - B站：手动上传，用 `_description.txt` 作简介，并勾选「AI 生成内容」。B站没有给个人的官方上传 API，不要用基于登录 Cookie 的第三方工具。

## 上传到 YouTube（准备只做一次）

1. 打开 https://console.cloud.google.com/ ，新建项目（例如 tobis-uploader）。
2. 「API とサービス / APIs & Services」→ 启用 **YouTube Data API v3**。
3. 「OAuth 同意画面 / OAuth consent screen」：User type 选 External，填应用名和自己的邮箱；在 Test users 里加上自己的 Google 账号。
4. 「認証情報 / Credentials」→ 创建 OAuth クライアント ID，类型选 **Desktop app**，下载 JSON，改名为 `client_secret.json` 放到项目根目录。
5. 第一次运行上传脚本时会打开浏览器，用 YouTube 频道所在的账号登录并允许。授权保存在 `.youtube_token.json`。
   - 必须在**运行脚本的这台电脑**上的浏览器里允许（授权会跳回 `http://localhost:端口`），在手机上点允许脚本收不到。
   - 出现「禁止访问 … 错误 403: access_denied」= 这个 Gmail 不在 Audience → Test users 里，加上后等一两分钟再试。
   - Windows 下载的 JSON 可能变成 `client_secret.json.json`（隐藏了扩展名），要改名。

- `client_secret*.json` 和 `.youtube_token.json` 已 gitignore，**绝不提交**。
- **最大的限制**：2020-07-28 之后建的 API 项目，在通过 YouTube API 审核（audit）之前，用 API 上传的视频会被锁成私享（Studio 里显示 "locked as private"），开发者反映**无法改成公开**。
  - 第一次先用 1 分钟的测试视频上传，确认是否被锁；被锁就删掉测试视频。
  - 解除方法：提交 Google 的「YouTube API Services – Audit and Quota Extension Form」，说明用途（个人频道每周上传 1 个自制教学视频）；可能要求提供隐私政策页面。审核通过前，YouTube 也手动上传。
  - **2026-11-12 实测（频道 ミサキ @みさき0807，项目 tobis-uploader / 应用名 video_uploader_tobis）：API 上传的测试视频在 Studio 里可以改成公开，没有被锁。** 目前不需要申请审核；以后如果出现 "locked as private" 再按上面申请。
- 配额：每天默认 10,000 单位，一次上传约 1,600，每周 1 个视频足够。
- **超过 15 分钟的视频要求频道完成电话验证**（https://www.youtube.com/verify ）。2026-11-12 第一次上传 Vol.1（32 分钟）因未验证失败；Ellen 已完成验证，之后重新上传。
- OAuth 同意画面处于「测试」状态时，授权大约 7 天过期；脚本会自动重新打开浏览器让你再授权一次。

## 已知问题与经验

- 日语 TTS 用 misaki 的 `JAG2P(version="pyopenjtalk")` → Kokoro。不用默认的 cutlet 模式（要 fugashi + 约 770MB 的 unidic 词典）；`pyopenjtalk-plus` 在 Windows/macOS 有预编译包（原版 pyopenjtalk 在 Windows 要 cmake 编译，会装失败）。
- `norm_ja()` 已处理：千分位逗号、小数点后逐位读（0.25 → れいてんにご，14.2 → じゅうよんてんに）、% → パーセント、〜 → から；读错的词写进 `READING_FIXES`（只改语音，画面不变）。已收录：自社株買い、設備投資、FinOps、7〜9月期、間を取って、50対50。单独的「月末」用正则改成 げつまつ（3月末・今月末・来月末 不能改，pyopenjtalk 本来读对——2026-11-13 发现过这个坑）。
- 写题时避开的写法：「銀行3行」（读成 さんぎょう，写「3銀行」）、「取引先約…」（被切成 先約，写「取引のある約…」）、「年10%」（读成 とし，写「年率10%」）。
- 抽查读音最快的方法：对所有日语句子跑 `pyopenjtalk.g2p(norm_ja(text), kana=True)`，看片假名，不用一题题听。
- Windows 上 winget 装的 ffmpeg 要开新终端才在 PATH 里。
- 日语声音偶尔会读错多音汉字，上传前必须抽查。
- 英语声音在美式和英式之间轮换，日语在女声 jf_alpha 和男声 jm_kumo 之间轮换。
- 40 题一期约 25–30 分钟，生成耗时约 10–15 分钟（CPU）。

## 待办（按优先级）

1. ~~生成第 1 期完整视频~~：已完成，2026-11-12 上传 https://youtu.be/Defi33Zgb_0 （私享，待 Ellen 改公开；第一次上传因频道未电话验证失败，已于同日重传）。
2. **按 docs/TOBIS_冲刺总计划.md 第 6 节的制作时间表做。** 目标 3 級：Part 1・2 占约 85% 时间，Part 3 只做入门。
3. ~~Vol.2（第 2 周）~~：已完成，2026-11-12 上传 https://youtu.be/-LjZuKdLQgI （私享，待改公开）。另有【お試し】示例 https://youtu.be/xfryjUsr4ZI 。系列名：元気社畜の通訳ノート（推荐 handle @GenkiShachikuNote）。
4. Vol.3（第 3 周）：**题目已写好**（2026-11-13，全文见 docs/TOBIS_W3_每日计划.md 附录 A–E），等审核；11/22 前实现演讲模式（speech/segment，按演讲人固定声音、分截播放），再生成。
5. 第 4 周 + 冲刺周：模考 E、F、G **题目已写好**，答案在 docs/答案/（模考前不要给 Ellen 看答案）；要实现模考模式（"mode": "exam"：不出答案卡，只有 听→提示音→倒计时）；冲刺周的错题合集等 Ellen 12/4 的错误日志。
6. 生成 SRT 字幕文件（只在答案阶段显示）；自动生成封面图（1280×720，期数 + 主题）。
7. 可选：接入商用 TTS（Azure / Google，用 Ellen 自己的 API key）作为第二种语音引擎，提高日语自然度。

## 备考时间线（供出题节奏参考）

- 详见 docs/TOBIS_冲刺总计划.md（2026-11-12 重排）。从 11/9 算第 1 周；目标 3 級，只靠 Part 1・2。
- 11/9–15 第 1 周 Part 2 + 数字 + 笔记符号 · 11/16–22 第 2 周 Part 1 入门 + Part 2 巩固 · 11/23–29 第 3 周 强化（新题 + 出力テンプレート + Part 3 入门）· 11/30–12/6 第 4 周 模考 ×2 · 12/7–12/12 考前冲刺 · 12/13 考试
- 12/14 起转入 JTF 笔译冲刺（领域：金融・証券，备选 情報処理）
