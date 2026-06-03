"""FastAPI 主应用 — 入口、生命周期、中间件."""

from __future__ import annotations

import asyncio
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 生命周期管理."""
    # 启动
    settings = get_settings()
    setup_logging(
        log_dir="./logs",
        level=settings.log_level,
        retention=settings.log_retention_days,
    )
    logger = get_logger()
    logger.info("=" * 60)
    logger.info("游戏包名爬虫系统 启动中...")
    logger.info("=" * 60)

    # 初始化数据库
    init_db()
    logger.info("SQLite 数据库已初始化: data/crawler.db")

    # 启动下载管理器
    download_mgr = get_download_manager()

    # 注入进度回调（WebSocket 推送）
    from backend.api.websocket import get_ws_manager
    ws_mgr = get_ws_manager()

    async def on_download_progress(task):
        await ws_mgr.send_download_progress(task.to_dict())

    download_mgr.on_progress(on_download_progress)

    # 后台运行下载管理器
    download_task = asyncio.create_task(download_mgr.start())

    logger.info("下载管理器已启动 (并发={})", settings.download_concurrency)

    # 后台启动 Playwright 浏览器管理器（不阻塞服务就绪）
    from backend.core.browser_manager import get_browser_manager
    browser_mgr = get_browser_manager()
    asyncio.create_task(browser_mgr.start())

    logger.info("代理: {}", settings.proxy or "未配置")
    logger.info("启用站点: {}", ", ".join(settings.enabled_sites))

    yield

    # 关闭
    logger.info("正在关闭...")
    await download_mgr.stop()
    download_task.cancel()
    await browser_mgr.stop()
    close_db()
    logger.info("系统已关闭")


app = FastAPI(
    title="游戏包名爬虫系统",
    description="Android APK 版本排查工具 — 后端 API",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS — 允许前端跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
app.include_router(router)

# ── 静态文件（Vue3 前端）───────────────────────────────────

FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    # 挂载静态资源 (JS/CSS/图片等)
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/")
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str = ""):
        """SPA 回退 — 所有非 API 路径返回 index.html."""
        # API 路径不要被 catch-all 吃掉（路由优先级已经保证了但保险起见）
        if full_path.startswith("api/") or full_path.startswith("ws"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Not Found"}, status_code=404)

        index_path = FRONTEND_DIST / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return {"message": "Frontend not built. Run: cd frontend && npm run build"}

    logger = get_logger()
    logger.info("前端静态文件已挂载: {}", FRONTEND_DIST)


# ── 直接启动入口 ──────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info",
    )
