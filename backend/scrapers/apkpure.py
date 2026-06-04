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

    def _to_cn_url(self, url: str) -> str:
        """将 APKPure URL 转为中文站: apkpure.com/slug → apkpure.com/cn/slug."""
        if "apkpure.com/cn/" in url or "apkpure.net/cn/" in url:
            return url
        if "apkpure.net/" in url:
            return url.replace("apkpure.net/", "apkpure.com/cn/")
        return url.replace("apkpure.com/", "apkpure.com/cn/", 1)

    async def _fetch_from_url(self, url: str, package: str) -> ApkInfo:
        """从指定 URL 提取版本信息."""
        status, html = await http_get(url)
        detail_url = self._to_cn_url(url)
        if status != 200:
            return ApkInfo(
                source=self.name,
                package=package,
                detail_url=detail_url,
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
                detail_url=detail_url,
                app_name=app_name,
                whats_new=whats_new,
            )
        return ApkInfo(
            source=self.name,
            package=package,
            version_code=vcode,
            detail_url=detail_url,
            error=f"仅匹配版本号 vc:{vcode}" if vcode else f"未匹配版本 ({len(html)} 字节)",
            app_name=app_name,
            whats_new=whats_new,
        )

    def _extract_app_name(self, html: str) -> str | None:
        """从 APKPure 详情页提取应用名."""
        import re as _re
        m = _re.search(r'data-dt-title\s*=\s*"([^"]+)"', html)
        if m:
            return m.group(1).strip()
        for pattern in [
            r'<h1[^>]*class="[^"]*title[^"]*"[^>]*>([^<]+)</h1>',
            r'<div[^>]*class="[^"]*app-title[^"]*"[^>]*>([^<]+)</div>',
        ]:
            m = _re.search(pattern, html, _re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return None

    def _extract_whats_new(self, html: str) -> str | None:
        """从 APKPure 详情页提取更新内容.

        策略 (按优先级):
        1. 匹配 .whats-new-container 内的 p.text 段落
        2. 匹配 .show-more-content 内的所有文本
        3. data-dt-whatsnew 属性 (fallback, 通常只有标题)
        """
        import re as _re

        # 策略 1: APKPure 标准结构 — .whats-new-container 内的 p.text
        container_match = _re.search(
            r'<div[^>]*class="[^"]*whats-new-container[^"]*"[^>]*>(.*?)</div>\s*(?:</div>)?\s*</div>\s*</div>',
            html, _re.DOTALL | _re.IGNORECASE,
        )
        if container_match:
            parts = []
            for p in _re.finditer(r'<p[^>]*class="[^"]*text[^"]*"[^>]*>(.*?)</p>', container_match.group(1), _re.DOTALL):
                text = self._clean_html(p.group(1).strip())
                if text and not _re.match(r'^last updated', text, _re.IGNORECASE):
                    parts.append(text)
            if parts:
                result = '\n'.join(parts)
                if len(result) > 30:
                    return result

        # 策略 2: .show-more-content 内的所有文本
        show_match = _re.search(
            r'<div[^>]*class="[^"]*show-more-content[^"]*"[^>]*>(.*?)</div>\s*</div>',
            html, _re.DOTALL | _re.IGNORECASE,
        )
        if show_match:
            content = self._clean_html(show_match.group(1).strip())
            if content and len(content) > 20:
                return content

        # 策略 3: data-dt-whatsnew 属性 (fallback)
        m = _re.search(r'data-dt-whatsnew\s*=\s*"([^"]*)"', html)
        if m and m.group(1).strip():
            return self._clean_html(m.group(1).strip())

        return None

    @staticmethod
    def _clean_html(text: str) -> str:
        """移除 HTML 标签并解码实体，保留纯文本."""
        import re as _re
        from html import unescape
        text = _re.sub(r'<br\s*/?>', '\n', text, flags=_re.IGNORECASE)
        text = _re.sub(r'<li[^>]*>', '\n- ', text, flags=_re.IGNORECASE)
        text = _re.sub(r'<[^>]+>', '', text)
        text = _re.sub(r'\n{3,}', '\n\n', text)
        text = unescape(text)
        return text.strip()

    def _extract_detail_url(self, html: str, pkg: str) -> str | None:
        """从 APKPure 搜索结果页提取目标 app 的详情页 URL.

        加固策略:
        1. 精确匹配完整包名在 URL 路径中 (作为路径段, 而非 URL 参数)
        2. 排除 /search 路径
        3. 多个结果时, 取第一个 (最佳匹配在前)
        4. v2.8: 中文站转换在 _to_cn_url() 统一处理
        """
        escaped = re.escape(pkg)
        pattern = r'href="((?:https?://apkpure\.com)?/[^"]*?' + escaped + r'[^"]*)"'
        candidates = []
        for m in re.finditer(pattern, html):
            url = urljoin("https://apkpure.com", m.group(1))
            if "/search" in url:
                continue
            if f"/{pkg}" in url or f"/{pkg}?" in url or url.endswith(f"/{pkg}"):
                candidates.append(url)
        if candidates:
            logger.debug("APKPure 搜索页找到 {} 个候选链接, 取第一个: {}", len(candidates), candidates[0])
            return candidates[0]
        return None
