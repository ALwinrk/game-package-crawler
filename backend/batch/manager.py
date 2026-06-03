"""批量任务管理器 — asyncio.Queue + BackgroundTasks.

处理 Excel 批量排查，支持暂停/继续/取消。
每个任务独立协程运行，通过 WebSocket 推送进度。
"""

from __future__ import annotations

import asyncio
import uuid
from io import BytesIO
from pathlib import Path

import openpyxl

from backend.db.database import get_connection
from backend.logging_setup import get_logger
from backend.models.schemas import FetchResult

logger = get_logger()


class BatchTask:
    """单个批量任务."""

    def __init__(
        self,
        task_id: str,
        filename: str,
        packages: list[tuple[str, str | None, str | None]],
        excel_bytes: bytes = b"",
        pkg_col: int = 0,
        evc_col: int = 0,
        ev_col: int = 0,
    ):
        self.id = task_id
        self.filename = filename
        self.packages = packages
        self.total = len(packages)
        self.completed = 0
        self.status = "pending"
        self.results: list[FetchResult] = []
        self.stop_event = asyncio.Event()
        self._progress_callbacks: list[callable] = []
        # 原始 Excel 信息 (用于完成后在原文件写入结果)
        self.excel_bytes = excel_bytes
        self.pkg_col = pkg_col
        self.evc_col = evc_col
        self.ev_col = ev_col

    def on_progress(self, callback):
        self._progress_callbacks.append(callback)

    async def notify_progress(self):
        for cb in self._progress_callbacks:
            try:
                await cb(self)
            except Exception:
                pass

    def to_dict(self) -> dict:
        # 统计结果
        matched = newer = older = not_found = 0
        for r in self.results:
            s = r.compare_status.value
            if s == "matched": matched += 1
            elif s == "newer": newer += 1
            elif s == "older": older += 1
            else: not_found += 1

        return {
            "id": self.id,
            "filename": self.filename,
            "total": self.total,
            "completed": self.completed,
            "status": self.status,
            "progress_pct": round(self.completed / self.total * 100, 1) if self.total else 0,
            "summary": {
                "matched": matched,
                "newer": newer,
                "older": older,
                "not_found": not_found,
            },
        }


