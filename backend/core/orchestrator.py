"""爬取调度器 — 快/慢两级并发，聚合结果，版本对比."""

from __future__ import annotations

import asyncio

from backend.config import get_settings
from backend.logging_setup import get_logger
from backend.models.schemas import ApkInfo, CompareStatus, FetchResult
from backend.scrapers.base import BaseScraper
from backend.scrapers.google_play import GooglePlayScraper
from backend.scrapers.apkpure import ApkpureScraper
from backend.scrapers.apkcombo import ApkcomboScraper
from backend.scrapers.apkmirror import ApkmirrorScraper
from backend.scrapers.apkvision import ApkvisionScraper
import re as _re

from backend.core.version import best_version, best_version_code, compare_version_codes, is_plausible_version

logger = get_logger()


def _is_placeholder_whats_new(text: str) -> bool:
    """检测 Google Play 的占位符更新内容，视为无效."""
    if not text or not text.strip():
        return True
    t = text.strip().lower()
    patterns = [
        r"what'?s new in the latest",        # "What's new in the latest 4.4.0" 等
        r"^whats new[!.]*$",
        r"^no recent changes[!.]*$",
        r"^暂无更新[!.]*$",
        r"^last updated on [\d\-]+$",        # 仅日期行，无实际内容
    ]
    for p in patterns:
        if _re.search(p, t):
            return True
    if _re.match(r'^[\d\.\s\-]+$', t):
        return True
    return False

# ── 站点分组 ───────────────────────────────────────────────

# 快速源: Fetcher 后端，秒级响应
FAST_SCRAPERS: dict[str, type[BaseScraper]] = {
    "google_play": GooglePlayScraper,
    "apkpure": ApkpureScraper,
    "apkcombo": ApkcomboScraper,
}

# 慢速源: StealthySession 浏览器渲染，需绕过 Cloudflare
SLOW_SCRAPERS: dict[str, type[BaseScraper]] = {
    "apkmirror": ApkmirrorScraper,
    "apkvision": ApkvisionScraper,
}

# 全部
ALL_SCRAPERS: dict[str, type[BaseScraper]] = {**FAST_SCRAPERS, **SLOW_SCRAPERS}


def _get_scrapers(from_group: dict[str, type[BaseScraper]]) -> list[BaseScraper]:
    """根据配置筛选已启用的爬虫实例."""
    settings = get_settings()
    enabled = []
    for name in settings.enabled_sites:
        cls = from_group.get(name)
        if cls:
            enabled.append(cls())
    return enabled


async def _fetch_scrapers(
    package: str,
    scrapers: list[BaseScraper],
) -> dict[str, ApkInfo]:
    """通用爬取逻辑：并发查询，重试，聚合.

    Args:
        package: Android 包名.
        scrapers: 爬虫实例列表.

    Returns:
        {source_name: ApkInfo} 字典.
    """
    settings = get_settings()
    if not scrapers:
        return {}

    semaphore = asyncio.Semaphore(settings.scraper_concurrency)

    async def _fetch_one(scraper: BaseScraper) -> ApkInfo:
        async with semaphore:
            try:
                for attempt in range(settings.retry_times + 1):
                    result = await scraper.fetch(package)
                    if result.ok or attempt == settings.retry_times:
                        return result
                    logger.debug(
                        "{} 第 {}/{} 次重试: {}",
                        scraper.name, attempt + 1, settings.retry_times, package,
                    )
                    await asyncio.sleep(settings.retry_delay)
                return result
            except Exception as e:
                logger.warning("{} 查询异常: {} — {}", scraper.name, package, e)
                return ApkInfo(
                    source=scraper.name,
                    package=package,
                    error=f"{type(e).__name__}: {e!s}"[:100],
                )

    tasks = [_fetch_one(s) for s in scrapers]
    results_list = await asyncio.gather(*tasks)

    results: dict[str, ApkInfo] = {}
    for info in results_list:
        results[info.source] = info
    return results


