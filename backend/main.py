"""FastAPI 主应用 — 入口、生命周期、中间件 + 快速启动/关闭 (v2.8)."""

from __future__ import annotations

import asyncio
import ctypes
import os
import signal
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.api.routes import router
from backend.config import get_settings
from backend.db.database import init_db, close_db
from backend.download.manager import get_download_manager, DownloadManager
from backend.logging_setup import setup_logging, get_logger


# ── 浏览器就绪事件 (v2.8: 后台初始化, 不阻塞服务启动) ────
browser_ready = asyncio.Event()


# ── 强制退出 (v2.8: 秒级关闭) ──────────────────────────

_force_exit = False

def _do_force_exit():
    global _force_exit
    if _force_exit:
        return
    _force_exit = True
    try:
        print("[v2.8] 收到退出信号，强制关闭...")
        loop = asyncio.get_running_loop()
        tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
    except Exception:
        pass
    os._exit(0)


def setup_console_handler():
    """注册 Windows 控制台关闭事件 + Unix 信号处理."""
    if sys.platform == "win32":
        @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)
        def _handler(ctrl_type):
            if ctrl_type == 2:  # CTRL_CLOSE_EVENT
                _do_force_exit()
                return True
            return False
        ctypes.windll.kernel32.SetConsoleCtrlHandler(_handler, True)
    else:
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda s, f: _do_force_exit())


# ── 生命周期 ────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 生命周期管理 (v2.8: 后台初始化 + 快速关闭)."""
    # 启动
    settings = get_settings()
    setup_logging(
        log_dir="./logs",
        level=settings.log_level,
        retention=settings.log_retention_days,
    )
    logger = get_logger()
    logger.info("=" * 60)
    logger.info("游戏包名爬虫系统 v2.8 启动中...")
    logger.info("=" * 60)

    # 数据库 (同步, 极快)
    init_db()
    logger.info("SQLite 数据库已初始化: data/crawler.db")

    # 下载管理器
    download_mgr = get_download_manager()
    from backend.api.websocket import get_ws_manager
    ws_mgr = get_ws_manager()

    async def on_download_progress(task):
        await ws_mgr.send_download_progress(task.to_dict())

    download_mgr.on_progress(on_download_progress)
    download_task = asyncio.create_task(download_mgr.start())
    logger.info("下载管理器已启动 (并发={})", settings.download_concurrency)

    # 浏览器管理器 — v2.8: 完全后台初始化，不阻塞服务就绪
    async def _init_browser_background():
        try:
            from backend.core.browser_manager import get_browser_manager
            mgr = get_browser_manager()
            await mgr.start()
            browser_ready.set()
            logger.info("Playwright 浏览器就绪")
        except Exception as e:
            logger.warning("浏览器初始化失败 (慢速源不可用): {}", e)

    asyncio.create_task(_init_browser_background())

    logger.info("代理: {}", settings.proxy or "未配置")
    logger.info("启用站点: {}", ", ".join(settings.enabled_sites))
    logger.info("服务就绪 — 前端可访问 http://127.0.0.1:8000")

    yield

    # 关闭 — v2.8: 快速退出
    logger.info("正在关闭...")
    download_task.cancel()
    try:
        await asyncio.wait_for(download_mgr.stop(), timeout=1.5)
    except asyncio.TimeoutError:
        pass
    close_db()
    logger.info("系统已关闭")


# ── FastAPI 应用 ────────────────────────────────────────

app = FastAPI(
    title="游戏包名爬虫系统",
    description="Android APK 版本排查工具 — 后端 API",
    version="2.8.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


# ── 健康检查 (v2.8) ─────────────────────────────────────

@app.get("/api/ready")
async def ready():
    return {"status": "ready" if browser_ready.is_set() else "loading"}


# ── 静态文件 (Vue3 前端) ─────────────────────────────────

FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/")
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str = ""):
        if full_path.startswith("api/") or full_path.startswith("ws"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        index_path = FRONTEND_DIST / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return {"message": "Frontend not built. Run: cd frontend && npm run build"}

    get_logger().info("前端静态文件已挂载: {}", FRONTEND_DIST)


# ── 直接启动入口 ─────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    setup_console_handler()
    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=8000,
        timeout_graceful_shutdown=2,
        log_level="info",
    )
