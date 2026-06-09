"""APKPure 爬虫 — 搜索页 → 详情页两步提取，绕过 Cloudflare.

复用 gvc/sources.py:check_apkpure() 的核心逻辑.
"""

from __future__ import annotations

import asyncio as _asyncio
import random as _random
import re as _re
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
        """APKPure: 搜索页 (JS渲染) → 详情页 URL → 详情页提取版本.

        v3.3: 请求前随机延迟 0.5-2.0s, 降低单包名排查时的频率特征.
        """
        await _asyncio.sleep(_random.uniform(0.5, 2.0))
        search_url = f"https://apkpure.net/search?q={package}"

        # Step 1: Fetcher 获取搜索页
        status, html = await http_get(search_url)
        fetcher_ok = status == 200 and not is_cloudflare_block(html)

        if not fetcher_ok:
            # 回退到 apkpure.com
            return await self._fetch_from_url(
                f"https://apkpure.com/search?q={package}", package,
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

        # Step 5: 兜底 — .com 搜索页 (v3.5: 主域名已切 .net)
        result = await self._fetch_from_url(
            f"https://apkpure.com/search?q={package}", package,
        )
        if not result.ok:
            # 最后尝试详情页直连 (apkpure.net/cn/{package})
            result = await self._fetch_from_url(
                f"https://apkpure.net/cn/{package}", package,
            )
        return result

    def _to_cn_url(self, url: str) -> str:
        """将 APKPure URL 转为中文站: apkpure.net/slug → apkpure.net/cn/slug.

        v3.5: 主域名切换为 .net (apkpure.com 被 CF interactive Turnstile 拦截).
        """
        if "apkpure.net/cn/" in url or "apkpure.com/cn/" in url:
            return url
        if "apkpure.com/" in url:
            return url.replace("apkpure.com/", "apkpure.net/cn/")
        return url.replace("apkpure.net/", "apkpure.net/cn/", 1)

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
        """从 APKPure 详情页提取应用名.

        v3.5: apkpure.net 上 data-dt-title 不是应用名, h1 无 class,
        改用 h1 文本兜底.
        """
        # 策略 1: h1 标签 (apkpure.net 通用)
        m = _re.search(r'<h1[^>]*>([^<]+)</h1>', html, _re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            if len(name) > 1:
                return name
        # 策略 2: data-dt-title (apkpure.com 旧版)
        m = _re.search(r'data-dt-title\s*=\s*"([^"]+)"', html)
        if m:
            val = m.group(1).strip()
            if val and val not in ("home", "nav_game", "nav_app"):
                return val
        # 策略 3: class 选择器回退
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

        v3.5 策略 (apkpure.net 适配):
        1. .whats-new 或 [class*='whats-new'] 元素内容
        2. .whats-new-container 内的 p.text 段落 (apkpure.com 旧版)
        3. .show-more-content 回退
        4. data-dt-whatsnew 属性 (fallback)
        """
        # 策略 1: .whats-new 元素 (apkpure.net 标准)
        for sel in (r'<div[^>]*class="[^"]*whats-new[^"]*"[^>]*>(.*?)</div>',
                     r'<div[^>]*class="[^"]*whats-new-container[^"]*"[^>]*>(.*?)</div>\s*(?:</div>)?\s*</div>\s*</div>'):
            m = _re.search(sel, html, _re.DOTALL | _re.IGNORECASE)
            if m:
                parts = []
                for p in _re.finditer(r'<p[^>]*class="[^"]*text[^"]*"[^>]*>(.*?)</p>', m.group(1), _re.DOTALL):
                    text = self._clean_html(p.group(1).strip())
                    if text and not _re.match(r'^last updated', text, _re.IGNORECASE):
                        parts.append(text)
                if not parts:
                    content = self._clean_html(m.group(1).strip())
                    if content and len(content) > 30:
                        # 去掉 "最新版本X.X.X的更新日志" 前缀
                        content = _re.sub(r'^最新版本[\d.]+的更新日志\s*', '', content)
                        return content
                if parts:
                    result = '\n'.join(parts)
                    if len(result) > 30:
                        return result

        # 策略 2: .show-more-content 回退 (通常是游戏描述, 非更新内容)
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
        """从 APKPure 搜索结果页提取目标 app 的详情页 URL (v2.8.1: 多模式).

        加固策略:
        1. 精确匹配完整包名在 URL 路径中 (作为路径段, 而非 URL 参数)
        2. 排除 /search 路径
        3. 多个结果时, 取第一个 (最佳匹配在前)
        4. 多域名格式兼容 (apkpure.com / apkpure.net)
        5. v2.8: 中文站转换在 _to_cn_url() 统一处理
        """
        escaped = _re.escape(pkg)

        # 模式 1: 标准链接格式 (双引号, apkpure.com)
        pattern = r'href="((?:https?://apkpure\.(?:com|net))?/[^"]*?' + escaped + r'[^"]*)"'
        candidates = []
        for m in _re.finditer(pattern, html):
            url = urljoin("https://apkpure.net", m.group(1))
            if "/search" in url:
                continue
            if f"/{pkg}" in url or f"/{pkg}?" in url or url.endswith(f"/{pkg}"):
                candidates.append(url)

        # 模式 2: 单引号链接
        if not candidates:
            pattern2 = r"href='((?:https?://apkpure\.(?:com|net))?/[^']*?" + escaped + r"[^']*)'"
            for m in _re.finditer(pattern2, html):
                url = urljoin("https://apkpure.net", m.group(1))
                if "/search" not in url:
                    candidates.append(url)

        # 模式 3: 相对路径 (不带域名)
        if not candidates:
            pattern3 = r'href="(/(?:[^"]*?/)?' + escaped + r'[^"]*)"'
            for m in _re.finditer(pattern3, html):
                url = urljoin("https://apkpure.net", m.group(1))
                if "/search" not in url:
                    candidates.append(url)

        if candidates:
            logger.debug("APKPure 搜索页找到 {} 个候选链接, 取第一个: {}", len(candidates), candidates[0])
            return candidates[0]
        return None
