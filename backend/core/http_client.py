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
    1. 环境变量 _CHROMIUM_DIR 指定的路径
    2. PyInstaller EXE 打包后 — 优先 EXE 同目录/chromium/（持久, v3.3）
    3. PyInstaller EXE 打包后 — 回退 sys._MEIPASS/chromium/（临时）
    4. 开发模式 — 在 LOCALAPPDATA/ms-playwright/ 下找

    Returns:
        chrome-headless-shell.exe 或 chrome.exe 的路径, 找不到返回 None.
    """
    candidates: list[str] = []

    # 环境变量优先
    env_dir = os.environ.get("_CHROMIUM_DIR", "")
    if env_dir:
        for name in ("chrome-headless-shell.exe", "chrome.exe"):
            p = os.path.join(env_dir, name)
            if os.path.isfile(p):
                return p

    if getattr(sys, "frozen", False):
        # v3.3: 优先从 EXE 同目录的持久 chromium/ 查找
        exe_dir = os.path.dirname(sys.executable)
        persistent_chromium = os.path.join(exe_dir, "chromium")
        if os.path.isdir(persistent_chromium):
            for name in ("chrome-headless-shell.exe", "chrome.exe"):
                p = os.path.join(persistent_chromium, name)
                if os.path.isfile(p):
                    return p
        # 回退到 PyInstaller 临时解压目录
        temp_chromium = os.path.join(sys._MEIPASS, "chromium")  # type: ignore[attr-defined]
        for name in ("chrome-headless-shell.exe", "chrome.exe"):
            p = os.path.join(temp_chromium, name)
            if os.path.isfile(p):
                return p
        # v3.4: 回退到服务器安装的 Playwright Chromium (LOCALAPPDATA/ms-playwright)

    # 通用路径: ms-playwright (开发模式 + EXE 最终兜底)
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    ms_dir = os.path.join(local_appdata, "ms-playwright")
    if os.path.isdir(ms_dir):
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


# ── URL 安全验证 (SSRF 防护) ─────────────────────────────

import ipaddress as _ipaddress
import random as _random

# 已知的 APK 源域名白名单
_ALLOWED_DOMAINS: set[str] = {
    "apkpure.com", "apkpure.net",
    "apkcombo.com", "apkcombo.org",
    "apkmirror.com",
    "apkvision.org",
    "play.google.com", "android.googleapis.com",
    "google.com", "googleapis.com",
}


def validate_url(url: str, allow_all_https: bool = False) -> str:
    """验证 URL 安全性，防止 SSRF。

    规则:
        1. 必须 http:// 或 https://
        2. 拒绝解析到私有/回环/链路本地 IP 的域名
        3. 若 allow_all_https=False (默认), 域名必须在白名单中
        4. 若 allow_all_https=True, 允许任意 HTTPS URL (仅拒绝私有IP)

    Returns:
        规范化后的 URL。

    Raises:
        ValueError: URL 不安全。
    """
    import socket as _socket

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"不支持的协议: {parsed.scheme}")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("无效 URL: 缺少主机名")

    # 拒绝原始 IP 地址 (数字格式)
    ip = None
    try:
        ip = _ipaddress.ip_address(hostname)
    except ValueError:
        pass  # 不是 IP 地址，DNS 检查下面做
    if ip is not None:
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
            raise ValueError(f"拒绝内部 IP: {hostname}")
        if ip.version == 4 and (ip.is_reserved or ip.is_unspecified):
            raise ValueError(f"拒绝保留 IP: {hostname}")

    # DNS 解析后检查 (防 DNS rebinding)
    try:
        resolved = _socket.getaddrinfo(hostname, None, _socket.AF_INET)
        seen_ips: set[str] = set()
        for family, _type, _proto, _cname, sockaddr in resolved:
            ip_addr = sockaddr[0]  # IP 在 sockaddr 元组第一个元素
            if ip_addr in seen_ips:
                continue
            seen_ips.add(ip_addr)
            try:
                ip = _ipaddress.ip_address(ip_addr)
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
                    raise ValueError(f"域名 {hostname} 解析到内部 IP: {ip_addr}")
                if ip.version == 4 and (ip.is_reserved or ip.is_unspecified):
                    raise ValueError(f"域名 {hostname} 解析到保留 IP: {ip_addr}")
            except ValueError as ip_err:
                if "解析到" in str(ip_err):  # 我们的内部 IP 错误
                    raise
                # 其他 ValueError (如非标准 IP 格式) 忽略
    except _socket.gaierror:
        raise ValueError(f"域名解析失败: {hostname}")

    # 域名白名单检查
    if not allow_all_https:
        allowed = False
        for domain in _ALLOWED_DOMAINS:
            if hostname == domain or hostname.endswith("." + domain):
                allowed = True
                break
        if not allowed:
            raise ValueError(f"域名不在白名单中: {hostname} 如需访问，使用 allow_all_https=True")

    return parsed.geturl()# ── Fetcher 后端 ────────────────────────────────────────────

# TLS 指纹池 (v3.3: 随机轮换降低被 Cloudflare 关联封禁的概率)
_FINGERPRINTS = [
    "chrome110", "chrome116", "chrome120", "chrome124", "edge101",
]

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
    """同步 HTTP GET — Scrapling Fetcher (curl_cffi + browserforge).

    带代理时若代理不可用自动降级为直连请求。
    """
    settings = get_settings()
    proxies = _get_proxy_dict()

    def _do_fetch(proxies_override=None):
        fetcher = _get_fetcher()
        return fetcher.get(
            url,
            timeout=int(settings.request_timeout),
            retries=0 if proxies_override is not None else settings.retry_times,
            retry_delay=settings.retry_delay,
            impersonate=_random.choice(_FINGERPRINTS),
            stealthy_headers=True,
            proxies=proxies_override if proxies_override is not None else proxies,
            headers={"Accept-Language": "zh-CN,zh;q=0.9"},
        )

    def _check_response(resp) -> tuple[int, str]:
        if resp.status == 200 and len(resp.html_content) > 500:
            return resp.status, resp.html_content
        if resp.status == 403 and is_cloudflare_block(resp.html_content):
            return 0, f"Cloudflare blocked: {urlparse(url).hostname}"
        return resp.status, resp.html_content or ""

    try:
        resp = _do_fetch()
        return _check_response(resp)
    except Exception as e:
        err_msg = f"{type(e).__name__}: {e!s}"[:120]
        # 代理连接失败 → 降级直连重试一次
        if proxies and ("connect to 127.0.0.1" in str(e).lower()
                        or "connect to localhost" in str(e).lower()
                        or "proxy" in str(e).lower()
                        or "curl: (7)" in str(e)):
            logger.info("代理不可用 {}，降级为直连: {}", settings.proxy, url[:60])
            try:
                resp = _do_fetch(proxies_override={})
                return _check_response(resp)
            except Exception as e2:
                logger.warning("Fetcher error (直连) for {}: {}", url[:60], e2)
                return 0, f"{type(e2).__name__}: {e2!s}"[:80]
        logger.warning("Fetcher error for {}: {}", url[:60], e)
        return 0, err_msg[:80]


async def http_get(url: str) -> tuple[int, str]:
    """异步 HTTP GET."""
    return await asyncio.to_thread(_http_get_sync, url)


# ── StealthySession 后端 ────────────────────────────────────

def _stealth_get_sync(url: str) -> tuple[int, str]:
    """同步浏览器 GET — StealthySession (Chromium + CF 绕过)."""
    from scrapling.fetchers import StealthySession

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
