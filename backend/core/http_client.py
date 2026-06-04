"""HTTP 客户端 — 基于 Scrapling 的双层后端 + async 适配.

复用 gvc/http_client.py 的核心逻辑，包装为 RequestHelper 类。
同步的 Scrapling 调用通过 asyncio.to_thread() 适配为异步。
"""

from __future__ import annotations

import asyncio
import os
import queue
import sys
import threading
from urllib.parse import urlparse

from backend.config import get_settings
from backend.logging_setup import get_logger

logger = get_logger()


# ── Chromium 定位 ──────────────────────────────────────────

def get_chromium_executable() -> str | None:
    """定位 Chromium 浏览器可执行文件.

    优先级:
    1. PyInstaller EXE 打包后 — 在 sys._MEIPASS/chromium/ 下找
    2. 开发模式 — 在 LOCALAPPDATA/ms-playwright/ 下找

    Returns:
        chrome-headless-shell.exe 或 chrome.exe 的路径, 找不到返回 None.
    """
    if getattr(sys, "frozen", False):
        chromium_dir = os.path.join(sys._MEIPASS, "chromium")  # type: ignore[attr-defined]
        candidates = [
            os.path.join(chromium_dir, "chrome-headless-shell.exe"),
            os.path.join(chromium_dir, "chrome.exe"),
        ]
        for exe in candidates:
            if os.path.isfile(exe):
                return exe
        return None
    else:
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        ms_dir = os.path.join(local_appdata, "ms-playwright")
        for root, dirs, files in os.walk(ms_dir):
            depth = root.replace(ms_dir, "").count(os.sep)
            if depth > 2:
                continue
            for f in files:
                if f in ("chrome-headless-shell.exe", "chrome.exe"):
                    return os.path.join(root, f)
        return None

# ── Cloudflare 检测 ────────────────────────────────────────

_CF_SIGNATURES: list[str] = [
    "cf-browser-verify",
    "Cloudflare",
    "Attention Required",
    "cf-challenge",
    "cf_captcha",
    "cf-wrapper",
    "Checking your browser",
    "DDoS protection",
    "Just a moment",
]


def is_cloudflare_block(html: str) -> bool:
    """检测是否为 Cloudflare JS 挑战页面."""
    if len(html) > 20000:
        return False
    html_lower = html.lower()
    return any(sig.lower() in html_lower for sig in _CF_SIGNATURES)


# ── 代理 ────────────────────────────────────────────────────

def _get_proxy_dict() -> dict | None:
    """从配置获取代理字典."""
    settings = get_settings()
    if settings.proxy:
        return {"http": settings.proxy, "https": settings.proxy}
    return None


# ── Fetcher 后端 ────────────────────────────────────────────

_fetcher = None
_fetcher_lock = threading.Lock()


def _get_fetcher():
    """获取或创建持久化 Fetcher 实例."""
    global _fetcher
    if _fetcher is None:
        with _fetcher_lock:
            if _fetcher is None:
                from scrapling import Fetcher
                _fetcher = Fetcher()
    return _fetcher


def _http_get_sync(url: str) -> tuple[int, str]:
    """同步 HTTP GET — Scrapling Fetcher (curl_cffi + browserforge)."""
    from backend.config import get_settings
    settings = get_settings()
    proxies = _get_proxy_dict()

    try:
        fetcher = _get_fetcher()
        resp = fetcher.get(
            url,
            timeout=int(settings.request_timeout),
            retries=settings.retry_times,
            retry_delay=settings.retry_delay,
            impersonate="chrome124",
            stealthy_headers=True,
            proxies=proxies,
            headers={"Accept-Language": "zh-CN,zh;q=0.9"},
        )
        if resp.status == 200 and len(resp.html_content) > 500:
            return resp.status, resp.html_content
        if resp.status == 403 and is_cloudflare_block(resp.html_content):
            return 0, f"Cloudflare blocked: {urlparse(url).hostname}"
        return resp.status, resp.html_content or ""
    except Exception as e:
        logger.warning("Fetcher error for {}: {}", url[:60], e)
        return 0, f"{type(e).__name__}: {e!s}"[:80]


