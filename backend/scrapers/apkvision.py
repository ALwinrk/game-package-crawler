"""APKVision 爬虫 — StealthySession 绕过 Cloudflare JS Challenge.

复用 gvc/sources.py:check_apkvision() 的核心逻辑.
"""

from __future__ import annotations

from backend.core.http_client import http_get, stealth_get, is_cloudflare_block
from backend.core.parser import extract_both
from backend.logging_setup import get_logger
from backend.models.schemas import ApkInfo
from backend.scrapers.base import BaseScraper

logger = get_logger()


class ApkvisionScraper(BaseScraper):
    name = "APKVision"

    async def fetch(self, package: str) -> ApkInfo:
        """APKVision: Fetcher 优先 → StealthySession 降级 (v2.8.1).

        策略:
          1. 先尝试轻量 Fetcher (APKVision 可直接访问, 无需代理)
          2. 被 CF 拦截则升级到 StealthySession 浏览器渲染
          3. 搜索页不存在版本则尝试详情页直连
        """
        search_url = f"https://apkvision.org/search?q={package}"
        detail_url = f"https://apkvision.org/app/{package}"

        # Step 1: Fetcher 优先（快, 无 CF 时直接返回）
        status, html = await http_get(search_url)

        if status == 200 and not is_cloudflare_block(html) and len(html) > 500:
            version, vcode = extract_both(html, package)
            if version:
                return ApkInfo(
                    source=self.name, package=package,
                    version=version, version_code=vcode, detail_url=search_url,
                )
            # 搜索页无版本, 尝试详情页
            v2, vc2 = await self._try_detail_page(detail_url, package)
            if v2:
                return ApkInfo(
                    source=self.name, package=package,
                    version=v2, version_code=vc2, detail_url=detail_url,
                )
            return ApkInfo(source=self.name, package=package, version_code=vcode or vc2,
                           detail_url=search_url,
                           error=f"仅匹配版本号 vc:{vcode or vc2}" if (vcode or vc2) else f"未匹配版本")

        # Step 2: Fetcher 失败或被 CF 拦截 → 升级到 StealthySession
        if status != 200 or is_cloudflare_block(html):
            status, html = await stealth_get(search_url)
            if status != 200:
                return ApkInfo(source=self.name, package=package,
                               error=f"HTTP {status}" if status else f"连接失败: {html[:40]}")

            if is_cloudflare_block(html):
                return ApkInfo(source=self.name, package=package,
                               error="Cloudflare 拦截 (Stealthy 无法绕过)")

        # Step 3: 从 StealthySession 获取的 HTML 提取
        version, vcode = extract_both(html, package)
        if version:
            return ApkInfo(source=self.name, package=package,
                           version=version, version_code=vcode, detail_url=search_url)

        # 搜索页无版本, 尝试详情页
        if not version:
            v2, vc2 = await self._try_detail_page(detail_url, package)
            if v2:
                return ApkInfo(source=self.name, package=package,
                               version=v2, version_code=vc2, detail_url=detail_url)

        return ApkInfo(source=self.name, package=package, version_code=vcode,
                       detail_url=search_url,
                       error=f"仅匹配版本号 vc:{vcode}" if vcode else f"未匹配版本 ({len(html)} 字节)")

    async def _try_detail_page(self, url: str, package: str) -> tuple[str | None, str | None]:
        """v2.8.1: 辅助 — 尝试从详情页提取版本."""
        status, html = await http_get(url)
        if status == 200 and len(html) > 500 and not is_cloudflare_block(html):
            return extract_both(html, package)
        return None, None
