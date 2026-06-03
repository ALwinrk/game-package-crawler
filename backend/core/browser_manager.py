"""全局浏览器管理器 — Playwright 单例复用 + asyncio.Semaphore(2) 并发控制.

遵照设计文档 5.1.6 节：APKPure/APKCombo 使用 Playwright 无头浏览器提取下载链接。
- 全局只启动一个持久化浏览器实例，所有任务复用
- 每次请求使用新页面，用后关闭页面
- asyncio.Semaphore(2) 限制同时运行的 Playwright 页面数量
"""

from __future__ import annotations

import asyncio

from backend.config import get_settings
from backend.logging_setup import get_logger

logger = get_logger()


class BrowserManager:
    """Playwright 浏览器单例管理器."""

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._semaphore: asyncio.Semaphore | None = None
        self._started = False
        self._lock = asyncio.Lock()

    @property
    def available(self) -> bool:
        return self._started and self._context is not None

    async def start(self) -> bool:
        """启动浏览器。失败返回 False（降级到静态提取）."""
        async with self._lock:
            if self._started:
                return True
            try:
                from patchright.async_api import async_playwright
                from backend.core.http_client import get_chromium_executable

                settings = get_settings()
                concurrency = getattr(settings, 'playwright_concurrency', 2)
                self._semaphore = asyncio.Semaphore(concurrency)

                self._playwright = await async_playwright().start()

                chrome_exe = get_chromium_executable()
                proxy_config = {"server": settings.proxy} if settings.proxy else None

                self._context = await self._playwright.chromium.launch_persistent_context(
                    user_data_dir="./data/browser_profile",
                    headless=True,
                    executable_path=chrome_exe,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
                    proxy=proxy_config,
                    viewport={"width": 1920, "height": 1080},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                )
                self._started = True
                logger.info("Playwright 浏览器已启动 (并发={})", concurrency)
                return True
            except Exception as e:
                logger.warning("Playwright 启动失败: {} — 下载将回退到静态提取", e)
                self._started = False
                return False

    async def stop(self):
        """关闭浏览器."""
        async with self._lock:
            if not self._started:
                return
            try:
                if self._context:
                    await self._context.close()
                if self._playwright:
                    await self._playwright.stop()
                logger.info("Playwright 浏览器已关闭")
            except Exception as e:
                logger.warning("关闭浏览器出错: {}", e)
            finally:
                self._context = None
                self._playwright = None
                self._started = False

    async def new_page(self):
        """创建新页面（受信号量控制），返回 (page, release_fn)."""
        if not self.available:
            raise RuntimeError("浏览器未启动")
        await self._semaphore.acquire()
        page = await self._context.new_page()
        return page, self._semaphore

    async def close_page(self, page, semaphore: asyncio.Semaphore):
        """关闭页面并释放信号量."""
        try:
            await page.close()
        except Exception:
            pass
        semaphore.release()


# 全局单例
_browser_manager: BrowserManager | None = None


def get_browser_manager() -> BrowserManager:
    global _browser_manager
    if _browser_manager is None:
        _browser_manager = BrowserManager()
    return _browser_manager