def _build_fetch_result(
    package: str,
    results: dict[str, ApkInfo],
    expected_version: str | None = None,
    expected_version_code: str | None = None,
) -> FetchResult:
    """从爬取结果构建 FetchResult，含版本对比."""
    versions: list[str] = []
    codes: list[str] = []

    for info in results.values():
        # v3.8: 防御性检查 — 跳过爬虫返回的错误包名数据
        if info.package and info.package != package:
            logger.warning("爬虫 {} 返回了错误包名: {} ≠ {}，已跳过", info.source, info.package, package)
            continue
        if info.version and not info.error and is_plausible_version(info.version):
            versions.append(info.version)
        elif info.version and not info.error:
            logger.debug("过滤不合理版本: {} → {}", info.source, info.version)
        if info.version_code and not info.error:
            codes.append(info.version_code)

    google_version = results.get("Google Play", ApkInfo(source="", package=package)).version
    best_v = best_version(versions, google_version)
    best_vc = best_version_code(codes)

    # ── 版本名对比 ──
    vn_status = CompareStatus.NOT_FOUND
    vn_detail = ""
    if best_v:
        vn_status = CompareStatus.MATCHED
        if expected_version and best_v:
            from backend.core.version import compare_versions, normalize
            cmp = compare_versions(best_v, expected_version)
            if cmp == 1:
                vn_status = CompareStatus.NEWER
                vn_detail = f"{expected_version} → {best_v}"
            elif cmp == -1:
                vn_status = CompareStatus.OLDER
                vn_detail = f"{expected_version} → {best_v}"
            elif normalize(best_v) != normalize(expected_version):
                vn_status = CompareStatus.NEWER
                vn_detail = f"{expected_version} → {best_v}"
            else:
                vn_detail = f"版本名一致 ({best_v})"
        else:
            vn_detail = best_v

    # ── 版本号对比 ──
    vc_status = CompareStatus.NOT_FOUND
    vc_detail = ""
    if best_vc:
        vc_status = CompareStatus.MATCHED
        if expected_version_code and best_vc:
            cmp = compare_version_codes(expected_version_code, best_vc)
            if cmp == -1:
                vc_status = CompareStatus.NEWER
                vc_detail = f"vc:{expected_version_code} → vc:{best_vc}"
            elif cmp == 1:
                vc_status = CompareStatus.OLDER
                vc_detail = f"vc:{expected_version_code} → vc:{best_vc}"
            elif cmp == 0:
                vc_detail = f"版本号一致 (vc:{best_vc})"
            else:
                vc_detail = f"vc:{best_vc}"
        else:
            vc_detail = f"vc:{best_vc}"
    elif best_vc is None and expected_version_code:
        vc_status = CompareStatus.NOT_FOUND
        vc_detail = f"期望 vc:{expected_version_code}，未获取到线上版本号"

    # ── 综合状态：优先 version_code，其次 version_name ──
    if vc_status != CompareStatus.NOT_FOUND:
        compare_status = vc_status
    else:
        compare_status = vn_status

    # ── 聚合 app_name 和 whats_new (v2.6) ──
    # app_name 优先级: Google Play > APKPure > APKCombo
    name_priority = ["Google Play", "APKPure", "APKCombo"]
    best_app_name = None
    for name in name_priority:
        info = results.get(name)
        if info and not info.error and info.app_name:
            best_app_name = info.app_name
            break

    # whats_new 优先级: APKPure > APKCombo > Google Play（均过滤占位符）
    whats_new_priority = ["APKPure", "APKCombo", "Google Play"]
    best_whats_new = None
    for name in whats_new_priority:
        info = results.get(name)
        if info and not info.error and info.whats_new:
            if _is_placeholder_whats_new(info.whats_new):
                continue
            best_whats_new = info.whats_new
            break

    return FetchResult(
        package=package,
        expected_version=expected_version,
        expected_version_code=expected_version_code,
        results=results,
        best_version=best_v or None,
        best_version_code=best_vc or None,
        compare_status=compare_status,
        version_name_compare=f"{vn_status.value}:{vn_detail}" if vn_detail else None,
        version_code_compare=f"{vc_status.value}:{vc_detail}" if vc_detail else None,
        app_name=best_app_name,
        whats_new=best_whats_new,
    )


