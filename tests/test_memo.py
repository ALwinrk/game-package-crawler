"""记忆化存储测试."""

import pytest
import sqlite3
from pathlib import Path

from backend.db.database import init_db, close_db, get_connection


@pytest.fixture(autouse=True)
def setup_db(tmp_path):
    """使用临时数据库."""
    import backend.db.database as db_mod
    original = db_mod.DB_PATH
    db_mod.DB_PATH = tmp_path / "test.db"
    db_mod.DB_DIR = tmp_path
    init_db()
    yield
    close_db()
    db_mod.DB_PATH = original


class TestMemoStore:
    def test_upsert_and_get(self):
        from backend.memo.store import MemoStore
        store = MemoStore()
        store.upsert("com.test.app", "100", "1.0.0")

        result = store.get("com.test.app")
        assert result is not None
        assert result["version_code"] == "100"
        assert result["version_name"] == "1.0.0"

    def test_update_existing(self):
        from backend.memo.store import MemoStore
        store = MemoStore()
        store.upsert("com.test.app", "100", "1.0.0")
        store.upsert("com.test.app", "200", "2.0.0")

        result = store.get("com.test.app")
        assert result["version_code"] == "200"
        assert result["version_name"] == "2.0.0"

    def test_get_nonexistent(self):
        from backend.memo.store import MemoStore
        store = MemoStore()
        result = store.get("com.nonexistent.app")
        assert result is None

    def test_delete(self):
        from backend.memo.store import MemoStore
        store = MemoStore()
        store.upsert("com.test.app", "100", "1.0.0")
        store.delete("com.test.app")
        assert store.get("com.test.app") is None

    def test_list_all(self):
        from backend.memo.store import MemoStore
        store = MemoStore()
        store.upsert("com.a", "1", "v1")
        store.upsert("com.b", "2", "v2")
        items = store.list_all()
        assert len(items) == 2
