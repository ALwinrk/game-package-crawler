"""REST API 路由 — 所有端点定义."""

from __future__ import annotations

import asyncio
import uuid
from io import BytesIO
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
import openpyxl

from backend.api.websocket import get_ws_manager
from backend.batch.manager import BatchTask, BatchManager, get_batch_manager
from backend.config import get_settings, reload_settings
from backend.core.orchestrator import query_single, query_fast, query_slow, query_batch
from backend.core.cache import get_scraper_cache, get_slow_task_store
from backend.db.database import init_db
from backend.download.extractors import extract_download_links, pick_best_variant
from backend.download.manager import DownloadTask as DlTask, get_download_manager
from backend.logging_setup import get_logger
from backend.memo.store import get_memo_store

logger = get_logger()

router = APIRouter(prefix="/api")


# ── 健康检查 ───────────────────────────────────────────────

@router.get("/health")
async def health():
    return {"status": "ok"}


# ── 爬取 ───────────────────────────────────────────────────

# ── 爬取（三级模式）─────────────────────────────────────────

@router.post("/fetch")
async def fetch_package(data: dict[str, Any]):
    """单包名查询（默认快速排查: Google Play + APKPure + APKCombo）."""
    return await _do_fetch(data, query_fast)


@router.post("/fetch/fast")
async def fetch_fast(data: dict[str, Any]):
    """快速排查 — Google Play + APKPure + APKCombo（秒级响应）."""
    return await _do_fetch(data, query_fast)


@router.post("/fetch/slow")
async def fetch_slow(data: dict[str, Any]):
    """慢速排查 — APKMirror + APKVision（浏览器渲染，30-90s）.

    同步阻塞模式，推荐使用 /api/fetch/slow/async 异步提交.
    """
    return await _do_fetch(data, query_slow)


# ── 慢速异步任务 ───────────────────────────────────────────

@router.post("/fetch/slow/async")
async def fetch_slow_async(data: dict[str, Any]):
    """异步慢速排查 — 提交后台任务，立即返回 task_id.

    结果通过 GET /api/fetch/slow/result/{task_id} 轮询，
    或通过 WebSocket /api/ws/{task_id} 订阅完成通知。"""
    package = data.get("package", "").strip()
    if not package:
        raise HTTPException(400, "package is required")

    expected_version = data.get("expected_version")
    expected_version_code = data.get("expected_version_code")

    store = get_slow_task_store()
    task_id = store.create()

    async def _run_slow():
        try:
            result = await query_slow(package, expected_version, expected_version_code)
            store.complete(task_id, result)
            # WebSocket 推送完成通知
            ws_mgr = get_ws_manager()
            await ws_mgr.send_to_task(task_id, {
                "type": "slow_task_completed",
                "data": {"task_id": task_id, "status": "completed"},
            })
        except Exception as e:
            store.fail(task_id, str(e))
            ws_mgr = get_ws_manager()
            await ws_mgr.send_to_task(task_id, {
                "type": "slow_task_error",
                "data": {"task_id": task_id, "status": "error", "error": str(e)},
            })

    asyncio.create_task(_run_slow())

    return {
        "task_id": task_id,
        "status": "pending",
        "message": "任务已提交，预计 1-2 分钟完成",
    }


@router.get("/fetch/slow/result/{task_id}")
async def fetch_slow_result(task_id: str):
    """查询慢速异步任务结果."""
    store = get_slow_task_store()
    task = store.get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在或已过期")
    if task["status"] == "pending":
        return {"task_id": task_id, "status": "pending", "result": None}
    if task["status"] == "error":
        return {"task_id": task_id, "status": "error", "error": task["error"]}
    if task["status"] == "completed" and task["result"]:
        return {
            "task_id": task_id,
            "status": "completed",
            "result": task["result"].to_dict(),
        }
    return {"task_id": task_id, "status": task["status"]}


@router.post("/fetch/all")
async def fetch_all(data: dict[str, Any]):
    """全量排查 — 所有启用的站点（快速 + 慢速）."""
    return await _do_fetch(data, query_single)


async def _do_fetch(data: dict[str, Any], query_fn) -> dict:
    """统一处理单包名查询请求."""
    package = data.get("package", "").strip()
    if not package:
        raise HTTPException(400, "package is required")

    expected_version = data.get("expected_version")
    expected_version_code = data.get("expected_version_code")
    save_memo = data.get("save_memo", False)

    result = await query_fn(package, expected_version, expected_version_code)

    if save_memo and result.best_version:
        memo = get_memo_store()
        memo.upsert(
            package_name=package,
            version_code=result.best_version_code,
            version_name=result.best_version,
        )

    return result.to_dict()