# ── 公开 API ────────────────────────────────────────────────


async def query_fast(
    package: str,
    expected_version: str | None = None,
    expected_version_code: str | None = None,
    force: bool = False,
) -> FetchResult:
    """快速排查 — Google Play + APKPure + APKCombo（秒级响应）."""
    from backend.core.cache import get_scraper_cache

    cache = get_scraper_cache()
    if not force:
        cached = await cache.get(package, "fast")
        if cached is not None:
            return cached

    scrapers = _get_scrapers(FAST_SCRAPERS)
    if not scrapers:
        return FetchResult(
            package=package,
            error="无启用的快速源",
            compare_status=CompareStatus.ERROR,
        )
    results = await _fetch_scrapers(package, scrapers)
    result = _build_fetch_result(package, results, expected_version, expected_version_code)
    await cache.set(package, "fast", result)
    return result


async def query_slow(
    package: str,
    expected_version: str | None = None,
    expected_version_code: str | None = None,
    force: bool = False,
) -> FetchResult:
    """慢速排查 — APKMirror + APKVision（浏览器渲染，需 30-90s）."""
    from backend.core.cache import get_scraper_cache

    cache = get_scraper_cache()
    if not force:
        cached = await cache.get(package, "slow")
        if cached is not None:
            return cached

    scrapers = _get_scrapers(SLOW_SCRAPERS)
    if not scrapers:
        return FetchResult(
            package=package,
            error="无启用的慢速源",
            compare_status=CompareStatus.ERROR,
        )
    results = await _fetch_scrapers(package, scrapers)
    result = _build_fetch_result(package, results, expected_version, expected_version_code)
    await cache.set(package, "slow", result)
    return result


async def query_single(
    package: str,
    expected_version: str | None = None,
    expected_version_code: str | None = None,
    force: bool = False,
) -> FetchResult:
    """全量排查 — 所有启用的站点（快速 + 慢速）."""
    from backend.core.cache import get_scraper_cache

    cache = get_scraper_cache()
    if not force:
        cached = await cache.get(package, "all")
        if cached is not None:
            return cached

    scrapers = _get_scrapers(ALL_SCRAPERS)
    if not scrapers:
        return FetchResult(
            package=package,
            error="无启用的数据源",
            compare_status=CompareStatus.ERROR,
        )
    results = await _fetch_scrapers(package, scrapers)
    result = _build_fetch_result(package, results, expected_version, expected_version_code)
    await cache.set(package, "all", result)
    return result


async def query_batch(
    packages: list[tuple[str, str | None, str | None]],
    mode: str = "fast",  # fast / slow / all
    progress_callback=None,
    stop_event: asyncio.Event | None = None,
) -> list[FetchResult]:
    """批量查询多个包名.

    Args:
        packages: [(package, expected_version, expected_version_code), ...]
        mode: 排查模式 (fast / slow / all).
        progress_callback: async fn(index, total, result).
        stop_event: 暂停/取消事件.

    Returns:
        FetchResult 列表.
    """
    query_fn = {"fast": query_fast, "slow": query_slow, "all": query_single}.get(mode, query_fast)

    settings = get_settings()
    concurrency = getattr(settings, "batch_concurrency", 5)
    semaphore = asyncio.Semaphore(concurrency)
    total = len(packages)

    async def _process_one(idx: int, pkg: str, ev: str | None, evc: str | None):
        if stop_event and stop_event.is_set():
            return None
        async with semaphore:
            if stop_event and stop_event.is_set():
                return None
            result = await query_fn(pkg, ev, evc)
            if progress_callback:
                await progress_callback(idx + 1, total, result)
            return result

    tasks = [
        _process_one(i, pkg, ev, evc)
        for i, (pkg, ev, evc) in enumerate(packages)
    ]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]
