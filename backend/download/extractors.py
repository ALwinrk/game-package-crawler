"""下载链接提取 — 静态提取为主，Playwright 网络拦截为补充.

设计文档 5.1.6 节：APKPure/APKCombo 的 JS 动态下载链接通过 Playwright 无头浏览器捕获。
策略：优先使用 HTML 解析（快速），失败时回退到 Playwright 点击+网络拦截（可靠）。
"""

from __future__ import annotations

import re
import asyncio
import base64
import threading
import queue
from dataclasses import dataclass
from urllib.parse import urlparse, urljoin

from backend.logging_setup import get_logger

logger = get_logger()


@dataclass
class DownloadVariant:
    """单个下载变体."""
    url: str
    arch: str           # arm64-v8a / armeabi-v7a / universal / unknown
    size: str = ""
    source: str = ""


# ── 架构检测 ────────────────────────────────────────────

ARCH_64BIT: set[str] = {"arm64-v8a", "arm64", "aarch64", "arm64_v8a"}
ARCH_32BIT: set[str] = {"armeabi-v7a", "armeabi", "arm", "armeabi_v7a"}
ARCH_UNIVERSAL: set[str] = {"universal", "all", "nodpi"}


def detect_arch(text: str) -> str:
    """从文件名或页面文本判断 APK 架构."""
    lower = text.lower().replace("_", "-").replace(" ", "-")
    for arch in ARCH_64BIT:
        if arch in lower:
            return "arm64-v8a"
    for arch in ARCH_32BIT:
        if arch in lower:
            return "armeabi-v7a"
    for arch in ARCH_UNIVERSAL:
        if arch in lower:
            return "universal"
    if "x86_64" in lower or "x64" in lower:
        return "x86_64"
    if "x86" in lower and "x86_64" not in lower:
        return "x86"
    return "unknown"


def pick_best_variant(variants: list[DownloadVariant]) -> DownloadVariant | None:
    """从变体列表中选最佳 (arm64-v8a > universal > armeabi-v7a)."""
    if not variants:
        return None
    arch_rank = {
        "arm64-v8a": 0, "universal": 1, "x86_64": 2,
        "unknown": 3, "x86": 4, "armeabi-v7a": 5,
    }
    return max(variants, key=lambda v: (-arch_rank.get(v.arch, 99), v.url))


# ── 通用：浏览器模拟点击获取下载链接 ──────────────────────

def _browser_click_capture(
    url: str,
    click_selectors: list[str],
    wait_ms: int = 5000,
    use_proxy: bool = True,
) -> str | None:
    """使用 Chromium 浏览器打开页面 → 点击下载按钮 → 捕获真实下载链接.

    策略：
    1. 拦截新打开的页面/标签页（下载链接可能在 popup 中）
    2. 找不到 popup 则从当前页面提取 .apk 直链
    3. 兜底：监听页面中的下载链接变化

    Args:
        url: 详情页 URL.
        click_selectors: 优先尝试的 CSS 选择器列表.
        wait_ms: 点击后等待毫秒数.
        use_proxy: 是否使用代理.

    Returns:
        下载直链 URL 或 None.
    """
    from backend.core.http_client import get_chromium_executable
    from backend.config import get_settings

    settings = get_settings()
    chrome_exe = get_chromium_executable()

    proxy_config = None
    if use_proxy and settings.proxy:
        proxy_config = {"server": settings.proxy}

    result_queue: queue.Queue = queue.Queue()

    def _worker():
        try:
            from patchright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    executable_path=chrome_exe,
                    args=["--no-sandbox", "--disable-setuid-sandbox"],
                )
                context_options = {
                    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                }
                if proxy_config:
                    context_options["proxy"] = proxy_config

                context = browser.new_context(**context_options)
                page = context.new_page()

                # 监听新页面（下载链接可能在弹窗/新标签中）
                popup_urls: list[str] = []

                def _handle_popup(popup):
                    popup.wait_for_load_state("domcontentloaded", timeout=10000)
                    pu = popup.url
                    if pu and pu != url and pu != "about:blank" and _is_valid_download_url(pu):
                        popup_urls.append(pu)

                context.on("page", _handle_popup)

                # 访问页面
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)

                # 尝试点击下载按钮
                clicked = False
                for selector in click_selectors:
                    try:
                        btn = page.locator(selector).first
                        if btn.is_visible(timeout=2000):
                            btn.click()
                            clicked = True
                            logger.info("点击下载按钮: {}", selector)
                            break
                    except Exception:
                        continue

                if not clicked:
                    # 没找到按钮，尝试直接提取
                    content = page.content()
                    result_queue.put(_extract_first_apk_url(content, url))
                    browser.close()
                    return

                # 等待下载链接出现
                page.wait_for_timeout(wait_ms)

                # 检查是否有弹窗 URL（已在 _handle_popup 中过滤）
                if popup_urls:
                    result_queue.put(popup_urls[0])
                    browser.close()
                    return

                # 从当前页面提取 .apk 链接
                content = page.content()
                apk_url = _extract_first_apk_url(content, url)
                if apk_url:
                    result_queue.put(apk_url)
                else:
                    # 兜底：检查页面 URL 是否变成了下载链接
                    current_url = page.url
                    if current_url != url and ".apk" in current_url.lower():
                        result_queue.put(current_url)
                    else:
                        result_queue.put(None)

                browser.close()

        except Exception as e:
            logger.warning("浏览器点击捕获失败: {}", e)
            result_queue.put(None)

    worker = threading.Thread(target=_worker, daemon=True)
    worker.start()
    worker.join(timeout=60)

    try:
        return result_queue.get_nowait()
    except queue.Empty:
        return None


