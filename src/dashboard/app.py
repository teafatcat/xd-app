"""Flask web dashboard for investment analysis results."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from flask import Flask, render_template, request, jsonify
from src.database import init_db, get_all_analyses
from src.youtube_fetcher import fetch_single_video
from src.analyzer import analyze_transcript
from src import database as db

app = Flask(__name__, template_folder="templates", static_folder="static")


@app.route("/")
def index():
    analyses = get_all_analyses(limit=30)
    return render_template("index.html", analyses=analyses)


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    data = request.get_json()
    url = (data or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "請提供 YouTube 網址"}), 400

    try:
        video = fetch_single_video(url)
    except Exception as e:
        return jsonify({"error": f"無法取得影片資訊: {e}"}), 400

    if db.video_exists(video.video_id):
        analyses = get_all_analyses(limit=30)
        for a in analyses:
            if a["video_id"] == video.video_id:
                return jsonify({"cached": True, "result": a["raw"]})

    try:
        result = analyze_transcript(video.title, video.transcript)
    except Exception as e:
        return jsonify({"error": f"AI 分析失敗: {e}"}), 500

    db.save_video(
        video.video_id, video.channel_id,
        video.title, video.published_at, video.transcript,
    )
    db.save_analysis(video.video_id, result)

    return jsonify({"cached": False, "title": video.title, "result": result})


@app.route("/api/analyses")
def api_analyses():
    return jsonify(get_all_analyses(limit=30))


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