class BatchManager:
    """批量任务管理器.

    使用 asyncio.Queue 接收任务，独立协程处理，
    支持暂停/继续/取消。
    """

    def __init__(self):
        self._queue: asyncio.Queue[BatchTask] = asyncio.Queue()
        self._active_tasks: dict[str, BatchTask] = {}

    async def enqueue(self, task: BatchTask) -> None:
        """添加批量任务."""
        await self._queue.put(task)
        self._active_tasks[task.id] = task
        self._save_task(task)
        logger.info("批量任务已入队: {} ({} 行)", task.filename, task.total)

    async def run(self, task: BatchTask):
        """执行批量任务（默认快速模式：Google Play + APKPure + APKCombo）."""
        from backend.core.orchestrator import query_fast

        task.status = "running"
        self._save_task(task)
        await task.notify_progress()

        for i, (pkg, ev, evc) in enumerate(task.packages):
            # 检查暂停/取消
            if task.stop_event.is_set():
                if task.status == "cancelled":
                    self._save_task(task)
                    await task.notify_progress()
                    return
                # 暂停等待
                while task.status == "paused" and not task.stop_event.is_set():
                    await asyncio.sleep(0.5)
                task.stop_event.clear()

            try:
                result = await query_fast(pkg, ev, evc)
                task.results.append(result)
            except Exception as e:
                logger.warning("批量任务行 {} 失败: {} — {}", i + 1, pkg, e)
                from backend.models.schemas import CompareStatus
                result = FetchResult(
                    package=pkg,
                    error=str(e),
                    compare_status=CompareStatus.ERROR,
                )
                task.results.append(result)

            task.completed = i + 1
            self._save_task(task)
            await task.notify_progress()

            # 请求间隔
            from backend.config import get_settings
            settings = get_settings()
            if settings.request_interval > 0:
                await asyncio.sleep(settings.request_interval)

        task.status = "completed"
        self._save_task(task)
        await task.notify_progress()
        logger.info("批量任务完成: {} ({}/{})", task.filename, task.completed, task.total)

    def pause(self, task_id: str) -> bool:
        if task_id in self._active_tasks:
            task = self._active_tasks[task_id]
            task.status = "paused"
            task.stop_event.set()
            return True
        return False

    def resume(self, task_id: str) -> bool:
        if task_id in self._active_tasks:
            task = self._active_tasks[task_id]
            if task.status == "paused":
                task.status = "running"
                task.stop_event.clear()
            return True
        return False

    def cancel(self, task_id: str) -> bool:
        if task_id in self._active_tasks:
            task = self._active_tasks[task_id]
            task.status = "cancelled"
            task.stop_event.set()
            return True
        return False

    def get_task(self, task_id: str) -> BatchTask | None:
        return self._active_tasks.get(task_id)

    def get_all_tasks(self) -> list[BatchTask]:
        return list(self._active_tasks.values())

    def _save_task(self, task: BatchTask):
        conn = get_connection()
        conn.execute("""
            INSERT OR REPLACE INTO batch_tasks
            (id, filename, total_rows, completed_rows, status, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (task.id, task.filename, task.total, task.completed, task.status))
        conn.commit()

    @staticmethod
    def export_to_excel(task: BatchTask) -> BytesIO:
        """在原 Excel 写入排查结果 (排查时间 + 版本号 + 对比状态).

        逻辑:
          1. 加载原始 Excel
          2. 在包名列右侧插入三列: 排查时间, 当前后台版本号(vc), 对比状态
          3. 若已有列则复用, 否则新建
          4. 返回修改后的文件
        """
        from datetime import datetime
        from openpyxl.styles import Alignment, Font, PatternFill

        HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        HEADER_FONT = Font(color="FFFFFF", bold=True)
        CENTER = Alignment(horizontal="center")

        wb = openpyxl.load_workbook(BytesIO(task.excel_bytes))
        ws = wb.active

        pkg_col = task.pkg_col
        if pkg_col <= 0:
            for c in range(1, ws.max_column + 1):
                h = str(ws.cell(1, c).value or "").lower().replace(" ", "").replace("_", "")
                if h in ("packagename", "package", "pkg"):
                    pkg_col = c
                    break
            if pkg_col <= 0:
                pkg_col = 1

        # 三列配置: (列名, 关键词, 列宽, 取值函数)
        columns = [
            ("排查时间", ["排查时间", "checktime", "check_time"], 18,
             lambda r, pkg: datetime.now().strftime("%Y-%m-%d %H:%M")),
            ("当前后台版本号(vc)", ["当前后台版本号", "版本号(vc)", "versioncode", "version_code", "vc"], 18,
             lambda r, pkg: r.best_version_code or "-"),
            ("对比状态", ["对比状态", "状态", "status"], 14,
             lambda r, pkg: {"matched": "已匹配", "newer": "有新版本", "older": "版本较旧",
                              "not_found": "未找到", "error": "错误"}.get(r.compare_status.value, r.compare_status.value) if r else "-"),
        ]

        # 查找或插入列
        check_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        result_map: dict[str, any] = {}
        for r in task.results:
            result_map[r.package] = r

        col_positions = []
        for col_name, keywords, width, _ in columns:
            found = 0
            for c in range(1, ws.max_column + 1):
                h = str(ws.cell(1, c).value or "").lower().replace(" ", "").replace("_", "")
                for kw in keywords:
                    if kw.replace(" ", "").replace("_", "") in h:
                        found = c
                        break
                if found:
                    break
            if not found:
                # 在现有列右侧插入
                insert_at = ws.max_column + 1
                ws.insert_cols(insert_at)
                found = insert_at
                cell = ws.cell(1, found, col_name)
                cell.font = HEADER_FONT
                cell.fill = HEADER_FILL
                cell.alignment = CENTER
            col_positions.append(found)
            ws.column_dimensions[openpyxl.utils.get_column_letter(found)].width = width

        # 写入数据
        filled = 0
        for row in range(2, ws.max_row + 1):
            pkg = str(ws.cell(row, pkg_col).value or "").strip()
            if not pkg:
                continue
            r = result_map.get(pkg)
            for ci, (_, _, _, getter) in enumerate(columns):
                val = getter(r, pkg) if r else getter(None, pkg) if ci == 0 else "-"
                ws.cell(row, col_positions[ci], val).alignment = CENTER
            if r and r.best_version_code and r.best_version_code != "-":
                filled += 1

        output = BytesIO()
        wb.save(output)
        output.seek(0)
        return output


# 全局单例
_batch_manager: BatchManager | None = None


def get_batch_manager() -> BatchManager:
    global _batch_manager
    if _batch_manager is None:
        _batch_manager = BatchManager()
    return _batch_manager
