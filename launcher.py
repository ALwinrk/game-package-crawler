"""游戏包名爬虫系统 v2.0 — 桌面启动器.

双击运行: 启动后端服务 → 打开浏览器 → 等待退出 → 清理.
"""

from __future__ import annotations

import os
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


def main():
    import uvicorn

    # 切换工作目录到应用根目录
    app_dir = get_app_dir()
    os.chdir(app_dir)

    # 设置 Chromium 路径（PyInstaller 打包后 chrome 在指定目录）
    if getattr(sys, 'frozen', False) and 'LOCALAPPDATA' not in os.environ.get('_CHROMIUM_CHECKED', ''):
        chromium_dir = app_dir / "chromium"
        if chromium_dir.exists():
            # 让 get_chromium_executable() 能找到
            os.environ['_CHROMIUM_CHECKED'] = '1'

    # 确保数据目录存在
    Path("./data").mkdir(parents=True, exist_ok=True)
    Path("./downloads").mkdir(parents=True, exist_ok=True)
    Path("./logs").mkdir(parents=True, exist_ok=True)

    host = "127.0.0.1"
    port = 8000

    # 在独立线程中启动浏览器（等服务器就绪后）
    def open_browser():
        time.sleep(2)
        webbrowser.open(f"http://{host}:{port}")

    threading.Thread(target=open_browser, daemon=True).start()

    print(f"游戏包名爬虫系统 v2.0")
    print(f"启动服务: http://{host}:{port}")
    print(f"按 Ctrl+C 退出")
    print("-" * 50)

    uvicorn.run(
        "backend.main:app",
        host=host,
        port=port,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