def _extract_first_apk_url(html: str, base_url: str) -> str | None:
    """从 HTML 中提取第一个 APK 下载链接."""
    # 优先匹配 d.apkpure.net / download.apkcombo.com 等已知 CDN
    for pattern in [
        r'https?://d\.apkpure\.net/[^\s"\'<>]+',
        r'https?://download\.apkcombo\.com/[^\s"\'<>]+',
        r'https?://[^\s"\'<>]*\.apk[^\s"\'<>]*',
    ]:
        matches = re.findall(pattern, html)
        if matches:
            return matches[0]

    # 通用: 找以 .apk 结尾的链接
    m = re.search(r'href="([^"]*\.apk[^"]*)"', html, re.IGNORECASE)
    if m:
        href = m.group(1)
        if href.startswith("//"):
            return f"https:{href}"
        if not href.startswith("http"):
            return urljoin(base_url, href)
        return href

    return None



# ── Playwright 网络拦截捕获（设计文档 5.1.6 节）─────────────────

async def _playwright_capture_apk_urls(
    url: str,
    click_selectors: list[str],
    wait_ms: int = 5000,
) -> list[str]:
    captured_urls: list[str] = []
    seen = set()
    try:
        from backend.core.browser_manager import get_browser_manager
        mgr = get_browser_manager()
        if not mgr.available:
            return []
        page, sem = await mgr.new_page()
        try:
            async def _on_response(response):
                resp_url = response.url
                if resp_url in seen:
                    return
                if _is_valid_download_url(resp_url):
                    seen.add(resp_url)
                    captured_urls.append(resp_url)

            page.on("response", _on_response)
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)

            clicked = False
            for selector in click_selectors:
                try:
                    btn = page.locator(selector).first
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        clicked = True
                        break
                except Exception:
                    continue

            if clicked:
                await page.wait_for_timeout(wait_ms)
            elif not captured_urls:
                c = await page.content()
                u = _extract_first_apk_url(c, url)
                if u:
                    captured_urls.append(u)
        finally:
            await mgr.close_page(page, sem)
    except RuntimeError:
        pass
    except Exception as e:
        logger.warning("Playwright 拦截异常: {}", e)
    return captured_urls


# ── APKPure ──────────────────────────────────────────────

def _extract_slug_from_url(url: str) -> str:
    """从详情页 URL 提取 slug.

    例: https://apkpure.com/pubg-mobile-for-android-2025/com.tencent.ig
        → pubg-mobile-for-android-2025
        https://apkcombo.com/pubg-mobile/com.tencent.ig/
        → pubg-mobile

    API 格式 (如 /api/app/{pkg}) 无法提取 slug，返回空字符串。
    """
    url_clean = url.rstrip("/")
    # 排除 API/非详情页路径
    skip_segments = {"api", "search", "download"}
    m = re.search(r'https?://[^/]+/([^/]+)/([^/]+)$', url_clean)
    if m:
        slug = m.group(1)
        if slug.lower() in skip_segments:
            return ""
        return slug
    return ""


async def extract_apkpure_links(detail_url: str, package: str = "", version: str = "") -> list[DownloadVariant]:
    """APKPure 浏览器下载页 — 构造 https://apkpure.com/cn/{slug}/{package}/download"""
    slug = _extract_slug_from_url(detail_url)
    if not slug:
        return []
    dl_url = f"https://apkpure.com/cn/{slug}/{package}/download"
    logger.info("APKPure 浏览器下载页: {}", dl_url)
    return [DownloadVariant(url=dl_url, arch="unknown", source="APKPure")]


# ── APKCombo ─────────────────────────────────────────────

