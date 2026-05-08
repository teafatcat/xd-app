import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "xd_app.db"


def get_conn():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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
            (video_id, channel_id, title, published_at, transcript, datetime.utcnow().isoformat()),
        )


def save_analysis(video_id: str, result: dict):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO analyses (video_id, analyzed_at, tickers, sentiment, market_outlook, strategy, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                video_id,
                datetime.utcnow().isoformat(),
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
        results = []
        for row in rows:
            d = dict(row)
            d["tickers"] = json.loads(d["tickers"]) if d["tickers"] else []
            d["raw"] = json.loads(d["raw_json"]) if d["raw_json"] else {}
            results.append(d)
        return results


def video_exists(video_id: str) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM analyses WHERE video_id = ?", (video_id,)).fetchone()
        return row is not None