@router.post("/fetch/batch")
async def fetch_batch(data: dict[str, Any]):
    """多包名查询（使用内部并发控制，默认最大5并发）."""
    packages = data.get("packages", [])
    mode = data.get("mode", "fast")
    if not packages:
        raise HTTPException(400, "packages is required")

    # 解析包名列表
    parsed = []
    for item in packages:
        if isinstance(item, str):
            parsed.append((item, None, None))
        else:
            parsed.append((
                item.get("package", ""),
                item.get("expected_version"),
                item.get("expected_version_code"),
            ))

    # 使用 orchestrator.query_batch 进行限流并发查询
    results_list = await query_batch(
        [(pkg, ev, evc) for pkg, ev, evc in parsed if pkg],
        mode=mode,
    )

    return {
        "results": [r.to_dict() for r in results_list],
        "mode": mode,
    }


# ── 批量 Excel ─────────────────────────────────────────────

@router.post("/batch/upload")
async def batch_upload(
    file: UploadFile = File(...),
):
    """上传 Excel 文件并启动批量排查."""
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(400, "仅支持 .xlsx / .xls 文件")

    content = await file.read()
    wb = openpyxl.load_workbook(BytesIO(content), read_only=True)
    ws = wb.active

    # 自动检测列
    headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
    pkg_col = None
    evc_col = None
    ev_col = None
    for i, h in enumerate(headers):
        h_lower = str(h).lower().replace(" ", "_") if h else ""
        if h_lower in ("package_name", "package", "packagename"):
            pkg_col = i
        elif h_lower in ("expected_version_code", "version_code", "versioncode"):
            evc_col = i
        elif h_lower in ("expected_version_name", "version_name", "versionname"):
            ev_col = i

    if pkg_col is None:
        raise HTTPException(400, "未找到 package_name 列")

    packages = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        pkg = str(row[pkg_col]).strip() if row[pkg_col] else None
        if not pkg:
            continue
        ev = str(row[ev_col]).strip() if ev_col is not None and row[ev_col] else None
        evc = str(row[evc_col]).strip() if evc_col is not None and row[evc_col] else None
        packages.append((pkg, ev, evc))

    wb.close()

    if not packages:
        raise HTTPException(400, "Excel 中无有效数据")

    task_id = f"batch_{uuid.uuid4().hex[:8]}"
    batch_task = BatchTask(
        task_id=task_id,
        filename=file.filename,
        packages=packages,
        excel_bytes=content,
        pkg_col=pkg_col,
        evc_col=evc_col or 0,
        ev_col=ev_col or 0,
    )

    # WebSocket 进度回调
    async def on_progress(bt: BatchTask):
        ws_mgr = get_ws_manager()
        await ws_mgr.send_to_task(task_id, {
            "type": "batch_progress",
            "data": bt.to_dict(),
        })

    batch_task.on_progress(on_progress)

    manager = get_batch_manager()
    await manager.enqueue(batch_task)
    asyncio.create_task(manager.run(batch_task))

    return {
        "task_id": task_id,
        "total": batch_task.total,
        "filename": file.filename,
    }


@router.get("/batch/{task_id}")
async def batch_status(task_id: str):
    """查询批量任务状态."""
    manager = get_batch_manager()
    task = manager.get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return task.to_dict()


@router.post("/batch/{task_id}/pause")
async def batch_pause(task_id: str):
    manager = get_batch_manager()
    if not manager.pause(task_id):
        raise HTTPException(404, "任务不存在")
    return {"ok": True}


@router.post("/batch/{task_id}/resume")
async def batch_resume(task_id: str):
    manager = get_batch_manager()
    if not manager.resume(task_id):
        raise HTTPException(404, "任务不存在")
    return {"ok": True}


@router.post("/batch/{task_id}/cancel")
async def batch_cancel(task_id: str):
    manager = get_batch_manager()
    if not manager.cancel(task_id):
        raise HTTPException(404, "任务不存在")
    return {"ok": True}


@router.get("/batch/{task_id}/download")
async def batch_download_result(task_id: str):
    """下载批量排查结果 Excel."""
    from backend.batch.manager import BatchTask as BT
    manager = get_batch_manager()
    task = manager.get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    if task.status != "completed":
        raise HTTPException(400, "任务未完成")

    output = BatchManager.export_to_excel(task)
    BT._cleanup_temp(task)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=batch_{task_id}.xlsx"},
    )


# ── 下载 ───────────────────────────────────────────────────

@router.post("/download")
async def download_apk(data: dict[str, Any]):
    """提交下载任务."""
    url = data.get("url", "").strip()
    package = data.get("package", "").strip()
    version = data.get("version", "latest")
    arch = data.get("arch", "unknown")
    detail_url = data.get("detail_url", "").strip()

    if not url or not package:
        raise HTTPException(400, "url and package are required")

    settings = get_settings()
    save_path = f"{settings.download_path}/{package}/{version}/{package}_{version}_{arch}.apk"

    task = DlTask(
        id=f"dl_{uuid.uuid4().hex[:8]}",
        url=url,
        package_name=package,
        version=version,
        arch=arch,
        save_path=save_path,
        detail_url=detail_url,
    )

    manager = get_download_manager()
    await manager.enqueue(task)

    return {"task_id": task.id, "status": "queued"}


