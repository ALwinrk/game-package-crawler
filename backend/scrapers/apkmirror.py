"""APKMirror 爬虫 — 搜索 → 详情页 → 下载页多步跳转.

复用 gvc/sources.py:check_apkmirror() 的核心逻辑.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from backend.core.http_client import http_get, stealth_get, is_cloudflare_block
from backend.core.parser import extract_both
from backend.logging_setup import get_logger
from backend.models.schemas import ApkInfo
from backend.scrapers.base import BaseScraper

logger = get_logger()


class ApkmirrorScraper(BaseScraper):
    name = "APKMirror"

    async def fetch(self, package: str) -> ApkInfo:
        """APKMirror: 搜索 → 详情页 → 版本提取.

        v2.8.1: 多模式 URL 提取 + 搜索页降级提取, 提高站点改版韧性.
        """
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

        # Step 2: 从搜索结果提取详情页 URL (多模式, 韧性更强)
        detail_url = self._extract_detail_url(html)

        # 降级: 如果搜索页没找到链接, 尝试直接从搜索页提取版本
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
            # v2.8.1: 搜索页也没版本, 试包名直连
            direct_url = f"https://www.apkmirror.com/apk/{package}/"
            status2, html2 = await http_get(direct_url)
            if status2 == 200:
                version2, vcode2 = extract_both(html2, package)
                if version2:
                    return ApkInfo(
                        source=self.name, package=package,
                        version=version2, version_code=vcode2, detail_url=direct_url,
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
        """从搜索页提取详情页链接 (v2.8.1: 多模式, 依次尝试)."""
        base = "https://www.apkmirror.com"

        # 模式 1: 经典格式 /apk/{slug}/{version}/
        m = re.search(r'href="(/apk/[^"]+/[^"]+/)"', html)
        if m:
            return urljoin(base, m.group(1))

        # 模式 2: 宽松格式 /apk/... 任意深度
        m = re.search(r'href="(/apk/[^"]+)"', html)
        if m:
            return urljoin(base, m.group(1))

        # 模式 3: 单引号 href
        m = re.search(r"href='(/apk/[^']+/[^']+/)'", html)
        if m:
            return urljoin(base, m.group(1))

        # 模式 4: 包含 upload-date 的上传页链接
        m = re.search(r'href="(/apk/[^"]+?/\d+/)"', html)
        if m:
            return urljoin(base, m.group(1))

        return None