async def extract_apkcombo_links(detail_url: str, package: str = "", version: str = "") -> list[DownloadVariant]:
    """APKCombo 浏览器下载页 — 构造 https://apkcombo.com/zh/{slug}/{package}/download/phone-{version}-apk

    若 slug 无法从 detail_url 提取（如 API 格式 /api/app/{pkg}），
    回退使用包名直连: https://apkcombo.com/zh/{package}/download
    """
    slug = _extract_slug_from_url(detail_url)
    ver = version or "latest"
    if slug:
        dl_url = f"https://apkcombo.com/zh/{slug}/{package}/download/phone-{ver}-apk"
    else:
        dl_url = f"https://apkcombo.com/zh/{package}/download"
    logger.info("APKCombo 浏览器下载页: slug={} → {}", slug or "(无)", dl_url)
    return [DownloadVariant(url=dl_url, arch="unknown", source="APKCombo")]


# ── APKMirror (保持原有逻辑) ──────────────────────────────

async def extract_apkmirror_links(detail_url: str) -> list[DownloadVariant]:
    """APKMirror 下载链接提取 (多步跳转)."""
    from backend.core.http_client import stealth_get

    variants: list[DownloadVariant] = []
    status, html = await stealth_get(detail_url)
    if status != 200:
        return []

    download_m = re.search(r'href="(/apk/[^"]+?/download/[^"]*)"', html)
    if not download_m:
        return []

    download_url = download_m.group(1)
    parsed = urlparse(detail_url)
    if not download_url.startswith("http"):
        download_url = f"{parsed.scheme}://{parsed.netloc}{download_url}"

    status, html = await stealth_get(download_url)
    if status != 200:
        return []

    seen_urls = set()
    for m in re.finditer(r'href="([^"]*?\.apk[^"]*)"[^>]*>([^<]*?)</a>', html):
        url = m.group(1)
        label = m.group(2).strip()
        if url in seen_urls:
            continue
        seen_urls.add(url)
        if not url.startswith("http"):
            if url.startswith("//"):
                url = f"{parsed.scheme}:{url}"
            else:
                url = f"{parsed.scheme}://{parsed.netloc}{url}"
        variants.append(DownloadVariant(url=url, arch=detect_arch(f"{url} {label}"), source="APKMirror"))

    return variants


# ── APKVision (保持原有逻辑) ──────────────────────────────

async def extract_apkvision_links(detail_url: str) -> list[DownloadVariant]:
    """APKVision 详情页下载链接提取."""
    from backend.core.http_client import stealth_get
    status, html = await stealth_get(detail_url)
    if status != 200:
        return []

    variants: list[DownloadVariant] = []
    seen_urls = set()
    for m in re.finditer(r'href="([^"]*?\.apk[^"]*)"[^>]*>([^<]*?)<', html):
        url = m.group(1)
        label = m.group(2).strip()
        if url in seen_urls:
            continue
        seen_urls.add(url)
        variants.append(DownloadVariant(url=url, arch=detect_arch(f"{url} {label}"), source="APKVision"))
    return variants


# ── URL 验证 ─────────────────────────────────────────────

def _is_valid_download_url(url: str) -> bool:
    """过滤无效 URL（图标、CSS、JS 等非 APK 下载链接）.

    APKCombo 的下载网关使用 ogimgs.apkcombo.org / apkcombo.com 等子域名，
    这些是有效的下载服务端点，不在过滤范围内。
    """
    if not url:
        return False
    # APKCombo 和 APKPure 的合法下载子域名
    valid_domains = [
        "apkcombo.com", "apkcombo.org", "apkpure.net", "apkpure.com",
        "apkmirror.com", "apkvision.org", "apkdl.com",
    ]
    url_lower = url.lower()
    # 先检查黑名单，再检查白名单
    invalid_prefixes = [
        "imgrs.", "ogimgs.", "m.apkpure",
        "doubleclick", "googlesyndication", "google-analytics",
    ]
    for d in invalid_prefixes:
        if d in url_lower:
            return False
    # 属于已知有效域名 → 放行
    for d in valid_domains:
        if d in url_lower:
            return True
    # 排除静态资源扩展名
    invalid_exts = [".jpg", ".jpeg", ".png", ".gif", ".svg", ".ico", ".css", ".js", ".php"]
    for ext in invalid_exts:
        if url_lower.rstrip("/").endswith(ext):
            return False
    return True


# ── 源映射 ───────────────────────────────────────────────

EXTRACTOR_MAP: dict[str, callable] = {
    "APKPure": extract_apkpure_links,
    "APKCombo": extract_apkcombo_links,
    "APKMirror": extract_apkmirror_links,
    "APKVision": extract_apkvision_links,
}


async def extract_download_links(source_name: str, detail_url: str, package: str = "", version: str = "") -> list[DownloadVariant]:
    """从指定源的详情页提取所有下载变体."""
    extractor = EXTRACTOR_MAP.get(source_name)
    if not extractor:
        return []
    try:
        if source_name in ("APKPure", "APKCombo"):
            return await extractor(detail_url, package=package, version=version)
        return await extractor(detail_url)
    except Exception as e:
        logger.warning("下载链接提取失败 [{}]: {}", source_name, e)
        return []
