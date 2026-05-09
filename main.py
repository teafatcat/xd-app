#!/usr/bin/env python3
"""
XD App - YouTube Investment Analysis CLI

Usage:
  python main.py analyze <youtube_url>
  python main.py channel <channel_url> [--max=5]
  python main.py history [--limit=10]
  python main.py serve
"""

import sys
import os
import argparse
import json
from dotenv import load_dotenv

load_dotenv()


def _check_api_key():
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("錯誤：請設定 OPENROUTER_API_KEY 環境變數")
        print("  複製 .env.example 為 .env 並填入您的 OpenRouter API Key")
        print("  取得方式：https://openrouter.ai → Keys → Create Key（免費）")
        sys.exit(1)


def cmd_analyze(url: str):
    _check_api_key()
    from src.database import init_db, save_video, save_analysis, video_exists, get_all_analyses
    from src.youtube_fetcher import fetch_single_video
    from src.analyzer import analyze_transcript

    init_db()

    print(f"正在抓取影片資訊：{url}")
    try:
        video = fetch_single_video(url)
    except Exception as e:
        print(f"錯誤：{e}")
        sys.exit(1)

    print(f"標題：{video.title}")
    print(f"逐字稿長度：{len(video.transcript)} 字")

    if video_exists(video.video_id):
        print("此影片已分析過，顯示快取結果：")
        analyses = get_all_analyses(50)
        for a in analyses:
            if a["video_id"] == video.video_id:
                _print_result(a["raw"])
                return

    print("正在分析逐字稿...")
    try:
        result = analyze_transcript(video.title, video.transcript)
    except Exception as e:
        print(f"AI 分析錯誤：{e}")
        sys.exit(1)

    save_video(video.video_id, video.channel_id, video.title, video.published_at, video.transcript)
    save_analysis(video.video_id, result)

    _print_result(result)


def cmd_channel(channel_url: str, max_videos: int = 5):
    _check_api_key()
    from src.database import init_db, save_video, save_analysis, video_exists
    from src.youtube_fetcher import get_channel_latest_videos, get_transcript
    from src.analyzer import analyze_transcript

    init_db()

    print(f"正在抓取頻道最新 {max_videos} 部影片：{channel_url}")
    try:
        videos = get_channel_latest_videos(channel_url, max_videos)
    except Exception as e:
        print(f"錯誤：{e}")
        sys.exit(1)

    for v in videos:
        vid = v["video_id"]
        title = v["title"]
        print(f"\n{'='*60}")
        print(f"影片：{title} ({vid})")

        if video_exists(vid):
            print("已分析過，略過")
            continue

        try:
            transcript = get_transcript(vid)
        except Exception as e:
            print(f"無法取得逐字稿：{e}，略過")
            continue

        print(f"逐字稿長度：{len(transcript)} 字，分析中...")
        try:
            result = analyze_transcript(title, transcript)
        except Exception as e:
            print(f"分析失敗：{e}，略過")
            continue

        save_video(vid, v["channel_id"], title, v["published_at"], transcript)
        save_analysis(vid, result)
        _print_result(result)


def cmd_history(limit: int = 10):
    from src.database import init_db, get_all_analyses
    init_db()
    analyses = get_all_analyses(limit)
    if not analyses:
        print("尚無分析記錄")
        return
    for a in analyses:
        print(f"\n{'='*60}")
        print(f"影片：{a['title']}")
        print(f"分析時間：{a['analyzed_at']}")
        _print_result(a["raw"])


def cmd_serve():
    _check_api_key()
    from src.database import init_db
    init_db()
    print("啟動 Web Dashboard：http://127.0.0.1:5000")
    from src.dashboard.app import app
    app.run(debug=False, port=5000)


def _print_result(r: dict):
    print(f"\n整體情緒：{r.get('sentiment', '-')}")
    print(f"市場展望：{r.get('market_outlook', '-')}")
    print(f"時間維度：{r.get('time_horizon', '-')}  可信度：{r.get('confidence', '-')}")

    tickers = r.get("tickers", [])
    if tickers:
        print("\n提及標的：")
        for t in tickers:
            print(f"  {t.get('symbol','?')} [{t.get('type','')}] {t.get('sentiment','')} - {t.get('reason','')}")

    pts = r.get("key_points", [])
    if pts:
        print("\n重點摘要：")
        for p in pts:
            print(f"  ▸ {p}")

    print(f"\n建議策略：\n  {r.get('strategy', '-')}")

    risks = r.get("risks", [])
    if risks:
        print("\n風險提示：")
        for risk in risks:
            print(f"  ⚠ {risk}")

    print(f"\n{r.get('disclaimer', '')}")


def main():
    parser = argparse.ArgumentParser(description="XD App - YouTube 投資分析工具")
    sub = parser.add_subparsers(dest="cmd")

    p_analyze = sub.add_parser("analyze", help="分析單一 YouTube 影片")
    p_analyze.add_argument("url", help="YouTube 影片網址")

    p_channel = sub.add_parser("channel", help="批量分析頻道最新影片")
    p_channel.add_argument("url", help="YouTube 頻道網址")
    p_channel.add_argument("--max", type=int, default=5, help="最多分析幾部影片")

    p_history = sub.add_parser("history", help="查看歷史分析記錄")
    p_history.add_argument("--limit", type=int, default=10)

    sub.add_parser("serve", help="啟動 Web Dashboard")

    args = parser.parse_args()

    if args.cmd == "analyze":
        cmd_analyze(args.url)
    elif args.cmd == "channel":
        cmd_channel(args.url, args.max)
    elif args.cmd == "history":
        cmd_history(args.limit)
    elif args.cmd == "serve":
        cmd_serve()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
