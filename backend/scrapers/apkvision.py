"""APKVision 爬虫 — StealthySession 绕过 Cloudflare JS Challenge.

复用 gvc/sources.py:check_apkvision() 的核心逻辑.
"""

from __future__ import annotations

from backend.core.http_client import stealth_get, is_cloudflare_block
from backend.core.parser import extract_both
from backend.logging_setup import get_logger
from backend.models.schemas import ApkInfo
from backend.scrapers.base import BaseScraper

logger = get_logger()


class ApkvisionScraper(BaseScraper):
    name = "APKVision"

    async def fetch(self, package: str) -> ApkInfo:
        """APKVision: StealthySession 浏览器渲染 + CF 绕过."""
        search_url = f"https://apkvision.org/search?q={package}"

        status, html = await stealth_get(search_url)
        if status != 200:
            return ApkInfo(
                source=self.name,
                package=package,
                error=f"HTTP {status}" if status else f"连接失败: {html[:40]}",
            )

        if is_cloudflare_block(html):
            return ApkInfo(
                source=self.name,
                package=package,
                error="Cloudflare 拦截 (Stealthy 无法绕过)",
            )

        version, vcode = extract_both(html, package)
        if version:
            return ApkInfo(
                source=self.name,
                package=package,
                version=version,
                version_code=vcode,
                detail_url=search_url,
            )
        return ApkInfo(
            source=self.name,
            package=package,
            version_code=vcode,
            detail_url=search_url,
            error=f"仅匹配版本号 vc:{vcode}" if vcode else f"未匹配版本 ({len(html)} 字节)",
        )
