"""SQLite 数据库连接 + 建表."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


DB_DIR = Path("./data")
DB_PATH = DB_DIR / "crawler.db"

_local = threading.local()


def get_connection() -> sqlite3.Connection:
    """获取当前线程的 SQLite 连接（线程安全）."""
    if not hasattr(_local, "conn") or _local.conn is None:
        DB_DIR.mkdir(parents=True, exist_ok=True)
        _local.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


def init_db() -> None:
    """创建所有表."""
    conn = get_connection()

    # 记忆化表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_history (
            package_name TEXT PRIMARY KEY,
            version_code TEXT,
            version_name TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 下载任务表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS download_tasks (
            id TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            package_name TEXT,
            version TEXT,
            arch TEXT,
            save_path TEXT NOT NULL,
            total_size INTEGER DEFAULT 0,
            downloaded_size INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 批量任务表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS batch_tasks (
            id TEXT PRIMARY KEY,
            filename TEXT,
            total_rows INTEGER DEFAULT 0,
            completed_rows INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            result_path TEXT,
            error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()


def close_db() -> None:
    """关闭数据库连接."""
    if hasattr(_local, "conn") and _local.conn:
        _local.conn.close()
        _local.conn = None
