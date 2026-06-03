"""APKMirror 爬虫 — 搜索 → 详情页 → 下载页多步跳转.

复用 gvc/sources.py:check_apkmirror() 的核心逻辑.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from backend.core.http_client import http_get, stealth_get, is_cloudflare_block
from backend.core.parser import extract_both
from backend.logging_setup import get_logger
from backend.models.schemas import ApkInfo
from backend.scrapers.base import BaseScraper

logger = get_logger()


class ApkmirrorScraper(BaseScraper):
    name = "APKMirror"

    async def fetch(self, package: str) -> ApkInfo:
        """APKMirror: 搜索 → 详情页 → 版本提取."""
        search_url = f"https://www.apkmirror.com/?s={package}"

        # Step 1: Fetcher 获取搜索页（代理绕过 GFW）
        status, html = await http_get(search_url)

        if status != 200 or is_cloudflare_block(html):
            # 回退到 StealthySession
            status, html = await stealth_get(search_url)
            if status != 200:
                return ApkInfo(
                    source=self.name,
                    package=package,
                    error=f"HTTP {status}" if status else f"连接失败: {html[:40]}",
                )

        # Step 2: 从搜索结果提取详情页 URL
        detail_url = self._extract_detail_url(html)
        if not detail_url:
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
                error=f"未找到详情页链接 ({len(html)} 字节)",
            )

        # Step 3: 访问详情页提取版本
        status, html = await http_get(detail_url)
        if status != 200:
            status, html = await stealth_get(detail_url)

        version, vcode = extract_both(html, package)
        if version:
            return ApkInfo(
                source=self.name,
                package=package,
                version=version,
                version_code=vcode,
                detail_url=detail_url,
            )
        return ApkInfo(
            source=self.name,
            package=package,
            version_code=vcode,
            detail_url=detail_url,
            error=f"仅匹配版本号 vc:{vcode}" if vcode else f"未匹配版本 ({len(html)} 字节)",
        )

    def _extract_detail_url(self, html: str) -> str | None:
        """从搜索页提取详情页链接."""
        m = re.search(r'href="(/apk/[^"]+/[^"]+/)"', html)
        if m:
            return urljoin("https://www.apkmirror.com", m.group(1))
        return None
