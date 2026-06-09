"""定时抓取服务 — APKPure / APKCombo 最新更新列表, 带熔断与事务保护 (v2.8.2).

v2.8.2: 增加详情页抓取 — 获取图标/真实更新时间/详情页链接.
"""

from __future__ import annotations

import asyncio
import random
import re
import threading
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, parse_qs

from bs4 import BeautifulSoup

from backend.config import get_settings
from backend.core.http_client import http_get, stealth_get
from backend.db.database import get_connection
from backend.logging_setup import get_logger

logger = get_logger()

_last_modified: datetime | None = None
_last_modified_lock = threading.Lock()
_DETAIL_SEMAPHORE = asyncio.Semaphore(5)  # 详情页并发限制


def set_last_modified(dt: datetime) -> None:
    with _last_modified_lock:
        global _last_modified
        _last_modified = dt


def get_last_modified() -> datetime | None:
    with _last_modified_lock:
        return _last_modified


# v3.2: 砍掉低价值分类 (卡牌/赌场/知识问答/文字/音乐/益智/教育/桌面棋类)
APKPURE_CATEGORIES = [
    "android-games", "action-games", "adventure-games", "arcade-games",
    "casual-games", "racing-games", "role-playing-games", "simulation-games",
    "sports-games", "strategy-games",
]

APKPURE_SELECTORS = {
    "container": [".ranking-apk-item[data-dt-app]"],
    "icon": ["img.app-icon", "img.lazy", "img[src]"],
    "app_name": ["a.icon[title]", "a[title]"],
    "package_name": ["data-dt-app"],
}

# 排除关键词: 休闲益智/纸牌/赌场/音乐/知识问答/文字/教育类游戏
_APKCOMBO_EXCLUDE_KEYWORDS = [
    "solitaire", "puzzle", "word", "trivia", "quiz", "casino", "bingo",
    "mahjong", "sudoku", "domino", "card", "poker", "slot", "roulette",
    "blackjack", "ludo", "chess", "checkers", "board", "music", "piano",
    "coloring", "drawing", "painting", "educational", "kids", "baby",
    "coloring book", "match 3", "merge", "dress up", "makeover",
    "接龙", "纸牌", "拼图", "填字", "数独", "麻将", "音乐", "涂色",
]
_APKCOMBO_EXCLUDE_KEYWORDS.extend([
    s.capitalize() for s in _APKCOMBO_EXCLUDE_KEYWORDS
])

APKCOMBO_SELECTORS = {
    "container": [".content-gapps a[href*='/com.']", ".content-apps a[href*='/com.']"],
    "icon": ["figure img.lzl", "figure img[data-src]", "figure img"],
    "app_name": ["p"],
    "download_count": ["p:nth-of-type(2)"],
    "package_name": ["href"],
}

