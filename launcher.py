"""游戏包名爬虫系统 v2.8 — 桌面启动器 (快速启动/关闭).

双击运行: 启动后端服务 → 打开浏览器 → 等待退出 → 清理.
"""

from __future__ import annotations

import ctypes
import os
import signal
import sys
import time
import threading
import webbrowser
from pathlib import Path


def get_app_dir() -> Path:
    """获取应用根目录（EXE 模式或开发模式）."""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


# ── 强制退出 (v2.8: 直接 os._exit, 不等待任何清理) ────

def _force_exit():
    """收到关闭信号时立即强制退出进程."""
    try:
        print("\n[v2.8] 收到关闭信号，强制退出...")
    except Exception:
        pass
    os._exit(0)


def _setup_exit_handler():
    """注册控制台关闭事件 + Unix 信号."""
    if sys.platform == "win32":
        @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)
        def _handler(ctrl_type):
            if ctrl_type == 2:  # CTRL_CLOSE_EVENT
                _force_exit()
                return True
            if ctrl_type in (0, 1):  # CTRL_C_EVENT, CTRL_BREAK_EVENT
                _force_exit()
                return True
            return False
        ctypes.windll.kernel32.SetConsoleCtrlHandler(_handler, True)
    else:
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda s, f: _force_exit())


def main():
    import uvicorn

    # 切换工作目录
    app_dir = get_app_dir()
    os.chdir(app_dir)

    # Chromium 路径 (PyInstaller EXE 模式)
    if getattr(sys, 'frozen', False):
        chromium_dir = app_dir / "chromium"
        if chromium_dir.exists():
            os.environ['_CHROMIUM_CHECKED'] = '1'

    # 确保数据目录
    Path("./data").mkdir(parents=True, exist_ok=True)
    Path("./downloads").mkdir(parents=True, exist_ok=True)
    Path("./logs").mkdir(parents=True, exist_ok=True)

    host = "127.0.0.1"
    port = 8000

    # 后台打开浏览器
    def open_browser():
        time.sleep(1.5)
        webbrowser.open(f"http://{host}:{port}")

    threading.Thread(target=open_browser, daemon=True).start()

    # v2.8: 注册强制退出处理器
    _setup_exit_handler()

    print(f"游戏包名爬虫系统 v2.8")
    print(f"启动服务: http://{host}:{port}")
    print("-" * 50)

    uvicorn.run(
        "backend.main:app",
        host=host,
        port=port,
        log_level="info",
        access_log=False,
        timeout_graceful_shutdown=2,  # v2.8: 秒级优雅关闭
    )


if __name__ == "__main__":
    main()
