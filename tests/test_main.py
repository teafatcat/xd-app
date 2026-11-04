from unittest.mock import MagicMock

import main
from src import youtube_fetcher, analyzer


def test_analyze_uses_cache_without_network(tmp_db, monkeypatch, capsys):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    tmp_db.save_video("dQw4w9WgXcQ", "c", "快取影片", "", "")
    tmp_db.save_analysis("dQw4w9WgXcQ", {"strategy": "快取策略", "tickers": []})
    fetch = MagicMock(side_effect=AssertionError("should not fetch"))
    llm = MagicMock(side_effect=AssertionError("should not call LLM"))
    monkeypatch.setattr(youtube_fetcher, "fetch_single_video", fetch)
    monkeypatch.setattr(analyzer, "analyze_transcript", llm)

    main.cmd_analyze("https://youtu.be/dQw4w9WgXcQ")
    out = capsys.readouterr().out
    assert "快取策略" in out and "快取影片" in out


def test_analyze_new_video_saves_result(tmp_db, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    video = youtube_fetcher.VideoInfo("dQw4w9WgXcQ", "標題", "20240101", "c", "逐字稿")
    monkeypatch.setattr(youtube_fetcher, "fetch_single_video", MagicMock(return_value=video))
    monkeypatch.setattr(analyzer, "analyze_transcript", MagicMock(return_value={"strategy": "新", "tickers": ["AAPL"]}))

    main.cmd_analyze("dQw4w9WgXcQ")
    assert tmp_db.get_analysis_by_video("dQw4w9WgXcQ")["raw"]["strategy"] == "新"
