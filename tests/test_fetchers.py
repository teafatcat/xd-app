import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src import youtube_fetcher as yf_mod
from src.data_fetcher import extract_tickers_from_text


@pytest.mark.parametrize("text,expected", [
    ("我看多AAPL股", ["AAPL"]),
    ("NVDA 漲很多", ["NVDA"]),
    ("買進2330.TW，賣出0700.HK", ["0700.HK", "2330.TW"]),
    ("$TSLA 與 QQQ", ["QQQ", "TSLA"]),
    ("QQQ ETF漲", ["QQQ"]),
    ("12330.TWX 不是代號", []),
    ("", []),
])
def test_extract_tickers(text, expected):
    assert extract_tickers_from_text(text) == expected


@pytest.mark.parametrize("url,vid", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ?t=1", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
])
def test_extract_video_id(url, vid):
    assert yf_mod.extract_video_id(url) == vid


def test_extract_video_id_invalid():
    with pytest.raises(ValueError):
        yf_mod.extract_video_id("https://example.com/")


def test_join_transcript_supports_dicts_and_snippet_objects():
    entries = [{"text": "a"}, SimpleNamespace(text="b"), {"text": ""}, SimpleNamespace(text=None)]
    assert yf_mod._join_transcript(entries) == "a b"


def test_channel_url_is_passed_after_end_of_options(monkeypatch):
    run = MagicMock(return_value=subprocess.CompletedProcess([], 0, stdout='{"id":"x","title":"t"}\nnot-json\n', stderr=""))
    monkeypatch.setattr(yf_mod.subprocess, "run", run)
    videos = yf_mod.get_channel_latest_videos("--exec=touch /tmp/pwned", 3)
    cmd = run.call_args.args[0]
    assert cmd[-2:] == ["--", "--exec=touch /tmp/pwned"]
    assert videos == [{"video_id": "x", "title": "t", "published_at": "", "channel_id": ""}]


def test_ytdlp_missing_or_timeout_raises_runtime_error(monkeypatch):
    monkeypatch.setattr(yf_mod.subprocess, "run", MagicMock(side_effect=FileNotFoundError()))
    with pytest.raises(RuntimeError):
        yf_mod.get_channel_latest_videos("https://youtube.com/@x")
    monkeypatch.setattr(yf_mod.subprocess, "run", MagicMock(side_effect=subprocess.TimeoutExpired("yt-dlp", 60)))
    with pytest.raises(RuntimeError):
        yf_mod.get_channel_latest_videos("https://youtube.com/@x")


def test_get_transcript_with_v1_instance_api(monkeypatch):
    """youtube-transcript-api >= 1.0 has no list_transcripts classmethod."""
    transcript = MagicMock()
    transcript.fetch.return_value = [SimpleNamespace(text="你好"), SimpleNamespace(text="世界")]
    tlist = MagicMock()
    tlist.find_manually_created_transcript.return_value = transcript

    class FakeApi:
        def list(self, video_id):
            assert video_id == "abcdefghijk"
            return tlist

    monkeypatch.setattr(yf_mod, "YouTubeTranscriptApi", FakeApi)
    assert yf_mod.get_transcript("abcdefghijk") == "你好 世界"


def test_get_transcript_with_legacy_classmethod_api(monkeypatch):
    transcript = MagicMock()
    transcript.fetch.return_value = [{"text": "hi"}]
    tlist = MagicMock()
    tlist.find_manually_created_transcript.return_value = transcript
    legacy = MagicMock()
    legacy.list_transcripts.return_value = tlist
    monkeypatch.setattr(yf_mod, "YouTubeTranscriptApi", legacy)
    assert yf_mod.get_transcript("abcdefghijk") == "hi"
