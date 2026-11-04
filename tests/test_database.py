import sqlite3


SAMPLE = {
    "tickers": [{"symbol": "AAPL", "type": "股票", "sentiment": "看多", "reason": "財報佳"}],
    "sentiment": "看多",
    "market_outlook": "樂觀",
    "strategy": "分批進場",
    "key_points": ["a"],
    "risks": ["b"],
}


def test_init_creates_db_file_and_tables(tmp_db):
    assert tmp_db.DB_PATH.exists()
    with tmp_db.get_conn() as conn:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"videos", "analyses"} <= names


def test_init_is_idempotent(tmp_db):
    tmp_db.init_db()
    tmp_db.init_db()


def test_save_and_fetch_roundtrip(tmp_db):
    tmp_db.save_video("vid00000001", "chan", "標題", "20240101", "逐字稿")
    tmp_db.save_analysis("vid00000001", SAMPLE)

    assert tmp_db.video_exists("vid00000001")
    assert not tmp_db.video_exists("missing0000")

    rows = tmp_db.get_all_analyses(10)
    assert len(rows) == 1
    row = rows[0]
    assert row["title"] == "標題"
    assert row["tickers"][0]["symbol"] == "AAPL"
    assert row["raw"]["strategy"] == "分批進場"
    assert row["analyzed_at"].endswith("+00:00")  # timezone-aware UTC


def test_get_analysis_by_video_not_limited_to_recent(tmp_db):
    # The old CLI only searched the 50 most recent analyses for the cache hit.
    tmp_db.save_video("old00000000", "c", "old", "", "")
    tmp_db.save_analysis("old00000000", {**SAMPLE, "strategy": "old"})
    for i in range(60):
        vid = f"new{i:08d}"
        tmp_db.save_video(vid, "c", "t", "", "")
        tmp_db.save_analysis(vid, SAMPLE)

    found = tmp_db.get_analysis_by_video("old00000000")
    assert found is not None
    assert found["raw"]["strategy"] == "old"
    assert tmp_db.get_analysis_by_video("nope0000000") is None


def test_sql_injection_payload_is_stored_as_data(tmp_db):
    evil = "x'); DROP TABLE videos; --"
    tmp_db.save_video(evil, "c", evil, "", "")
    tmp_db.save_analysis(evil, SAMPLE)
    assert tmp_db.video_exists(evil)
    assert tmp_db.get_analysis_by_video(evil)["title"] == evil
    assert len(tmp_db.get_all_analyses(10)) == 1


def test_limit_is_respected(tmp_db):
    for i in range(5):
        vid = f"v{i:010d}"
        tmp_db.save_video(vid, "c", "t", "", "")
        tmp_db.save_analysis(vid, SAMPLE)
    assert len(tmp_db.get_all_analyses(3)) == 3


def test_corrupted_json_row_does_not_crash(tmp_db):
    tmp_db.save_video("bad00000000", "c", "t", "", "")
    with tmp_db.get_conn() as conn:
        conn.execute(
            "INSERT INTO analyses (video_id, analyzed_at, tickers, raw_json) VALUES (?, ?, ?, ?)",
            ("bad00000000", "2024", "{not json", "{not json"),
        )
    row = tmp_db.get_all_analyses(10)[0]
    assert row["tickers"] == []
    assert row["raw"] == {}


def test_connection_is_closed_after_use(tmp_db):
    with tmp_db.get_conn() as conn:
        pass
    try:
        conn.execute("SELECT 1")
    except sqlite3.ProgrammingError:
        return
    raise AssertionError("connection should be closed")


def test_rollback_on_error(tmp_db):
    try:
        with tmp_db.get_conn() as conn:
            conn.execute("INSERT INTO videos (id) VALUES ('rb000000000')")
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    with tmp_db.get_conn() as conn:
        assert conn.execute("SELECT 1 FROM videos WHERE id='rb000000000'").fetchone() is None
