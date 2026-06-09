"""异步下载管理器 — aiohttp + 流式写入 + Range 断点续传."""

from __future__ import annotations

import asyncio
import os
import queue
import time
import uuid
from pathlib import Path

import aiohttp
import aiofiles

from backend.config import get_settings
from backend.db.database import get_connection
from backend.logging_setup import get_logger
from backend.models.schemas import DownloadTask

logger = get_logger()


class DownloadManager:
    """异步下载管理器.

    - 队列管理（asyncio.Queue + Semaphore 控制并发）
    - 断点续传（Range 请求 + .part 文件）
    - 进度推送（通过 WebSocket 回调）
    """

    def __init__(self, concurrency: int = 3):
        self.concurrency = concurrency
        self.semaphore = asyncio.Semaphore(concurrency)
        self._queue: asyncio.Queue[DownloadTask] = asyncio.Queue()
        self._active_tasks: dict[str, DownloadTask] = {}
        self._progress_callbacks: list[callable] = []
        self._running = False
        self._session: aiohttp.ClientSession | None = None

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    @property
    def active_count(self) -> int:
        return len(self._active_tasks)

    def on_progress(self, callback):
        """注册进度回调 async fn(task: DownloadTask)."""
        self._progress_callbacks.append(callback)

    async def _notify_progress(self, task: DownloadTask):
        for cb in self._progress_callbacks:
            try:
                await cb(task)
            except Exception:
                pass

    async def enqueue(self, task: DownloadTask) -> None:
        """添加任务到下载队列."""
        await self._queue.put(task)
        task.status = "pending"
        self._active_tasks[task.id] = task
        self._save_task(task)
        logger.info("下载任务已入队: {} ({})", task.package_name, task.arch)

    async def start(self):
        """启动下载消费者."""
        self._running = True
        connector = aiohttp.TCPConnector(limit=self.concurrency + 2)
        settings = get_settings()
        proxy = settings.proxy if settings.proxy else None
        self._session = aiohttp.ClientSession(connector=connector)

        logger.info("下载管理器已启动 (并发={})", self.concurrency)

        # 恢复未完成的下载
        await self._resume_tasks()

        # 消费队列
        while self._running:
            try:
                task = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            async with self.semaphore:
                await self._download(task)

    async def stop(self):
        """停止下载管理器."""
        self._running = False
        if self._session:
            await self._session.close()
            self._session = None
        logger.info("下载管理器已停止")

    async def _download(self, task: DownloadTask):
        """执行单个下载任务（带重试 + 架构识别）.

        策略:
        1. HEAD 预检下载链接
        2. aiohttp 直接下载（快速）
        3. HTTP 403/404 → Playwright 浏览器下载（绕过防盗链）
        4. 失败自动重试，最多 3 次
        """
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            task.retry_count = attempt
            try:
                await self._do_download(task, attempt)
                return  # 成功
            except asyncio.CancelledError:
                task.status = "paused"
                self._save_task(task)
                return
            except Exception as e:
                if attempt < max_retries:
                    delay = [1, 3, 6][attempt - 1]
                    logger.warning("下载失败 (attempt {}/{}): {} — {}，{}s 后重试",
                                   attempt, max_retries, task.package_name, e, delay)
                    await asyncio.sleep(delay)
                else:
                    task.status = "error"
                    task.error = f"{type(e).__name__}: {e!s}"[:100]
                    self._save_task(task)
                    await self._notify_progress(task)
                    logger.warning("下载失败（已达最大重试）: {} — {}", task.package_name, e)

    async def _do_download(self, task: DownloadTask, attempt: int):
        """单次下载尝试."""
        task.status = "downloading"
        self._save_task(task)

        part_path = Path(f"{task.save_path}.part")
        headers = {}
        if part_path.exists():
            task.downloaded_size = part_path.stat().st_size
            headers["Range"] = f"bytes={task.downloaded_size}-"

        # HEAD 预检 (首次尝试时)
        if attempt == 1 and not headers.get("Range"):
            if not await self._check_url_accessible(task.url):
                logger.info("HEAD 预检失败，直接走 Playwright: {}", task.package_name)
                await self._browser_download(task, part_path)
                if task.status == "error":
                    raise Exception(task.error or "浏览器下载失败")
                return

        settings = get_settings()
        proxy = settings.proxy if settings.proxy else None

        async with self._session.get(
            task.url,
            headers=headers,
            proxy=proxy,
            timeout=aiohttp.ClientTimeout(total=600),
        ) as resp:
            if resp.status not in (200, 206):
                if resp.status >= 400 or resp.status == 0:
                    logger.info("aiohttp HTTP {}，尝试 Playwright: {}", resp.status, task.package_name)
                    await self._browser_download(task, part_path)
                    if task.status == "error":
                        raise Exception(task.error or "浏览器下载失败")
                    return
                raise Exception(f"HTTP {resp.status}")

            content_length = resp.headers.get("Content-Length")
            if content_length:
                task.total_size = task.downloaded_size + int(content_length)

            # 架构识别: 从最终 URL（重定向后）或 Content-Disposition 文件名
            final_url = str(resp.url)
            cd = resp.headers.get("Content-Disposition", "")
            if cd and "filename=" in cd:
                fname = cd.split("filename=")[-1].strip('"')
            else:
                fname = final_url.split("/")[-1].split("?")[0]
            detected = self._detect_arch(final_url, fname)
            if detected and detected != "unknown":
                task.arch = detected
                task.abi_source = "url"

            os.makedirs(os.path.dirname(task.save_path), exist_ok=True)

            mode = "ab" if task.downloaded_size > 0 else "wb"
            last_sample_time = time.time()
            last_sample_bytes = task.downloaded_size
            chunk_size = getattr(settings, "download_chunk_size", 1024 * 1024)

            async with aiofiles.open(part_path, mode) as f:
                async for chunk in resp.content.iter_chunked(chunk_size):
                    await f.write(chunk)
                    task.downloaded_size += len(chunk)
                    now = time.time()
                    if now - last_sample_time >= 0.5:
                        elapsed = now - last_sample_time
                        bytes_delta = task.downloaded_size - last_sample_bytes
                        speed_bps = bytes_delta / elapsed if elapsed > 0 else 0
                        task.speed = self._format_speed(speed_bps)
                        if task.total_size > 0:
                            task.progress_pct = round(task.downloaded_size / task.total_size * 100, 1)
                        last_sample_time = now
                        last_sample_bytes = task.downloaded_size
                        self._save_task(task)
                        await self._notify_progress(task)

        # 完成
        if part_path.exists():
            final_path = Path(task.save_path)
            if final_path.exists():
                final_path.unlink()
            part_path.rename(final_path)

        task.status = "completed"
        task.progress_pct = 100.0
        task.speed = ""
        self._save_task(task)
        await self._notify_progress(task)
        logger.info("下载完成: {} → {} (arch={})", task.package_name, task.save_path, task.arch)

    async def _browser_download(self, task: DownloadTask, part_path: Path):
        """APKPure/APKCombo 防盗链下载（设计文档 5.1.6）.

        策略：这些站点的下载链接有严格的防盗链（Referer/Cookie/JS 生成），
        aiohttp 直接请求会返回 403 或 HTML 页面。使用 Playwright 的 download
        事件来捕获真实下载 — 浏览器上下文能通过所有验证。
        """
        import threading as _thr
        done_queue: queue.Queue = queue.Queue()

        is_apkpure = "apkpure" in task.url.lower()

        def _browser_worker():
            try:
                from patchright.sync_api import sync_playwright
                from backend.core.http_client import get_chromium_executable
                from backend.config import get_settings as _gs

                settings = _gs()
                chrome_exe = get_chromium_executable()
                if not chrome_exe:
                    done_queue.put(("error", "Chromium 未找到"))
                    return

                with sync_playwright() as p:
                    browser = p.chromium.launch(
                        headless=True, executable_path=chrome_exe,
                        args=["--no-sandbox"],
                        downloads_path=str(Path(task.save_path).parent),
                    )
                    context = browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        accept_downloads=True,
                        locale="zh-CN",
                    )
                    page = context.new_page()

                    # 监听 download 事件
                    download_completed = {"done": False, "path": "", "error": ""}

                    def _on_download(download):
                        try:
                            suggested = download.suggested_filename
                            # 从文件名识别架构
                            arch = DownloadManager._detect_arch("", suggested)
                            if arch != "unknown":
                                download_completed["arch"] = arch
                            save_as = str(Path(task.save_path).parent / suggested)
                            download.save_as(save_as)
                            download_completed["done"] = True
                            download_completed["path"] = save_as
                        except Exception as e:
                            download_completed["error"] = str(e)

                    page.on("download", _on_download)

                    try:
                        if is_apkpure and task.detail_url:
                            # 先去详情页建立 cookie 上下文
                            page.goto(task.detail_url, wait_until="domcontentloaded", timeout=20000)
                            page.wait_for_timeout(2000)

                        # 尝试直接访问下载 URL（此时已有 cookie 上下文）
                        page.goto(task.url, wait_until="domcontentloaded", timeout=30000)
                        page.wait_for_timeout(3000)

                        # 如果还没触发下载，点击页面中的下载按钮
                        if not download_completed["done"]:
                            for sel in [
                                'a[href*="download"]', 'a:has-text("Download")',
                                '.download-btn', '#download_link', 'a[data-dt-apkid]',
                                'button:has-text("Download")',
                            ]:
                                try:
                                    btn = page.locator(sel).first
                                    if btn.is_visible(timeout=1000):
                                        btn.click()
                                        page.wait_for_timeout(5000)
                                        if download_completed["done"]:
                                            break
                                except Exception:
                                    continue

                        # 等待下载
                        page.wait_for_timeout(8000)

                    except Exception as e:
                        logger.warning("浏览器导航异常: {}", e)
                    finally:
                        browser.close()

                    if download_completed["done"]:
                        apk_path = download_completed["path"]
                        size = os.path.getsize(apk_path) if os.path.exists(apk_path) else 0
                        if size > 50000:  # 至少 50KB
                            # 移动到目标路径
                            final_path = Path(task.save_path)
                            os.makedirs(final_path.parent, exist_ok=True)
                            if final_path.exists():
                                final_path.unlink()
                            os.rename(apk_path, str(final_path))
                            done_queue.put(("completed", size))
                        else:
                            done_queue.put(("error", f"下载文件过小 ({size} bytes)，非 APK"))
                    elif download_completed["error"]:
                        done_queue.put(("error", download_completed["error"]))
                    else:
                        done_queue.put(("error", "未触发下载事件，请手动在浏览器中打开下载链接"))

            except ImportError:
                done_queue.put(("error", "patchright 未安装"))
            except Exception as e:
                done_queue.put(("error", f"浏览器下载失败: {e}"))

        worker = _thr.Thread(target=_browser_worker, daemon=True)
        worker.start()
        worker.join(timeout=120)

        try:
            status, data = done_queue.get_nowait()
        except queue.Empty:
            task.status = "error"
            task.error = "浏览器下载超时"
            self._save_task(task)
            await self._notify_progress(task)
            return

        if status == "completed":
            task.downloaded_size = data if isinstance(data, int) else 0
            task.progress_pct = 100.0
            task.total_size = task.downloaded_size
            # 从文件名识别架构
            detected = download_completed.get("arch", "")
            if detected and task.arch == "unknown":
                task.arch = detected
                task.abi_source = "filename"
            if part_path.exists():
                final_path = Path(task.save_path)
                if final_path.exists():
                    final_path.unlink()
                part_path.rename(final_path)
            task.status = "completed"
            task.speed = ""
            self._save_task(task)
            await self._notify_progress(task)
            logger.info("浏览器下载完成: {} ({} bytes, arch={})", task.package_name, task.downloaded_size, task.arch)
        else:
            task.status = "error"
            task.error = str(data)
            self._save_task(task)
            await self._notify_progress(task)
            logger.warning("浏览器下载失败: {} — {}", task.package_name, data)

    async def _resume_tasks(self):
        """启动时恢复未完成的下载."""
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM download_tasks WHERE status IN ('downloading', 'pending', 'paused')"
        ).fetchall()
        for row in rows:
            task = DownloadTask(
                id=row["id"],
                url=row["url"],
                package_name=row["package_name"],
                version=row["version"],
                arch=row["arch"] or "",
                save_path=row["save_path"],
                total_size=row["total_size"],
                downloaded_size=row["downloaded_size"],
                status="paused",
            )
            await self._queue.put(task)
            self._active_tasks[task.id] = task
            logger.info("恢复下载任务: {}", task.package_name)

    async def _check_url_accessible(self, url: str) -> bool:
        """HEAD 请求验证下载链接是否可访问."""
        try:
            async with self._session.head(
                url, timeout=aiohttp.ClientTimeout(total=8), allow_redirects=True
            ) as resp:
                return resp.status in (200, 206)
        except Exception:
            return False

    @staticmethod
    def _detect_arch(url: str, filename: str) -> str:
        """从 URL 和文件名检测架构."""
        import re as _re
        text = f"{url} {filename}".lower()
        if _re.search(r'arm64|aarch64|arm64-v8a|arm64_v8a', text):
            return "arm64-v8a"
        if _re.search(r'armeabi-v7a|armeabi|armv7', text):
            return "armeabi-v7a"
        if _re.search(r'x86_64|x64', text):
            return "x86_64"
        if _re.search(r'(?<![_a-z])x86(?![_a-z])', text):
            return "x86"
        if _re.search(r'universal|nodpi|all_arch', text):
            return "universal"
        return "unknown"

    def _save_task(self, task: DownloadTask):
        """持久化任务到 SQLite."""
        conn = get_connection()
        conn.execute("""
            INSERT OR REPLACE INTO download_tasks
            (id, url, package_name, version, arch, abi_source, save_path,
             total_size, downloaded_size, status, retry_count, error, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            task.id, task.url, task.package_name, task.version, task.arch,
            task.abi_source, task.save_path, task.total_size, task.downloaded_size,
            task.status, task.retry_count, task.error,
        ))
        conn.commit()

    def pause_task(self, task_id: str) -> bool:
        """暂停下载."""
        if task_id in self._active_tasks:
            self._active_tasks[task_id].status = "paused"
            self._save_task(self._active_tasks[task_id])
            return True
        return False

    def resume_task(self, task_id: str) -> bool:
        """恢复暂停的下载."""
        if task_id in self._active_tasks:
            task = self._active_tasks[task_id]
            if task.status == "paused":
                task.status = "pending"
                self._save_task(task)
                asyncio.create_task(self._queue.put(task))
                return True
        return False

    def cancel_task(self, task_id: str) -> bool:
        """取消下载并删除 .part 文件."""
        if task_id in self._active_tasks:
            task = self._active_tasks[task_id]
            task.status = "cancelled"
            part_path = Path(f"{task.save_path}.part")
            if part_path.exists():
                part_path.unlink()
            self._save_task(task)
            del self._active_tasks[task_id]
            return True
        return False

    def get_all_tasks(self) -> list[DownloadTask]:
        return list(self._active_tasks.values())

    @staticmethod
    def _format_speed(bps: float) -> str:
        if bps < 1024:
            return f"{bps:.0f} B/s"
        elif bps < 1024 * 1024:
            return f"{bps / 1024:.1f} KB/s"
        else:
            return f"{bps / (1024 * 1024):.1f} MB/s"


# 全局单例
_download_manager: DownloadManager | None = None


def get_download_manager() -> DownloadManager:
    global _download_manager
    if _download_manager is None:
        settings = get_settings()
        _download_manager = DownloadManager(concurrency=settings.download_concurrency)
    return _download_manager
