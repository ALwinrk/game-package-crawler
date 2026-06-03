"""爬虫结果缓存 — TTL dict + 慢速异步任务存储."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from backend.config import get_settings
from backend.logging_setup import get_logger

logger = get_logger()


class ScraperCache:
    """TTL 内存缓存，存储 {cache_key: (FetchResult, expiry_time)}.

    用于避免短时间内的重复爬虫查询。
    """

    def __init__(self):
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = asyncio.Lock()

    def _make_key(self, package: str, mode: str) -> str:
        return f"{package}::{mode}"

    async def get(self, package: str, mode: str = "fast") -> Any | None:
        """获取缓存结果，过期返回 None."""
        key = self._make_key(package, mode)
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            result, expiry = entry
            if time.time() > expiry:
                del self._store[key]
                return None
            logger.debug("缓存命中: {}", key)
            return result

    async def set(self, package: str, mode: str, result: Any) -> None:
        """写入缓存."""
        settings = get_settings()
        ttl = getattr(settings, "cache_ttl_seconds", 300)
        key = self._make_key(package, mode)
        expiry = time.time() + ttl
        async with self._lock:
            self._store[key] = (result, expiry)
            logger.debug("缓存写入: {} (TTL={}s)", key, ttl)

    async def clear(self) -> int:
        """清除所有缓存，返回清除数量."""
        async with self._lock:
            count = len(self._store)
            self._store.clear()
            logger.info("缓存已清除: {} 条", count)
            return count

    async def cleanup(self) -> int:
        """清理过期条目，返回清理数量."""
        now = time.time()
        async with self._lock:
            expired = [k for k, (_, exp) in self._store.items() if now > exp]
            for k in expired:
                del self._store[k]
            if expired:
                logger.debug("缓存过期清理: {} 条", len(expired))
            return len(expired)


class SlowTaskStore:
    """慢速异步任务存储.

    用于 /api/fetch/slow/async 的后台任务结果存储，
    支持通过 task_id 轮询结果。
    """

    def __init__(self, ttl_seconds: int = 3600):
        self._tasks: dict[str, dict] = {}
        self._ttl = ttl_seconds

    def create(self) -> str:
        """创建任务，返回 task_id."""
        task_id = f"slow_{uuid.uuid4().hex[:8]}"
        self._tasks[task_id] = {
            "status": "pending",
            "result": None,
            "error": None,
            "created_at": time.time(),
        }
        self._cleanup_expired()
        return task_id

    def complete(self, task_id: str, result: Any) -> None:
        if task_id in self._tasks:
            self._tasks[task_id] = {
                "status": "completed",
                "result": result,
                "error": None,
                "created_at": time.time(),
            }

    def fail(self, task_id: str, error: str) -> None:
        if task_id in self._tasks:
            self._tasks[task_id] = {
                "status": "error",
                "result": None,
                "error": error,
                "created_at": time.time(),
            }

    def get(self, task_id: str) -> dict | None:
        """获取任务状态."""
        self._cleanup_expired()
        return self._tasks.get(task_id)

    def _cleanup_expired(self) -> None:
        now = time.time()
        expired = [k for k, v in self._tasks.items() if now - v["created_at"] > self._ttl]
        for k in expired:
            del self._tasks[k]


# 全局单例
_scraper_cache: ScraperCache | None = None
_slow_task_store: SlowTaskStore | None = None


def get_scraper_cache() -> ScraperCache:
    global _scraper_cache
    if _scraper_cache is None:
        _scraper_cache = ScraperCache()
    return _scraper_cache


def get_slow_task_store() -> SlowTaskStore:
    global _slow_task_store
    if _slow_task_store is None:
        _slow_task_store = SlowTaskStore()
    return _slow_task_store