_PKG_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9_.]{1,127}$')
_CN_DATE_RE = re.compile(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日')


def _parse_cn_date(text: str) -> str | None:
    """解析中文日期格式: 2026年06月08日 → YYYY-MM-DD."""
    m = _CN_DATE_RE.search(text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime(y, mo, d).strftime("%Y-%m-%d")
        except ValueError:
            return None
    return None


async def _fetch_page(url: str, retries: int = 2) -> tuple[int, str]:
    status, html = await http_get(url)
    if status == 200 and len(html) > 500:
        return status, html
    for _ in range(retries):
        await asyncio.sleep(random.uniform(1.2, 2.5))
        status, html = await stealth_get(url)
        if status == 200 and len(html) > 500:
            return status, html
    return status, html


def _extract_icon(soup, selectors: list[str]) -> str:
    """从元素中提取图标 URL."""
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            src = el.get("data-original") or el.get("data-src") or el.get("src", "")
            if src and len(src) > 20 and not src.endswith("1.gif") and "base64" not in src:
                return src
    return ""


def _extract_attr(el, attr: str) -> str:
    """安全提取元素属性."""
    if hasattr(el, "get"):
        return str(el.get(attr, "") or "")
    return ""


def _parse_apkpure_html(html: str) -> list[dict]:
    """解析 APKPure 排名页面: cn/ranking/latest-updated-android-games.

    页面按游戏分类展示，提取所有分类下的游戏。
    去重: 使用 set 按 package_name 去重。
    """
    items: list[dict] = []
    soup = BeautifulSoup(html, "html.parser")
    seen_pkgs: set[str] = set()
    for item in soup.select(APKPURE_SELECTORS["container"][0]):
        # 从 data-dt-app 属性直接获取包名（最可靠）
        pkg = _extract_attr(item, "data-dt-app")
        if not pkg or pkg in seen_pkgs:
            continue
        if not _PKG_RE.match(pkg):
            continue
        seen_pkgs.add(pkg)
        # 图标: img.app-icon 的 src/srcset 属性 (排名页图标直接是完整URL)
        icon_el = item.select_one(APKPURE_SELECTORS["icon"][0])
        icon_url = ""
        if icon_el:
            src = icon_el.get("src") or icon_el.get("data-src") or icon_el.get("data-original") or ""
            # srcset 格式: "url1 1x, url2 2x"，取第一个
            srcset = icon_el.get("srcset") or ""
            if not src or len(src) < 20 or "base64" in src:
                if srcset:
                    src = srcset.split(",")[0].strip().split(" ")[0] or src
            if src and len(src) > 20 and "base64" not in src:
                icon_url = src
        # 游戏名 + 详情链接: a.icon[title] 的 title 和 href
        link_el = item.select_one(APKPURE_SELECTORS["app_name"][0])
        app_name = _extract_attr(link_el, "title") if link_el else ""
        detail_href = _extract_attr(link_el, "href") if link_el else ""
        if not app_name or len(app_name) < 2:
            continue
        for suffix in (" APK", " APKs", " MOD APK", " XAPK"):
            if app_name.endswith(suffix):
                app_name = app_name[:-len(suffix)].strip()
        detail_url = detail_href if detail_href.startswith("http") else f"https://apkpure.com{detail_href}"
        # 版本名: .info-sdk 文本如 "2.135.3 by Aniplex Inc."，取 " by" 之前的部分
        ver_el = item.select_one(".info-sdk")
        version_name = ""
        if ver_el:
            ver_text = ver_el.get_text(strip=True)
            if " by " in ver_text:
                version_name = ver_text.split(" by ")[0]
            elif "by " in ver_text:
                version_name = ver_text.split("by ")[0].rstrip()
            else:
                version_name = ver_text.split(" ")[0] if " " in ver_text else ver_text
        items.append({
            "icon_url": icon_url,
            "app_name": app_name,
            "package_name": pkg,
            "detail_url": detail_url,
            "download_count": "",
            "version_name": version_name,
            "updated_at": None,
        })
    return items


def _extract_pkg_from_href(href: str) -> str | None:
    """从 APKCombo/APKPure 链接中提取包名."""
    if not href:
        return None
    # href 格式: /zh/{app-slug}/{package.name}/ 或 https://apkpure.com/{slug}/{package}
    parts = [p for p in href.rstrip("/").split("/") if p]
    if not parts:
        return None
    pkg = parts[-1]
    if _PKG_RE.match(pkg):
        return pkg
    return None


def _parse_apkcombo_html(html: str) -> list[dict]:
    """解析 APKCombo 热门游戏页面: zh/category/game/.

    页面结构: <a href=\"...\"><figure><img/></figure><p>游戏名</p><p>50 M+</p></a>
    已按下载量从高到低排序。
    """
    items: list[dict] = []
    soup = BeautifulSoup(html, "html.parser")
    for sel in APKCOMBO_SELECTORS["container"]:
        links = soup.select(sel)
        if links:
            break
    for link in links:
        href = _extract_attr(link, "href")
        pkg = _extract_pkg_from_href(href)
        if not pkg:
            continue
        # 提取所有 <p> 标签: 第一个=游戏名, 第二个=下载量
        paragraphs = link.select("p")
        app_name = paragraphs[0].get_text(strip=True) if len(paragraphs) >= 1 else ""
        download_count = paragraphs[1].get_text(strip=True) if len(paragraphs) >= 2 else ""
        if not app_name:
            app_name = _extract_attr(link, "title").replace(" APK", "").strip()
        if not app_name:
            continue
        # 过滤: 排除休闲/益智/纸牌类游戏
        app_lower = app_name.lower()
        if any(kw in app_lower for kw in _APKCOMBO_EXCLUDE_KEYWORDS):
            continue
        detail_url = href if href.startswith("http") else f"https://apkcombo.com{href}"
        icon_url = _extract_icon(link, APKCOMBO_SELECTORS["icon"])
        items.append({
            "icon_url": icon_url,
            "app_name": app_name,
            "package_name": pkg,
            "detail_url": detail_url,
            "download_count": download_count,
            "updated_at": None,
        })
    return items


# ── 详情页抓取 (v2.8.2) ────────────────────────────────────

async def _fetch_detail_time_apkpure(item: dict) -> dict:
    """访问 APKPure 详情页获取真实更新时间 (http_get → stealth 降级)."""
    async with _DETAIL_SEMAPHORE:
        detail_url = item.get("detail_url", "")
        if not detail_url:
            return item
        try:
            status, html = await http_get(detail_url)
            # http_get 失败或疑似被 CF 拦截 → 降级 stealth_get
            if status != 200 or len(html) < 1000:
                logger.debug("APKPure detail http_get failed ({}) for {}, trying stealth...",
                             status, detail_url[:60])
                await asyncio.sleep(random.uniform(1.0, 2.5))
                status, html = await stealth_get(detail_url)
            if status != 200 or len(html) < 1000:
                logger.debug("APKPure detail page failed: {} HTTP {}", detail_url[:60], status)
                return item
            soup = BeautifulSoup(html, "html.parser")
            info_el = soup.select_one(".additional-info")
            if info_el:
                date_text = info_el.get_text(strip=True)
                parsed = _parse_cn_date(date_text)
                if parsed:
                    item["updated_at"] = parsed
                    return item
            logger.debug("APKPure detail page: .additional-info not found for {}", item.get("package_name"))
        except asyncio.TimeoutError:
            logger.debug("APKPure detail page timeout: {}", detail_url[:60])
        except Exception as exc:
            logger.debug("APKPure detail page error: {} — {}", detail_url[:60], exc)
    return item


async def _fetch_detail_time_apkcombo(item: dict) -> dict:
    """访问 APKCombo 详情页获取真实更新时间."""
    async with _DETAIL_SEMAPHORE:
        detail_url = item.get("detail_url", "")
        if not detail_url:
            return item
        try:
            status, html = await http_get(detail_url)
            if status != 200 or len(html) < 1000:
                logger.debug("APKCombo detail page failed: {} HTTP {}", detail_url[:60], status)
                return item
            soup = BeautifulSoup(html, "html.parser")
            ver_el = soup.select_one(".ver-item")
            if ver_el:
                date_text = ver_el.get_text(strip=True)
                parsed = _parse_cn_date(date_text)
                if parsed:
                    item["updated_at"] = parsed
                    return item
            logger.debug("APKCombo detail page: .ver-item not found for {}", item.get("package_name"))
        except asyncio.TimeoutError:
            logger.debug("APKCombo detail page timeout: {}", detail_url[:60])
        except Exception as exc:
            logger.debug("APKCombo detail page error: {} — {}", detail_url[:60], exc)
    return item


async def _enrich_with_detail_times(items: list[dict], source: str, max_enrich: int = 60) -> list[dict]:
    """并发抓取详情页填充真实更新时间 (分批执行, 批次间暂停降低 CF 风控)."""
    if not items:
        return items
    fn = _fetch_detail_time_apkpure if source == "apkpure" else _fetch_detail_time_apkcombo
    targets = items[:max_enrich]
    batch_size = 5
    for batch_start in range(0, len(targets), batch_size):
        batch = targets[batch_start:batch_start + batch_size]
        tasks = [fn(item) for item in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for j, result in enumerate(results):
            idx = batch_start + j
            if isinstance(result, dict):
                items[idx] = result
        # 批次间暂停 (最后一批不加)
        if batch_start + batch_size < len(targets):
            await asyncio.sleep(random.uniform(2.0, 4.0))
    # 统计真实日期获取情况; 未获取到的条目保持 updated_at=None
    enriched_count = sum(1 for item in targets if item.get("updated_at"))
    logger.info("{} detail enrichment: {}/{} got real dates, {} missing",
                source, enriched_count, len(targets),
                max(0, len(targets) - enriched_count))
    if enriched_count == 0:
        # 全部失败 → 不覆盖旧数据, save_updates 会跳过 DELETE 保留上次结果
        logger.warning("{} all detail fetches failed, keeping old data", source)
    return items


# ── APKVision 详情页富化 (v3.2) ─────────────────────────────

async def _enrich_apkvision_item(item: dict) -> dict | None:
    """访问 APKVision 详情页, 提取包名 (Google Play 链接) 和真实更新时间."""
    async with _DETAIL_SEMAPHORE:
        detail_url = item.get("detail_url", "")
        if not detail_url:
            return None
        try:
            status, html = await http_get(detail_url)
            if status != 200 or len(html) < 1000:
                logger.debug("APKVision detail page failed: {} HTTP {}", detail_url[:60], status)
                # 保留列表页数据, 用抓取时间兜底
                item["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                return item
            soup = BeautifulSoup(html, "html.parser")

            # 1. 从 Google Play 链接提取包名
            gp_link = soup.select_one("a[href*='play.google.com/store/apps/details?id=']") or \
                      soup.select_one("a[href*='google.com/store/apps/details?id=']")
            if gp_link:
                href = gp_link.get("href", "")
                # href 格式: https://play.google.com/store/apps/details?id=com.xxx.yyy&ref=...
                parsed = urlparse(href)
                qs = parse_qs(parsed.query)
                pkg_list = qs.get("id", [])
                if pkg_list and _PKG_RE.match(pkg_list[0]):
                    item["package_name"] = pkg_list[0]
                else:
                    # 尝试从 path 提取: /store/apps/details?id=com.xxx.yyy
                    if "id=" in parsed.path:
                        pkg = parsed.path.split("id=")[-1].split("&")[0]
                        if _PKG_RE.match(pkg):
                            item["package_name"] = pkg

            # 2. 从 meta 标签提取真实更新时间
            for meta_prop in ("article:modified_time", "article:published_time"):
                meta = soup.select_one(f"meta[property='{meta_prop}']")
                if meta and meta.get("content"):
                    try:
                        dt = datetime.fromisoformat(meta["content"].replace("Z", "+00:00"))
                        item["updated_at"] = dt.strftime("%Y-%m-%d %H:%M:%S")
                        break
                    except (ValueError, TypeError):
                        continue

            # 3. 如果没拿到真实时间, 用抓取时间兜底
            if not item.get("updated_at"):
                item["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        except asyncio.TimeoutError:
            logger.debug("APKVision detail page timeout: {}", detail_url[:60])
            item["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        except Exception as exc:
            logger.debug("APKVision detail page error: {} — {}", detail_url[:60], exc)
            item["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return item


async def _enrich_apkvision_items(items: list[dict], max_enrich: int = 40) -> list[dict]:
    """并发抓取 APKVision 详情页, 填充包名和真实更新时间."""
    if not items:
        return items
    tasks = [_enrich_apkvision_item(item) for item in items[:max_enrich]]
    enriched: list[dict] = []
    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, dict):
                # 只保留成功提取到包名的条目
                if result.get("package_name") and _PKG_RE.match(result["package_name"]):
                    enriched.append(result)
                else:
                    logger.debug("APKVision item dropped: no valid package_name (url={})",
                                 result.get("detail_url", "")[:60])

    # 统计
    with_time = sum(1 for it in enriched if it.get("updated_at"))
    logger.info("APKVision detail enrichment: {}/{} items with package, {} with real dates",
                len(enriched), min(len(items), max_enrich), with_time)
    if not enriched:
        logger.warning("APKVision all detail fetches returned no valid items")
    return enriched


# ── 列表页抓取 ──────────────────────────────────────────────

async def fetch_apkpure_updates():
    """抓取 APKPure 排名页面所有分类: 18 个分类 × 每类约 10 款游戏."""
    all_items: list[dict] = []
    seen_pkgs: set[str] = set()
    for cat in APKPURE_CATEGORIES:
        url = f"https://apkpure.com/cn/ranking/latest-updated-{cat}"
        try:
            status, html = await _fetch_page(url)
            if status != 200 or len(html) < 500:
                logger.warning("APKPure category {} failed: HTTP {}", cat, status)
                continue
            items = _parse_apkpure_html(html)
            # 跨分类去重
            new_count = 0
            for item in items:
                if item["package_name"] not in seen_pkgs:
                    seen_pkgs.add(item["package_name"])
                    all_items.append(item)
                    new_count += 1
            logger.debug("APKPure category {}: {} items ({} new)", cat, len(items), new_count)
        except Exception as exc:
            logger.warning("APKPure category {} error: {}", cat, exc)
        await asyncio.sleep(random.uniform(2.5, 5.0))
    if not all_items:
        raise Exception("APKPure all categories parse empty")
    logger.info("APKPure list fetched: {} unique items from {} categories, enriching...",
                len(all_items), len(APKPURE_CATEGORIES))
    all_items = await _enrich_with_detail_times(all_items, "apkpure", max_enrich=80)
    logger.info("APKPure enriched: {} items", len(all_items))
    return all_items


async def fetch_apkcombo_updates():
    """抓取 APKCombo 热门游戏页面: zh/category/game/ (按下载量排序)."""
    url = "https://apkcombo.com/zh/category/game/"
    status, html = await _fetch_page(url)
    if status != 200 or len(html) < 500:
        raise Exception(f"APKCombo category page failed: HTTP {status}")
    items: list[dict] = _parse_apkcombo_html(html)
    if not items:
        raise Exception("APKCombo parse empty, page structure may have changed")
    logger.info("APKCombo list fetched: {} items, enriching details...", len(items))
    items = await _enrich_with_detail_times(items, "apkcombo", max_enrich=100)
    logger.info("APKCombo enriched: {} items", len(items))
    return items


async def fetch_apkcombo_trending_updates():
    """抓取 APKCombo 最新更新页面 (50K+ 下载量游戏来源)."""
    items: list[dict] = []
    for page in range(1, 4):  # 3 页
        url = f"https://apkcombo.com/zh/category/game/latest-updates/?page={page}"
        status, html = await _fetch_page(url)
        if status != 200 or len(html) < 500:
            break
        # 复用热点页解析器 (结构兼容)
        soup = BeautifulSoup(html, "html.parser")
        links = soup.select(".l_item")
        for link in links:
            href = _extract_attr(link, "href")
            pkg = _extract_pkg_from_href(href)
            if not pkg:
                continue
            name_el = link.select_one(".name")
            app_name = name_el.get_text(strip=True) if name_el else _extract_attr(link, "title").replace(" APK", "").strip()
            if not app_name:
                continue
            app_lower = app_name.lower()
            if any(kw in app_lower for kw in _APKCOMBO_EXCLUDE_KEYWORDS):
                continue
            detail_url = href if href.startswith("http") else f"https://apkcombo.com{href}"
            icon_url = _extract_icon(link, ["figure img.lzl", "figure img[data-src]", "figure img"])
            items.append({
                "icon_url": icon_url,
                "app_name": app_name,
                "package_name": pkg,
                "detail_url": detail_url,
                "download_count": "",
                "version_name": "",
                "updated_at": None,
            })
        await asyncio.sleep(random.uniform(0.8, 1.5))
    if not items:
        raise Exception("APKCombo trending parse empty")
    logger.info("APKCombo trending fetched: {} items, enriching...", len(items))
    items = await _enrich_with_detail_times(items, "apkcombo", max_enrich=90)
    logger.info("APKCombo trending enriched: {} items", len(items))
    return items


# ── APKVision 抓取 (v3.1) ─────────────────────────────────

async def fetch_apkvision_updated():
    """抓取 APKVision 最近更新页面: /updated/ (仅取前 20 条).

    v3.2: APKVision 列表页 URL 使用语义化 slug (非包名), 需访问详情页
    提取 Google Play 链接获取真实包名 + 精确更新时间.
    """
    url = "https://apkvision.org/updated/"
    status, html = await _fetch_page(url)
    if status != 200 or len(html) < 500:
        raise Exception(f"APKVision updated page failed: HTTP {status}")
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    for article in soup.select(".main-news-grid .main-news")[:20]:
        name_el = article.select_one(".main-news-title")
        app_name = name_el.get_text(strip=True) if name_el else ""
        if not app_name or len(app_name) < 2:
            continue
        cat_els = article.select(".main-news-cat")
        version_name = cat_els[0].get_text(strip=True) if cat_els else ""
        link_el = article if article.name == "a" else article.select_one("a[href]")
        href = _extract_attr(link_el, "href") if link_el else ""
        if not href:
            continue
        detail_url = href if href.startswith("http") else f"https://apkvision.org{href}"
        icon_url = _extract_icon(article, ["img.lazy", "img[data-src]", "img[src]"])
        items.append({
            "icon_url": icon_url,
            "app_name": app_name,
            "package_name": "",  # 待详情页填充
            "detail_url": detail_url,
            "download_count": "",
            "version_name": version_name,
            "updated_at": None,
        })
    if not items:
        raise Exception("APKVision updated parse empty, page structure may have changed")
    logger.info("APKVision updated list: {} items, enriching details...", len(items))
    items = await _enrich_apkvision_items(items)
    if not items:
        raise Exception("APKVision updated: all items dropped after detail enrichment")
    logger.info("APKVision updated enriched: {} items", len(items))
    return items


async def fetch_apkvision_new():
    """抓取 APKVision 新游戏页面: /games/ (Best New Games + 普通列表, 仅取前 20 条).

    v3.2: APKVision 列表页 URL 使用语义化 slug (非包名), 需访问详情页
    提取 Google Play 链接获取真实包名 + 精确更新时间.
    """
    url = "https://apkvision.org/games/"
    status, html = await _fetch_page(url)
    if status != 200 or len(html) < 500:
        raise Exception(f"APKVision new games page failed: HTTP {status}")
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen_urls: set[str] = set()  # URL 去重 (列表页无包名, 用详情 URL 去重)

    def _parse_articles(article_list):
        for article in article_list:
            if len(items) >= 20:
                return
            name_el = article.select_one(".mainb-title") or article.select_one(".main-news-title")
            app_name = name_el.get_text(strip=True) if name_el else ""
            if not app_name or len(app_name) < 2:
                continue
            cat_els = article.select(".mainb-cat") or article.select(".main-news-cat")
            version_name = cat_els[0].get_text(strip=True) if cat_els else ""
            link_el = article if article.name == "a" else article.select_one("a[href]")
            href = _extract_attr(link_el, "href") if link_el else ""
            if not href:
                continue
            detail_url = href if href.startswith("http") else f"https://apkvision.org{href}"
            if detail_url in seen_urls:
                continue
            seen_urls.add(detail_url)
            icon_url = _extract_icon(article, ["img.lazy", "img[data-src]", "img[src]"])
            items.append({
                "icon_url": icon_url,
                "app_name": app_name,
                "package_name": "",  # 待详情页填充
                "detail_url": detail_url,
                "download_count": "",
                "version_name": version_name,
                "updated_at": None,
            })

    # 先取 Best New Games (.mainb-grid .mainb-item)
    _parse_articles(soup.select(".mainb-grid .mainb-item"))
    # 若不足 20，再取下方普通列表 (.main-news-grid .main-news)
    if len(items) < 20:
        _parse_articles(soup.select(".main-news-grid .main-news"))

    if not items:
        raise Exception("APKVision new games parse empty, page structure may have changed")
    logger.info("APKVision new games list: {} items, enriching details...", len(items))
    items = await _enrich_apkvision_items(items)
    if not items:
        raise Exception("APKVision new games: all items dropped after detail enrichment")
    logger.info("APKVision new games enriched: {} items", len(items))
    return items


# ── 入库 ─────────────────────────────────────────────────

async def save_updates(source: str, items: list[dict]) -> None:
    """事务入库 — 先删后插, 仅保存有真实更新时间的条目."""
    # 过滤: 只保留有真实更新时间的条目
    valid = [it for it in items if it.get("updated_at")]
    if not valid:
        logger.warning("{} no items with real dates, skipping save", source)
        return

    def _sync() -> None:
        conn = get_connection()
        try:
            conn.execute("BEGIN")
            conn.execute("DELETE FROM daily_updates WHERE source = ?", (source,))
            for item in valid:
                conn.execute(
                    """INSERT INTO daily_updates
                       (source, icon_url, detail_url, app_name, package_name,
                        download_count, version_name, version_code, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (source,
                     item.get("icon_url", ""),
                     item.get("detail_url", ""),
                     item.get("app_name", ""),
                     item["package_name"],
                     item.get("download_count", ""),
                     item.get("version_name", ""),
                     "",
                     item["updated_at"]),
                )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
    await asyncio.to_thread(_sync)
    logger.info("{} saved {} items to DB", source, len(valid))


# ── 熔断器 ───────────────────────────────────────────────

async def is_circuit_open(source):
    def _sync():
        conn = get_connection()
        try:
            cur = conn.execute(
                "SELECT is_open, open_until FROM daily_updates_circuit_breaker WHERE source = ?",
                (source,),
            )
            row = cur.fetchone()
            if row and row[0] and row[1]:
                open_until = datetime.fromisoformat(row[1])
                if datetime.now() < open_until:
                    return True
                conn.execute(
                    "UPDATE daily_updates_circuit_breaker SET is_open=0, consecutive_failures=0, open_until=NULL WHERE source=?",
                    (source,),
                )
                conn.commit()
        finally:
            conn.close()
        return False
    return await asyncio.to_thread(_sync)


async def record_failure(source):
    def _sync():
        conn = get_connection()
        try:
            now = datetime.now().isoformat()
            conn.execute(
                """INSERT INTO daily_updates_circuit_breaker
                   (source, consecutive_failures, last_failure_time, is_open, open_until)
                   VALUES (?, 1, ?, 0, NULL)
                   ON CONFLICT(source) DO UPDATE SET
                   consecutive_failures = consecutive_failures + 1, last_failure_time = ?""",
                (source, now, now),
            )
            conn.commit()
            cur = conn.execute(
                "SELECT consecutive_failures FROM daily_updates_circuit_breaker WHERE source=?",
                (source,),
            )
            row = cur.fetchone()
            if row and row[0] >= 3:
                open_until = (datetime.now() + timedelta(minutes=30)).isoformat()
                conn.execute(
                    "UPDATE daily_updates_circuit_breaker SET is_open=1, open_until=? WHERE source=?",
                    (open_until, source),
                )
                conn.commit()
                logger.warning("source {} failed {} times, circuit open 30min", source, row[0])
        finally:
            conn.close()
    await asyncio.to_thread(_sync)


async def record_success(source):
    def _sync():
        conn = get_connection()
        try:
            conn.execute(
                """INSERT INTO daily_updates_circuit_breaker
                   (source, consecutive_failures, is_open, open_until)
                   VALUES (?, 0, 0, NULL)
                   ON CONFLICT(source) DO UPDATE SET
                   consecutive_failures=0, is_open=0, open_until=NULL""",
                (source,),
            )
            conn.commit()
        finally:
            conn.close()
    await asyncio.to_thread(_sync)


# ── 编排 ─────────────────────────────────────────────────

async def fetch_source_with_circuit_breaker(source):
    if await is_circuit_open(source):
        logger.warning("source {} circuit open, skipping", source)
        return
    try:
        fn_map = {
            "apkpure": fetch_apkpure_updates,
            "apkcombo": fetch_apkcombo_updates,
            "apkcombo_trending": fetch_apkcombo_trending_updates,
            "apkvision_updated": fetch_apkvision_updated,
            "apkvision_new": fetch_apkvision_new,
        }
        items = await fn_map[source]()
        if not items:
            raise Exception(f"{source} parse returned empty")
        await save_updates(source, items)
        await record_success(source)
    except Exception as e:
        logger.error("fetch {} failed: {}", source, e)
        await record_failure(source)


async def update_once():
    await asyncio.gather(
        fetch_source_with_circuit_breaker("apkpure"),
        fetch_source_with_circuit_breaker("apkcombo"),
        fetch_source_with_circuit_breaker("apkcombo_trending"),
        fetch_source_with_circuit_breaker("apkvision_updated"),
        fetch_source_with_circuit_breaker("apkvision_new"),
        return_exceptions=True,
    )
    set_last_modified(datetime.now(timezone.utc))


async def run_periodic_updates():
    try:
        await update_once()
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error("initial update failed: {}", e)
    while True:
        settings = get_settings()
        interval = getattr(settings, "update_check_interval", 1800)
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            break
        try:
            await update_once()
            logger.info("daily updates panel refreshed")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("periodic update error: {}", e)
    logger.info("每日更新面板后台任务已停止")
