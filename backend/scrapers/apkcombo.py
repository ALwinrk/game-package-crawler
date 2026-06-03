"""APKCombo 爬虫 — /api/app 302 重定向 → 详情页版本提取.

复用 gvc/sources.py:check_apkcombo() 的核心逻辑.
"""

from __future__ import annotations

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
        status, html = await http_get(api_url)

        if status != 200:
            return ApkInfo(
                source=self.name,
                package=package,
                error=f"HTTP {status}" if status else f"连接失败: {html[:40]}",
            )

        version, vcode = extract_both(html, package)
        if version:
            return ApkInfo(
                source=self.name,
                package=package,
                version=version,
                version_code=vcode,
                detail_url=api_url,
            )
        return ApkInfo(
            source=self.name,
            package=package,
            version_code=vcode,
            detail_url=api_url,
            error=f"仅匹配版本号 vc:{vcode}" if vcode else f"未匹配版本 ({len(html)} 字节)",
        )