async def http_get(url: str) -> tuple[int, str]:
    """异步 HTTP GET."""
    return await asyncio.to_thread(_http_get_sync, url)


# ── StealthySession 后端 ────────────────────────────────────

def _stealth_get_sync(url: str) -> tuple[int, str]:
    """同步浏览器 GET — StealthySession (Chromium + CF 绕过)."""
    from scrapling.fetchers import StealthySession
    from backend.config import get_settings

    settings = get_settings()
    proxies = _get_proxy_dict()
    proxy_config = None
    if proxies:
        proxy_url = proxies.get("https") or proxies.get("http")
        if proxy_url:
            proxy_config = {"server": proxy_url}

    hard_timeout = settings.stealth_timeout + 30.0
    result_queue: queue.Queue = queue.Queue()

    chrome_exe = get_chromium_executable()

    def _worker():
        try:
            with StealthySession(
                headless=True,
                solve_cloudflare=True,
                block_ads=True,
                disable_resources=True,
                timeout=int((settings.stealth_timeout + 15) * 1000),
                google_search=False,
                proxy=proxy_config,
                executable_path=chrome_exe,
            ) as s:
                resp = s.fetch(url, headers={"Accept-Language": "zh-CN,zh;q=0.9"})
                if resp.status == 200 and len(resp.html_content) > 500:
                    if is_cloudflare_block(resp.html_content):
                        result_queue.put((0, f"CF bypass failed: {urlparse(url).hostname}"))
                    else:
                        result_queue.put((resp.status, resp.html_content))
                else:
                    result_queue.put((resp.status, resp.html_content or ""))
        except Exception as e:
            result_queue.put((0, f"{type(e).__name__}: {e!s}"[:80]))

    worker = threading.Thread(target=_worker, daemon=True)
    worker.start()
    worker.join(timeout=hard_timeout)

    if worker.is_alive():
        logger.warning("StealthySession timeout after {:.0f}s for {}", hard_timeout, url[:60])
        return 0, f"StealthySession timeout after {hard_timeout:.0f}s"

    try:
        return result_queue.get_nowait()
    except queue.Empty:
        return 0, "StealthySession error: no result"


async def stealth_get(url: str) -> tuple[int, str]:
    """异步浏览器 GET."""
    return await asyncio.to_thread(_stealth_get_sync, url)


# ── JS 渲染后端 ─────────────────────────────────────────────

def _js_render_get_sync(url: str) -> tuple[int, str]:
    """同步 JS 渲染 GET — StealthySession (无 CF 等待)."""
    from scrapling.fetchers import StealthySession
    from backend.config import get_settings

    settings = get_settings()
    proxies = _get_proxy_dict()
    proxy_config = None
    if proxies:
        proxy_url = proxies.get("https") or proxies.get("http")
        if proxy_url:
            proxy_config = {"server": proxy_url}

    hard_timeout = 35.0
    result_queue: queue.Queue = queue.Queue()

    chrome_exe = get_chromium_executable()

    def _worker():
        try:
            with StealthySession(
                headless=True,
                solve_cloudflare=False,
                block_ads=True,
                disable_resources=True,
                timeout=20000,
                google_search=False,
                proxy=proxy_config,
                executable_path=chrome_exe,
            ) as s:
                resp = s.fetch(url, headers={"Accept-Language": "zh-CN,zh;q=0.9"})
                if resp.status == 200 and len(resp.html_content) > 500:
                    result_queue.put((resp.status, resp.html_content))
                else:
                    result_queue.put((resp.status, resp.html_content or ""))
        except Exception as e:
            result_queue.put((0, f"{type(e).__name__}: {e!s}"[:80]))

    worker = threading.Thread(target=_worker, daemon=True)
    worker.start()
    worker.join(timeout=hard_timeout)

    if worker.is_alive():
        return 0, f"JS render timeout after {hard_timeout:.0f}s"

    try:
        return result_queue.get_nowait()
    except queue.Empty:
        return 0, "JS render error: no result"


async def js_render_get(url: str) -> tuple[int, str]:
    """异步 JS 渲染 GET."""
    return await asyncio.to_thread(_js_render_get_sync, url)