@router.post("/download/batch")
async def download_batch(data: dict[str, Any]):
    """批量提交下载任务."""
    items = data.get("items", [])
    task_ids = []
    settings = get_settings()
    manager = get_download_manager()

    for item in items:
        url = item.get("url", "").strip()
        package = item.get("package", "").strip()
        version = item.get("version", "latest")
        arch = item.get("arch", "unknown")
        detail_url = item.get("detail_url", "").strip()

        if not url or not package:
            continue

        save_path = f"{settings.download_path}/{package}/{version}/{package}_{version}_{arch}.apk"
        task = DlTask(
            id=f"dl_{uuid.uuid4().hex[:8]}",
            url=url,
            package_name=package,
            version=version,
            arch=arch,
            save_path=save_path,
            detail_url=detail_url,
        )
        await manager.enqueue(task)
        task_ids.append(task.id)

    return {"queued": len(task_ids), "task_ids": task_ids}


@router.get("/download/tasks")
async def download_tasks():
    """获取所有下载任务状态."""
    manager = get_download_manager()
    return {"tasks": [t.to_dict() for t in manager.get_all_tasks()]}


@router.post("/download/{task_id}/pause")
async def download_pause(task_id: str):
    manager = get_download_manager()
    if not manager.pause_task(task_id):
        raise HTTPException(404, "任务不存在")
    return {"ok": True}


@router.post("/download/{task_id}/cancel")
async def download_cancel(task_id: str):
    manager = get_download_manager()
    if not manager.cancel_task(task_id):
        raise HTTPException(404, "任务不存在")
    return {"ok": True}


# ── 记忆化 ─────────────────────────────────────────────────

@router.get("/memo/{package_name}")
async def memo_get(package_name: str):
    """查询包名的历史版本信息."""
    store = get_memo_store()
    result = store.get(package_name)
    if not result:
        return {"found": False}
    return {"found": True, "data": result}


@router.post("/memo")
async def memo_save(data: dict[str, Any]):
    """保存版本信息到记忆."""
    package = data.get("package", "").strip()
    if not package:
        raise HTTPException(400, "package is required")

    store = get_memo_store()
    store.upsert(
        package_name=package,
        version_code=data.get("version_code"),
        version_name=data.get("version_name"),
    )
    return {"ok": True}


@router.get("/memo")
async def memo_list(limit: int = 100):
    """列出所有记忆."""
    store = get_memo_store()
    return {"items": store.list_all(limit)}


# ── 配置 ───────────────────────────────────────────────────

@router.get("/config")
async def config_get():
    settings = get_settings()
    return settings.model_dump(exclude_none=True)


@router.patch("/config")
async def config_update(data: dict[str, Any]):
    settings = get_settings()
    settings.update(data)
    reload_settings()
    return {"ok": True}


# ── 缓存管理 ───────────────────────────────────────────────

@router.post("/cache/clear")
async def cache_clear():
    """清除所有爬虫结果缓存."""
    cache = get_scraper_cache()
    count = await cache.clear()
    return {"ok": True, "cleared": count}


# ── WebSocket ──────────────────────────────────────────────

@router.websocket("/ws")
async def websocket_global(websocket: WebSocket):
    """全局 WebSocket：接收下载进度、批量任务通知."""
    ws_mgr = get_ws_manager()
    await ws_mgr.connect(websocket)
    try:
        while True:
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        ws_mgr.disconnect(websocket)


@router.websocket("/ws/{task_id}")
async def websocket_task(websocket: WebSocket, task_id: str):
    """任务专用 WebSocket：订阅特定批量任务的进度."""
    ws_mgr = get_ws_manager()
    await ws_mgr.connect(websocket, task_id=task_id)
    try:
        while True:
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        ws_mgr.disconnect(websocket, task_id=task_id)


# ── 下载链接提取 ───────────────────────────────────────────

@router.post("/extract-links")
async def extract_links(data: dict[str, Any]):
    """从指定源的详情页提取下载链接."""
    source = data.get("source", "").strip()
    detail_url = data.get("detail_url", "").strip()
    package = data.get("package", "").strip()
    version = data.get("version", "").strip()

    if not source or not detail_url:
        raise HTTPException(400, "source and detail_url are required")

    variants = await extract_download_links(source, detail_url, package=package, version=version)
    best = pick_best_variant(variants)

    return {
        "variants": [
            {"url": v.url, "arch": v.arch, "size": v.size, "source": v.source}
            for v in variants
        ],
        "best": {"url": best.url, "arch": best.arch, "source": best.source} if best else None,
    }
