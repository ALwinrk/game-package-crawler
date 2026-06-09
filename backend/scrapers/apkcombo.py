"""APKCombo 爬虫 — /api/app 302 重定向 → 详情页版本提取.

复用 gvc/sources.py:check_apkcombo() 的核心逻辑.
"""

from __future__ import annotations

import re as _re
from html import unescape

from backend.core.http_client import http_get
from backend.core.parser import extract_both
from backend.logging_setup import get_logger
from backend.models.schemas import ApkInfo
from backend.scrapers.base import BaseScraper

logger = get_logger()


class ApkcomboScraper(BaseScraper):
    name = "APKCombo"

    async def fetch(self, package: str) -> ApkInfo:
        """APKCombo: /api/app/<pkg> API → 搜索页降级 (v2.8.1).

        优先使用 API 端点 (最稳定), 失败时降级到 HTML 搜索页.
        """
        api_url = f"https://apkcombo.com/api/app/{package}"
        cn_detail_url = f"https://apkcombo.com/zh/{package}"
        status, html = await http_get(api_url)

        # v2.8.1: API 失败 → 降级到搜索页
        if status != 200 or len(html) < 500:
            if status != 200:
                logger.debug("APKCombo API 返回 {}, 降级到搜索页", status)
            return await self._fallback_search(package, cn_detail_url)

        version, vcode = extract_both(html, package)
        app_name = self._extract_app_name(html) or None
        whats_new = self._extract_whats_new(html) or None

        if version:
            return ApkInfo(
                source=self.name,
                package=package,
                version=version,
                version_code=vcode,
                detail_url=cn_detail_url,
                app_name=app_name,
                whats_new=whats_new,
            )
        return ApkInfo(
            source=self.name,
            package=package,
            version_code=vcode,
            detail_url=cn_detail_url,
            error=f"仅匹配版本号 vc:{vcode}" if vcode else f"未匹配版本 ({len(html)} 字节)",
            app_name=app_name,
            whats_new=whats_new,
        )

    async def _fallback_search(self, package: str, cn_detail_url: str) -> ApkInfo:
        """v2.8.1: /api/app 不可用时降级到 HTML 搜索页 / 详情页直连."""
        # 优先尝试详情页直连
        status, html = await http_get(cn_detail_url)
        if status == 200 and len(html) > 500:
            version, vcode = extract_both(html, package)
            if version:
                return ApkInfo(
                    source=self.name, package=package,
                    version=version, version_code=vcode, detail_url=cn_detail_url,
                )

        # 回退到搜索页
        search_url = f"https://apkcombo.com/search?q={package}"
        status, html = await http_get(search_url)
        if status == 200:
            version, vcode = extract_both(html, package)
            if version:
                return ApkInfo(
                    source=self.name, package=package,
                    version=version, version_code=vcode, detail_url=search_url,
                )
            return ApkInfo(source=self.name, package=package, version_code=vcode,
                           detail_url=search_url,
                           error=f"仅匹配版本号 vc:{vcode}" if vcode else "未匹配版本")

        return ApkInfo(source=self.name, package=package,
                       error=f"API+搜索均失败 (HTTP {status})")

    def _extract_app_name(self, html: str) -> str | None:
        """从 APKCombo 详情页提取应用名."""
        for pattern in [
            r'<h1[^>]*itemprop="name"[^>]*>([^<]+)</h1>',
            r'<div[^>]*class="[^"]*app-title[^"]*"[^>]*>([^<]+)</div>',
            r'<title>([^<]+) APK [^-]',  # "PUBG MOBILE APK - Download"
        ]:
            m = _re.search(pattern, html, _re.IGNORECASE)
            if m:
                name = m.group(1).strip()
                # 清理 title 标签中的 "APK" 等后缀
                name = _re.sub(r'\s+APK\s*$', '', name, flags=_re.IGNORECASE)
                return name
        return None

    def _extract_whats_new(self, html: str) -> str | None:
        """从 APKCombo 详情页提取更新内容."""
        for pattern in [
            r'<(?:div|section)[^>]*data-role="whatsnew"[^>]*>(.*?)</(?:div|section)>',
            r'<(?:div|section)[^>]*class="[^"]*whats-new[^"]*"[^>]*>(.*?)</(?:div|section)>',
        ]:
            m = _re.search(pattern, html, _re.DOTALL | _re.IGNORECASE)
            if m and m.group(1).strip():
                return self._clean_html(m.group(1).strip())
        return None

    @staticmethod
    def _clean_html(text: str) -> str:
        """移除 HTML 标签并解码实体，保留纯文本."""
        text = _re.sub(r'<br\s*/?>', '\n', text, flags=_re.IGNORECASE)
        text = _re.sub(r'<li[^>]*>', '\n- ', text, flags=_re.IGNORECASE)
        text = _re.sub(r'<[^>]+>', '', text)
        text = _re.sub(r'\n{3,}', '\n\n', text)
        text = unescape(text)
        return text.strip()
