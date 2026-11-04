import sqlite3
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "xd_app.db"


@contextmanager
def get_conn():
    """Yield a connection that commits on success, rolls back on error, and is always closed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _loads(value, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _row_to_dict(row) -> dict:
    d = dict(row)
    d["tickers"] = _loads(d.get("tickers"), [])
    d["raw"] = _loads(d.get("raw_json"), {})
    return d


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS videos (
                id TEXT PRIMARY KEY,
                channel_id TEXT,
                title TEXT,
                published_at TEXT,
                transcript TEXT,
                analyzed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT REFERENCES videos(id),
                analyzed_at TEXT,
                tickers TEXT,
                sentiment TEXT,
                market_outlook TEXT,
                strategy TEXT,
                raw_json TEXT
            );
        """)


def save_video(video_id: str, channel_id: str, title: str, published_at: str, transcript: str):
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO videos (id, channel_id, title, published_at, transcript, analyzed_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (video_id, channel_id, title, published_at, transcript, _utcnow()),
        )


def save_analysis(video_id: str, result: dict):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO analyses (video_id, analyzed_at, tickers, sentiment, market_outlook, strategy, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                video_id,
                _utcnow(),
                json.dumps(result.get("tickers", []), ensure_ascii=False),
                result.get("sentiment", ""),
                result.get("market_outlook", ""),
                result.get("strategy", ""),
                json.dumps(result, ensure_ascii=False),
            ),
        )


def get_all_analyses(limit: int = 20) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT a.*, v.title, v.published_at
               FROM analyses a JOIN videos v ON a.video_id = v.id
               ORDER BY a.analyzed_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [_row_to_dict(row) for row in rows]


def get_analysis_by_video(video_id: str) -> dict | None:
    """Return the most recent analysis for a video, or None."""
    with get_conn() as conn:
        row = conn.execute(
            """SELECT a.*, v.title, v.published_at
               FROM analyses a JOIN videos v ON a.video_id = v.id
               WHERE a.video_id = ?
               ORDER BY a.analyzed_at DESC, a.id DESC LIMIT 1""",
            (video_id,),
        ).fetchone()
        return _row_to_dict(row) if row else None


def video_exists(video_id: str) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM analyses WHERE video_id = ?", (video_id,)).fetchone()
        return row is not None
