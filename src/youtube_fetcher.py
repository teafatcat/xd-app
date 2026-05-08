"""Fetch YouTube video metadata and transcripts."""

import re
import subprocess
import json
from dataclasses import dataclass

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound


@dataclass
class VideoInfo:
    video_id: str
    title: str
    published_at: str
    channel_id: str
    transcript: str


def extract_video_id(url: str) -> str:
    """Extract video ID from a YouTube URL or return as-is if already an ID."""
    patterns = [
        r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})",
        r"^([A-Za-z0-9_-]{11})$",
    ]
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    raise ValueError(f"Cannot extract video ID from: {url}")


def get_channel_latest_videos(channel_url: str, max_videos: int = 5) -> list[dict]:
    """Use yt-dlp to fetch latest video metadata from a channel."""
    cmd = [
        "yt-dlp",
        "--dump-json",
        "--flat-playlist",
        f"--playlist-end={max_videos}",
        "--no-warnings",
        channel_url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp error: {result.stderr[:300]}")

    videos = []
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        data = json.loads(line)
        videos.append({
            "video_id": data.get("id", ""),
            "title": data.get("title", ""),
            "published_at": data.get("upload_date", ""),
            "channel_id": data.get("channel_id", ""),
        })
    return videos


def get_transcript(video_id: str, lang_priority: list[str] | None = None) -> str:
    """Fetch transcript for a video, trying languages in priority order."""
    if lang_priority is None:
        lang_priority = ["zh-TW", "zh-HK", "zh", "zh-Hans", "en"]

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        # Try manual transcripts first
        for lang in lang_priority:
            try:
                t = transcript_list.find_manually_created_transcript([lang])
                return _join_transcript(t.fetch())
            except Exception:
                continue

        # Fall back to auto-generated
        for lang in lang_priority:
            try:
                t = transcript_list.find_generated_transcript([lang])
                return _join_transcript(t.fetch())
            except Exception:
                continue

        # Last resort: take whatever is available
        for t in transcript_list:
            return _join_transcript(t.fetch())

    except (TranscriptsDisabled, NoTranscriptFound) as e:
        raise RuntimeError(f"No transcript available for {video_id}: {e}")

    raise RuntimeError(f"Could not fetch any transcript for {video_id}")


def _join_transcript(entries) -> str:
    return " ".join(entry["text"] for entry in entries if entry.get("text"))


def fetch_single_video(url: str) -> VideoInfo:
    """Fetch info + transcript for a single video URL."""
    video_id = extract_video_id(url)

    # Get metadata via yt-dlp
    cmd = [
        "yt-dlp",
        "--dump-json",
        "--no-warnings",
        "--no-playlist",
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp error: {result.stderr[:300]}")

    data = json.loads(result.stdout)
    transcript = get_transcript(video_id)

    return VideoInfo(
        video_id=video_id,
        title=data.get("title", ""),
        published_at=data.get("upload_date", ""),
        channel_id=data.get("channel_id", ""),
        transcript=transcript,
    )
