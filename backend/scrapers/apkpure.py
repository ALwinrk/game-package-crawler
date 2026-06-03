"""APKPure 爬虫 — 搜索页 → 详情页两步提取，绕过 Cloudflare.

复用 gvc/sources.py:check_apkpure() 的核心逻辑.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from backend.core.http_client import http_get, js_render_get, is_cloudflare_block
from backend.core.parser import extract_both
from backend.logging_setup import get_logger
from backend.models.schemas import ApkInfo
from backend.scrapers.base import BaseScraper

logger = get_logger()


class ApkpureScraper(BaseScraper):
    name = "APKPure"

    async def fetch(self, package: str) -> ApkInfo:
        """APKPure: 搜索页 (JS渲染) → 详情页 URL → 详情页提取版本."""
        search_url = f"https://apkpure.com/search?q={package}"

        # Step 1: Fetcher 获取搜索页
        status, html = await http_get(search_url)
        fetcher_ok = status == 200 and not is_cloudflare_block(html)

        if not fetcher_ok:
            # 回退到 apkpure.net
            return await self._fetch_from_url(
                f"https://apkpure.net/search?q={package}", package,
            )

        # Step 2: 从搜索页提取详情 URL
        detail_url = self._extract_detail_url(html, package)

        # Step 3: 若 Fetcher 拿不到链接，用 JS 渲染
        if not detail_url:
            b_status, b_html = await js_render_get(search_url)
            if b_status == 200:
                detail_url = self._extract_detail_url(b_html, package)

        # Step 4: 访问详情页提取版本
        if detail_url:
            return await self._fetch_from_url(detail_url, package)

        # Step 5: 兜底
        return await self._fetch_from_url(
            f"https://apkpure.net/search?q={package}", package,
        )

    async def _fetch_from_url(self, url: str, package: str) -> ApkInfo:
        """从指定 URL 提取版本信息."""
        status, html = await http_get(url)
        if status != 200:
            return ApkInfo(
                source=self.name,
                package=package,
                detail_url=url,
                error=f"HTTP {status}" if status else f"连接失败: {html[:40]}",
            )

        version, vcode = extract_both(html, package)
        if version:
            return ApkInfo(
                source=self.name,
                package=package,
                version=version,
                version_code=vcode,
                detail_url=url,
            )
        return ApkInfo(
            source=self.name,
            package=package,
            version_code=vcode,
            detail_url=url,
            error=f"仅匹配版本号 vc:{vcode}" if vcode else f"未匹配版本 ({len(html)} 字节)",
        )

    def _extract_detail_url(self, html: str, pkg: str) -> str | None:
        """从 APKPure 搜索结果页提取目标 app 的详情页 URL."""
        escaped = re.escape(pkg)
        pattern = r'href="((?:https?://apkpure\.com)?/[^"]*' + escaped + r'[^"]*)"'
        for m in re.finditer(pattern, html):
            url = m.group(1)
            if "/search" not in url:
                return urljoin("https://apkpure.com", url)
        return None
