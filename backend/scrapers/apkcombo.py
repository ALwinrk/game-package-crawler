"""APKCombo 爬虫 — /api/app 302 重定向 → 详情页版本提取.

复用 gvc/sources.py:check_apkcombo() 的核心逻辑.
"""

from __future__ import annotations

import re as _re

from backend.core.http_client import http_get
from backend.core.parser import extract_both
from backend.logging_setup import get_logger
from backend.models.schemas import ApkInfo
from backend.scrapers.base import BaseScraper

logger = get_logger()


class ApkcomboScraper(BaseScraper):
    name = "APKCombo"

    async def fetch(self, package: str) -> ApkInfo:
        """APKCombo: /api/app/<pkg> 302 → 详情页 → 提取版本.

        详情页 meta 含 "Latest Version: X.X.X"，解析器可直接提取。
        """
        api_url = f"https://apkcombo.com/api/app/{package}"
        # v2.8: 中文站详情页 URL
        cn_detail_url = f"https://apkcombo.com/zh/{package}"
        status, html = await http_get(api_url)

        if status != 200:
            return ApkInfo(
                source=self.name,
                package=package,
                error=f"HTTP {status}" if status else f"连接失败: {html[:40]}",
            )

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
        from html import unescape
        text = _re.sub(r'<br\s*/?>', '\n', text, flags=_re.IGNORECASE)
        text = _re.sub(r'<li[^>]*>', '\n- ', text, flags=_re.IGNORECASE)
        text = _re.sub(r'<[^>]+>', '', text)
        text = _re.sub(r'\n{3,}', '\n\n', text)
        text = unescape(text)
        return text.strip()
