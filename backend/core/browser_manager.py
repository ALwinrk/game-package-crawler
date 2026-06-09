"""全局浏览器管理器 — Playwright 单例复用 + asyncio.Semaphore(2) 并发控制.

遵照设计文档 5.1.6 节：APKPure/APKCombo 使用 Playwright 无头浏览器提取下载链接。
- 全局只启动一个持久化浏览器实例，所有任务复用
- 每次请求使用新页面，用后关闭页面
- asyncio.Semaphore(2) 限制同时运行的 Playwright 页面数量
"""

from __future__ import annotations

import asyncio
import os
import random as _random

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
        """启动浏览器。失败返回 False（降级到静态提取）.

        v3.3: 分步捕获异常, 区分驱动层 vs 浏览器层故障,
        浏览器启动失败时正确清理驱动进程, 防止 EPIPE 噪声.
        """
        async with self._lock:
            if self._started:
                return True
            try:
                from patchright.async_api import async_playwright
                from backend.core.http_client import get_chromium_executable

                settings = get_settings()
                concurrency = getattr(settings, 'playwright_concurrency', 2)
                self._semaphore = asyncio.Semaphore(concurrency)

                # Step 1: 启动 Node.js 驱动
                try:
                    self._playwright = await async_playwright().start()
                except Exception as e:
                    logger.warning("Patchright 驱动启动失败: {} — 浏览器功能不可用", e)
                    self._playwright = None
                    self._started = False
                    return False

                chrome_exe = get_chromium_executable()
                if not chrome_exe:
                    logger.warning("未找到 Chromium 可执行文件 — 浏览器功能不可用")
                    await self._playwright.stop()
                    self._playwright = None
                    self._started = False
                    return False

                proxy_config = {"server": settings.proxy} if settings.proxy else None

                # v3.3: 反检测增强 — 随机 viewport + 禁用自动化标记 + stealth 脚本
                _ua = _random.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                ])
                _vw = _random.randint(1280, 1920)
                _vh = _random.randint(768, 1080)

                # Step 2: 启动浏览器 (限时 15s, 防止驱动卡死)
                try:
                    self._context = await asyncio.wait_for(
                        self._playwright.chromium.launch_persistent_context(
                            user_data_dir="./data/browser_profile",
                            headless=True,
                            executable_path=chrome_exe,
                            args=["--no-sandbox", "--disable-setuid-sandbox",
                                  "--disable-dev-shm-usage",
                                  "--disable-blink-features=AutomationControlled",
                                  "--disable-extensions"],
                            proxy=proxy_config,
                            viewport={"width": _vw, "height": _vh},
                            user_agent=_ua,
                        ),
                        timeout=15.0,
                    )
                except asyncio.TimeoutError:
                    logger.warning("浏览器启动超时 (15s) — 降级到静态提取")
                    await self._playwright.stop()
                    self._playwright = None
                    self._started = False
                    return False
                except Exception as e:
                    logger.warning("浏览器启动失败: {} — 降级到静态提取", e)
                    await self._playwright.stop()
                    self._playwright = None
                    self._started = False
                    return False

                # Step 3: 注入 stealth 脚本
                try:
                    await self._context.add_init_script("""
                        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    """)
                except Exception:
                    pass  # 非致命, 浏览器仍可用

                self._started = True
                logger.info("Playwright 浏览器已启动 (并发={}, vp={}x{}, chrome={})",
                            concurrency, _vw, _vh,
                            os.path.basename(chrome_exe) if chrome_exe else "?")
                return True

            except Exception as e:
                logger.warning("Playwright 初始化异常: {} — 浏览器功能不可用", e)
                if self._playwright:
                    try:
                        await self._playwright.stop()
                    except Exception:
                        pass
                self._playwright = None
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
            try:
                await page.close()
            except Exception:
                pass
        finally:
            semaphore.release()


# 全局单例
_browser_manager: BrowserManager | None = None


def get_browser_manager() -> BrowserManager:
    global _browser_manager
    if _browser_manager is None:
        _browser_manager = BrowserManager()
    return _browser_manager
