"""把生成好的视频上传到 YouTube（YouTube Data API v3）。

用法:
    python scripts/upload_youtube.py output/ep01_w1.mp4 --dry-run      # 只打印要上传的信息，不上传
    python scripts/upload_youtube.py output/ep01_w1.mp4                # 上传为「私享」
    python scripts/upload_youtube.py output/ep01_w1.mp4 --privacy unlisted

- 标题 = <名字>_description.txt 的第一行（也可以用 --title 覆盖），简介 = 整个 _description.txt（含章节）。
- 默认上传为 private。注意：API 项目通过 YouTube API 审核（audit）之前，YouTube 会把 API 上传的视频
  锁成私享（"locked as private"），可能无法改公开。审核前请先用测试视频确认，详见 CLAUDE.md。
- 自动标注「AI 合成内容」（status.containsSyntheticMedia = true）。
- 第一次运行会打开浏览器，请用你的 YouTube 账号登录并授权；授权结果存在 .youtube_token.json（已 gitignore）。

准备（只做一次）: 见 CLAUDE.md「上传到 YouTube」。
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLIENT_SECRET = Path(os.environ.get("YT_CLIENT_SECRET", ROOT / "client_secret.json"))
TOKEN = ROOT / ".youtube_token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

DEFAULT_TAGS = ["TOBIS", "ビジネス通訳検定", "通訳練習", "逐次通訳", "口译练习", "英日口译",
                "日英通訳", "interpreting practice", "Japanese English interpreting"]
CATEGORY_EDUCATION = "27"


def clean(text):
    """YouTube 不接受标题/简介里的 < 和 >。"""
    return text.replace("<", "＜").replace(">", "＞")


def build_body(video, title, privacy):
    desc_file = video.with_name(video.stem + "_description.txt")
    if not desc_file.exists():
        sys.exit(f"找不到简介文件 {desc_file}（make_video.py 会和视频一起生成）")
    description = clean(desc_file.read_text(encoding="utf-8").strip())
    title = clean(title or description.splitlines()[0]).strip()
    if len(title) > 100:
        sys.exit(f"标题超过 100 字（{len(title)}）：请用 --title 指定一个短标题")
    if len(description.encode("utf-8")) > 5000:
        sys.exit(f"简介超过 5000 字节（{len(description.encode('utf-8'))}）")
    return {
        "snippet": {
            "title": title,
            "description": description,
            "tags": DEFAULT_TAGS,
            "categoryId": CATEGORY_EDUCATION,
            "defaultLanguage": "zh-Hans",
            "defaultAudioLanguage": "ja",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,
        },
    }


def credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    from google.auth.exceptions import RefreshError

    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES) if TOKEN.exists() else None
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:  # 测试状态的 OAuth 应用，授权约 7 天过期 → 重新登录
            creds = None
    if not creds or not creds.valid:
        if not CLIENT_SECRET.exists():
            sys.exit(f"找不到 OAuth 客户端文件 {CLIENT_SECRET}。请按 CLAUDE.md「上传到 YouTube」下载后放到项目根目录。")
        creds = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES).run_local_server(port=0)
    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return creds


def upload(video, body):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    youtube = build("youtube", "v3", credentials=credentials())
    media = MediaFileUpload(str(video), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"上传中 {int(status.progress() * 100)}%", flush=True)
    return response


def main():
    ap = argparse.ArgumentParser(description="上传视频到 YouTube")
    ap.add_argument("video", type=Path)
    ap.add_argument("--title", help="覆盖标题（默认取简介第一行）")
    ap.add_argument("--privacy", choices=["private", "unlisted", "public"], default="private")
    ap.add_argument("--dry-run", action="store_true", help="只打印要上传的信息")
    args = ap.parse_args()

    if not args.video.exists():
        sys.exit(f"找不到视频 {args.video}")
    body = build_body(args.video, args.title, args.privacy)
    if args.dry_run:
        print(json.dumps(body, ensure_ascii=False, indent=2))
        print(f"\n视频: {args.video}（{args.video.stat().st_size / 1e6:.1f} MB） — dry run，未上传")
        return

    resp = upload(args.video, body)
    vid = resp["id"]
    url = f"https://youtu.be/{vid}"
    args.video.with_name(args.video.stem + "_youtube.txt").write_text(url + "\n", encoding="utf-8")
    print(f"已上传: {url}（{resp['status']['privacyStatus']}）")
    print(f"下一步: 打开 https://studio.youtube.com/video/{vid}/edit 检查；"
          "如果显示 locked as private，说明 API 项目还没通过审核（见 CLAUDE.md），这个视频改不了公开")


if __name__ == "__main__":
    main()
