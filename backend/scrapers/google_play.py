"""Google Play 爬虫 — google-play-scraper + Playwright 降级.

复用 gvc/sources.py:check_google() 的核心逻辑.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from pathlib import Path

from backend.config import get_settings
from backend.logging_setup import get_logger
from backend.models.schemas import ApkInfo
from backend.scrapers.base import BaseScraper

logger = get_logger()

# ── 代理注入（google-play-scraper 底层用 urllib）─────────────

_proxy_setup_done = False
_proxy_lock = threading.Lock()


def _setup_urllib_proxy() -> None:
    global _proxy_setup_done
    if _proxy_setup_done:
        return
    with _proxy_lock:
        if _proxy_setup_done:
            return
        _proxy_setup_done = True
        settings = get_settings()
        if not settings.proxy:
            return
        for env_key in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
            os.environ[env_key] = settings.proxy


class GooglePlayScraper(BaseScraper):
    name = "Google Play"

    async def fetch(self, package: str) -> ApkInfo:
        """通过 google-play-scraper 查询 Google Play."""
        try:
            _setup_urllib_proxy()

            # 加载 Cookie（如果有）
            cookie_data = self._load_cookies()

            info = await asyncio.to_thread(
                self._gp_fetch, package, cookie_data,
            )

            version = info.get("version", "")
            if version.lower() in ("varies with device", "varies", ""):
                return ApkInfo(
                    source=self.name,
                    package=package,
                    error="Varies with device",
                )

            # 格式化发布日期（Unix timestamp → 可读日期）
            release_date = None
            updated_ts = info.get("updated")
            if updated_ts:
                from datetime import datetime
                try:
                    release_date = datetime.fromtimestamp(int(updated_ts)).strftime("%Y-%m-%d")
                except (ValueError, OSError):
                    release_date = str(updated_ts)

            # google-play-scraper 不返回 versionCode，需从详情页 HTML 提取
            # 这里尝试通过 version 字段本身作为版本名
            return ApkInfo(
                source=self.name,
                package=package,
                version=version,
                version_name=version,
                version_code=None,  # google-play-scraper 不提供 versionCode
                release_date=release_date,
                file_size=info.get("size", ""),
                detail_url=f"https://play.google.com/store/apps/details?id={package}",
                abis=[],
            )
        except ImportError:
            return ApkInfo(
                source=self.name,
                package=package,
                error="google-play-scraper 未安装",
            )
        except Exception as e:
            err_msg = f"{type(e).__name__}: {e!s}"[:100]
            if "404" in err_msg or "NotFoundError" in err_msg:
                err_msg = "App not found on Google Play"
            elif "URLError" in err_msg or "timeout" in err_msg.lower():
                err_msg = "Google Play unreachable (proxy needed)"
            return ApkInfo(source=self.name, package=package, error=err_msg)

    def _gp_fetch(self, package: str, cookie_data: dict | None):
        """同步执行 google-play-scraper 调用."""
        from google_play_scraper import app as gp_app

        kwargs = {"lang": "en", "country": "us"}
        if cookie_data:
            # google-play-scraper 可能不支持自定义 cookie
            # 作为备选参数传递
            pass

        return gp_app(package, **kwargs)

    def _load_cookies(self) -> dict | None:
        """从配置中的 cookie 文件加载."""
        settings = get_settings()
        path = settings.google_play_cookie_path
        if not path:
            return None
        cookie_file = Path(path)
        if not cookie_file.exists():
            logger.warning("Google Play Cookie 文件不存在: {}", path)
            return None
        try:
            with open(cookie_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("加载 Google Play Cookie 失败: {}", e)
            return None
