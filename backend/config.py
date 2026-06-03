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

    # ── 爬虫 ──────────────────────────────
    scraper_concurrency: int = 4
    playwright_concurrency: int = 2    # Playwright 同时打开页面上限
    request_interval: float = 1.0
    retry_times: int = 2
    retry_delay: float = 1.0

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

    # ── 清理 ──────────────────────────────
    auto_cleanup_days: int = 7

    # ── 多语言 ────────────────────────────
    language: str = "zh"

    # ── HTTP 超时 ─────────────────────────
    request_timeout: float = 10.0
    stealth_timeout: float = 60.0  # StealthySession 总超时(含CF挑战)

    class Config:
        env_prefix = "CRAWLER_"
        env_file = ".env"
        extra = "allow"

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

    def update(self, changes: dict[str, Any]) -> None:
        """运行时更新配置."""
        for key, value in changes.items():
            if hasattr(self, key):
                setattr(self, key, value)
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
