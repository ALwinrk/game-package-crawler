"""配置管理 — pydantic BaseSettings + config.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置，支持从 config.json 和环境变量读取."""

    # ── 下载 ──────────────────────────────
    download_path: str = "./downloads"
    download_concurrency: int = 3
    download_chunk_size: int = 1024 * 1024  # 下载缓冲区(字节)，默认1MB

    # ── 爬虫 ──────────────────────────────
    scraper_concurrency: int = 4
    playwright_concurrency: int = 2    # Playwright 同时打开页面上限
    retry_times: int = 2
    retry_delay: float = 1.0

    # ── 批量任务 ──────────────────────────
    batch_concurrency: int = 5         # 批量任务同时处理的包名数

    # ── 缓存 ──────────────────────────────
    cache_ttl_seconds: int = 300       # 爬虫结果缓存有效期(秒)，默认5分钟

    # ── 代理 ──────────────────────────────
    proxy: str = "http://127.0.0.1:7897"

    # ── 站点开关 ──────────────────────────
    enabled_sites: list[str] = [
        "google_play", "apkpure", "apkcombo", "apkmirror", "apkvision",
    ]

    # ── Google Play ───────────────────────
    google_play_cookie_path: str = ""

    # ── 日志 ──────────────────────────────
    log_level: str = "INFO"
    log_retention_days: int = 30

    # ── HTTP 超时 ─────────────────────────
    request_timeout: float = 10.0
    stealth_timeout: float = 60.0  # StealthySession 总超时(含CF挑战)

    # ── 每日更新面板 (v2.8.1) ─────────────
    update_check_interval: int = 1800    # 定时抓取间隔(秒), 默认30分钟
    daily_updates_pages: int = 3         # 每个源抓取页数
    daily_updates_limit: int = 20        # API 默认返回条数
    frontend_poll_interval: int = 300    # 前端轮询间隔(秒), 默认5分钟

    class Config:
        env_prefix = "CRAWLER_"
        env_file = ".env"
        extra = "ignore"

    @classmethod
    def from_json(cls, path: str = "config.json") -> Settings:
        """从 config.json 加载配置."""
        config_path = Path(path)
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls(**data)
        return cls()

    def save(self, path: str = "config.json") -> None:
        """保存配置到 config.json."""
        data = self.model_dump(exclude_none=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # 允许通过 /api/config PATCH 热更新的键白名单
    _HOT_UPDATE_WHITELIST: set[str] = {
        "scraper_concurrency", "playwright_concurrency", "batch_concurrency",
        "download_concurrency", "download_chunk_size",
        "retry_times", "retry_delay", "cache_ttl_seconds",
        "request_timeout", "stealth_timeout",
        "log_level", "log_retention_days",
        "enabled_sites",
        "update_check_interval", "daily_updates_pages",
        "daily_updates_limit", "frontend_poll_interval",
    }

    def update(self, changes: dict[str, Any]) -> None:
        """运行时更新配置 — 仅白名单键可通过 API 修改.

        敏感键 (proxy, download_path, google_play_cookie_path)
        需要重启应用生效, 通过 API 修改会被拒绝。
        """
        for key, value in changes.items():
            if key in self._HOT_UPDATE_WHITELIST and hasattr(self, key):
                setattr(self, key, value)
            elif hasattr(self, key) and key not in self._HOT_UPDATE_WHITELIST:
                raise ValueError(
                    f"'{key}' 是敏感配置，需要编辑 config.json 后重启应用"
                )
        self.save()


# 全局单例
_settings: Settings | None = None


def get_settings(config_path: str = "config.json") -> Settings:
    """获取全局配置单例."""
    global _settings
    if _settings is None:
        _settings = Settings.from_json(config_path)
    return _settings


def reload_settings(config_path: str = "config.json") -> Settings:
    """重新加载配置."""
    global _settings
    _settings = Settings.from_json(config_path)
    return _settings
