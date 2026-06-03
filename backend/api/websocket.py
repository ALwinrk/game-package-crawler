"""WebSocket 管理器 — 进度推送、任务状态广播."""

from __future__ import annotations

import json
from typing import Any

from fastapi import WebSocket

from backend.logging_setup import get_logger

logger = get_logger()


class WSManager:
    """WebSocket 连接管理器.

    支持按 task_id 分组推送，也可全局广播。
    """

    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}   # task_id → [ws, ...]
        self._global_connections: list[WebSocket] = []       # 无特定 task_id 的连接

    async def connect(self, websocket: WebSocket, task_id: str | None = None):
        """接受 WebSocket 连接."""
        await websocket.accept()
        if task_id:
            self._connections.setdefault(task_id, []).append(websocket)
            logger.debug("WS 连接: task_id={} (现有 {} 个)", task_id, len(self._connections[task_id]))
        else:
            self._global_connections.append(websocket)
            logger.debug("WS 全局连接 (现有 {} 个)", len(self._global_connections))

    def disconnect(self, websocket: WebSocket, task_id: str | None = None):
        """断开连接."""
        if task_id and task_id in self._connections:
            conns = self._connections[task_id]
            if websocket in conns:
                conns.remove(websocket)
            if not conns:
                del self._connections[task_id]
        elif websocket in self._global_connections:
            self._global_connections.remove(websocket)

    async def send_to_task(self, task_id: str, data: dict[str, Any]):
        """向订阅特定 task_id 的连接推送消息."""
        message = json.dumps(data, ensure_ascii=False)
        dead = []
        for ws in self._connections.get(task_id, []):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, task_id)

    async def broadcast(self, data: dict[str, Any]):
        """全局广播."""
        message = json.dumps(data, ensure_ascii=False)
        dead = []
        for ws in self._global_connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def send_download_progress(self, task: dict):
        """推送下载进度."""
        await self.broadcast({
            "type": "download_progress",
            "data": task,
        })

    async def send_batch_progress(self, batch_task: dict):
        """推送批量任务进度."""
        await self.broadcast({
            "type": "batch_progress",
            "data": batch_task,
        })


# 全局单例
_ws_manager: WSManager | None = None


def get_ws_manager() -> WSManager:
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = WSManager()
    return _ws_manager
