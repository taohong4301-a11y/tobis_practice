# 搬到 Claude Code 的步骤

## 1. 放到你的电脑上

把 `tobis-practice.zip` 解压到你想放项目的文件夹，例如 `~/Projects/tobis-practice`。

（可选）建成 GitHub 仓库，以后换电脑或用网页版 Claude Code 都能接着做：

```bash
cd ~/Projects/tobis-practice
git init && git add . && git commit -m "TOBIS practice video series: initial"
gh repo create tobis-practice --private --source=. --push
```

## 2. 在 Claude Code 里打开

```bash
cd ~/Projects/tobis-practice
claude
```

Claude Code 启动后会自动读取 `CLAUDE.md`，里面写了项目背景、TOBIS 出题规则、JSON 格式、每周流程和待办，不用重新解释。

## 3. 第一条指令（直接复制）

> 读一下 CLAUDE.md。帮我把环境搭起来（venv、依赖、ffmpeg、下载模型），然后用 content/ep01_part2_A.json 生成第 1 期视频到 output/ep01.mp4。生成后抽查日语题里的数字和汉字读音，告诉我有没有读错。

## 4. 之后每周一条指令

> 按 CLAUDE.md 的每周工作流做第 N 期：Part 2 X 套 40 题，题材侧重 ___。生成 JSON → 我确认题目 → 生成视频 → 抽查 → 给我简介和章节。

## 文件说明

| 文件 | 用途 |
| --- | --- |
| `CLAUDE.md` | 项目说明书，Claude Code 每次启动自动读 |
| `scripts/make_video.py` | 生成视频、YouTube 章节、简介模板 |
| `scripts/download_models.sh` | 下载语音模型（约 350MB，不放进 git） |
| `content/ep01_part2_A.json` | 第 1 期 40 题（和《TOBIS_W1_每日计划.md》附录 A 相同） |
| `requirements.txt` | Python 依赖 |
