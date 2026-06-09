"""下载链接提取 — 静态提取为主，Playwright 网络拦截为补充.

设计文档 5.1.6 节：APKPure/APKCombo 的 JS 动态下载链接通过 Playwright 无头浏览器捕获。
策略：优先使用 HTML 解析（快速），失败时回退到 Playwright 点击+网络拦截（可靠）。
"""

from __future__ import annotations

import re
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


# ── APKPure ──────────────────────────────────────────────

def _extract_slug_from_url(url: str) -> str:
    """从详情页 URL 提取 slug.

    例: https://apkpure.com/pubg-mobile-for-android-2025/com.tencent.ig
        → pubg-mobile-for-android-2025
        https://apkcombo.com/pubg-mobile/com.tencent.ig/
        → pubg-mobile
        https://apkcombo.com/zh/com.tencent.ig
        → ""  (仅语言码+包名, 无 slug, 回退到包名直连)
        https://apkcombo.com/en/game-slug/com.test.app
        → game-slug  (三段 URL: 语言码/真slug/包名)

    API 格式 (如 /api/app/{pkg}) 无法提取 slug，返回空字符串。
    """
    url_clean = url.rstrip("/")
    skip_segments = {"api", "app", "search", "download"}
    lang_codes = {"zh", "en", "fr", "de", "ja", "ko", "pt", "es", "ru", "ar",
                  "vi", "th", "id", "tr", "it", "nl", "pl", "hi", "bn", "cn"}

    # 提取域名后的所有路径段
    m = re.search(r'https?://[^/]+/(.*)$', url_clean)
    if not m:
        return ""
    parts = [p for p in m.group(1).split("/") if p]
    if len(parts) < 2:
        return ""

    # 去掉包名段（最后一段）
    *prefix, pkg = parts

    # 去掉 API/语言码前缀，取最后一个作为 slug
    for seg in reversed(prefix):
        if seg.lower() not in skip_segments and seg.lower() not in lang_codes:
            return seg
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


# ── 下载页 URL 生成 (v3.3: 前端"浏览器下载页"按钮) ──────

def get_download_page_url(source: str, detail_url: str, package: str = "", version: str = "") -> str:
    """根据来源生成浏览器下载页 URL（用户手动下载）."""
    slug = _extract_slug_from_url(detail_url)
    ver = version or "latest"
    if source == "APKPure":
        if slug:
            return f"https://apkpure.com/cn/{slug}/{package}/download"
        return f"https://apkpure.com/cn/{package}"
    elif source == "APKCombo":
        if slug:
            return f"https://apkcombo.com/zh/{slug}/{package}/download/phone-{ver}-apk"
        return f"https://apkcombo.com/zh/{package}/download"
    elif source == "APKMirror":
        return detail_url  # 详情页就是下载入口
    elif source == "APKVision":
        return detail_url  # 同上
    else:
        return detail_url


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
