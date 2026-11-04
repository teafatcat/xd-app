import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Point the database module at a throwaway SQLite file."""
    from src import database

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "data" / "test.db")
    database.init_db()
    return database
