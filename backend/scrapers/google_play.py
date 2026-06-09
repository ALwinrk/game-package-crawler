"""Google Play 爬虫 — google-play-scraper + Playwright 降级.

复用 gvc/sources.py:check_google() 的核心逻辑.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from datetime import datetime
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
        """Google Play 双语言查询: 中文站取标题, 英文站取更新内容.

        中文 Google Play (lang=zh, country=cn) 的 recentChanges 常为空,
        英文站 (lang=en, country=us) 几乎总有完整 changelog。

        v2.8.1: 修复 Cookie 传递问题 + 库异常时降级到 HTTP 解析.
        """
        try:
            _setup_urllib_proxy()
            cookie_data = self._load_cookies()

            # 并行请求中文站 + 英文站
            info_cn, info_en = await asyncio.gather(
                asyncio.to_thread(self._gp_fetch, package, cookie_data, "zh", "cn"),
                asyncio.to_thread(self._gp_fetch, package, cookie_data, "en", "us"),
            )

            # 版本号优先中文站, 空则用英文站
            version_cn = info_cn.get("version", "")
            version_en = info_en.get("version", "")
            version = version_cn if version_cn and version_cn.lower() not in ("varies with device", "varies") else version_en

            # 提前提取 (错误路径也需要)
            title = info_cn.get("title", "") or info_en.get("title", "") or ""
            whats_new_early = info_en.get("recentChanges") or info_cn.get("recentChanges") or ""

            if not version or version.lower() in ("varies with device", "varies", ""):
                return ApkInfo(
                    source=self.name,
                    package=package,
                    error="Varies with device",
                    app_name=title or None,
                    whats_new=whats_new_early or None,
                )

            # 发布日期
            release_date = None
            updated_ts = info_cn.get("updated") or info_en.get("updated")
            if updated_ts:
                try:
                    release_date = datetime.fromtimestamp(int(updated_ts)).strftime("%Y-%m-%d")
                except (ValueError, OSError):
                    release_date = str(updated_ts)

            return ApkInfo(
                source=self.name,
                package=package,
                version=version,
                version_name=version,
                version_code=None,
                release_date=release_date,
                file_size=info_cn.get("size", "") or info_en.get("size", ""),
                detail_url=f"https://play.google.com/store/apps/details?id={package}&hl=zh_CN",
                abis=[],
                app_name=title or None,
                whats_new=whats_new_early or None,
            )
        except ImportError:
            # v2.8.1: 库不可用时降级到 HTTP 解析 Google Play 页面
            return await self._fallback_http(package)
        except Exception as e:
            err_msg = f"{type(e).__name__}: {e!s}"[:100]
            if "404" in err_msg or "NotFoundError" in err_msg:
                err_msg = "App not found on Google Play"
            elif "URLError" in err_msg or "timeout" in err_msg.lower():
                err_msg = "Google Play unreachable (proxy needed)"
            return ApkInfo(source=self.name, package=package, error=err_msg)

    def _gp_fetch(self, package: str, cookie_data: dict | None, lang: str = "en", country: str = "us"):
        """同步执行 google-play-scraper 调用.

        v2.8.1: 将 cookie_data 传递给 gp_app, 修复 Cookie 功能失效问题.
        """
        from google_play_scraper import app as gp_app
        kwargs: dict = {"lang": lang, "country": country}
        if cookie_data:
            kwargs["cookie"] = cookie_data
        return gp_app(package, **kwargs)

    async def _fallback_http(self, package: str) -> ApkInfo:
        """v2.8.1: google-play-scraper 不可用时的 HTTP 降级.

        直接请求 Google Play 页面, 用通用解析器提取版本.
        """
        try:
            from backend.core.http_client import http_get
            from backend.core.parser import extract_both

            url = f"https://play.google.com/store/apps/details?id={package}&hl=zh_CN"
            status, html = await http_get(url)
            if status == 200 and len(html) > 500:
                version, vcode = extract_both(html, package)
                if version:
                    return ApkInfo(
                        source=self.name,
                        package=package,
                        version=version,
                        version_code=vcode,
                        detail_url=url,
                    )
            return ApkInfo(source=self.name, package=package,
                           error=f"Google Play unreachable (HTTP {status})")
        except Exception as e:
            return ApkInfo(source=self.name, package=package,
                           error=f"Fallback failed: {type(e).__name__}")

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
