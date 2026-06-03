"""记忆化存储 — SQLite user_history 表 CRUD."""

from __future__ import annotations

from backend.db.database import get_connection
from backend.logging_setup import get_logger

logger = get_logger()


class MemoStore:
    """用户手动输入的版本记忆.

    - 以包名为 key，仅保存最近一次输入。
    - Excel 批量处理不触发记忆存储。
    """

    def get(self, package_name: str) -> dict | None:
        """查询包名的历史版本信息."""
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM user_history WHERE package_name = ?",
            (package_name,),
        ).fetchone()
        if row:
            return {
                "package_name": row["package_name"],
                "version_code": row["version_code"],
                "version_name": row["version_name"],
                "updated_at": row["updated_at"],
            }
        return None

    def upsert(
        self,
        package_name: str,
        version_code: str | None = None,
        version_name: str | None = None,
    ) -> None:
        """保存或更新版本信息."""
        conn = get_connection()
        conn.execute("""
            INSERT INTO user_history (package_name, version_code, version_name, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(package_name) DO UPDATE SET
                version_code = excluded.version_code,
                version_name = excluded.version_name,
                updated_at = CURRENT_TIMESTAMP
        """, (package_name, version_code or "", version_name or ""))
        conn.commit()
        logger.debug("记忆化保存: {} → vc:{} v:{}", package_name, version_code, version_name)

    def delete(self, package_name: str) -> None:
        """删除某包名的记忆."""
        conn = get_connection()
        conn.execute("DELETE FROM user_history WHERE package_name = ?", (package_name,))
        conn.commit()

    def list_all(self, limit: int = 100) -> list[dict]:
        """列出所有记忆."""
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM user_history ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "package_name": r["package_name"],
                "version_code": r["version_code"],
                "version_name": r["version_name"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]


# 全局单例
_memo_store: MemoStore | None = None


def get_memo_store() -> MemoStore:
    global _memo_store
    if _memo_store is None:
        _memo_store = MemoStore()
    return _memo_store
