"""游戏包名爬虫系统 v3.0 — 桌面启动器 (快速启动/关闭).

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
import shutil
from pathlib import Path


def get_app_dir() -> Path:
    """获取持久数据目录 (EXE 所在目录或开发目录)."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent  # EXE 所在目录, 数据持久化
    return Path(__file__).parent


def get_bundle_dir() -> Path:
    """获取 PyInstaller 打包资源目录 (chromium, 预置 config.json)."""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)  # 临时解压目录, 仅用于只读资源
    return Path(__file__).parent


# ── 强制退出 (v3.0: 直接 os._exit, 不等待任何清理) ────

def _force_exit():
    """收到关闭信号时立即强制退出进程."""
    try:
        print("\n[v3.0] 收到关闭信号，强制退出...")
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

    # 切换工作目录 (EXE 所在目录, 数据持久化)
    app_dir = get_app_dir()
    try:
        os.chdir(app_dir)
    except OSError as e:
        print(f"[错误] 无法切换工作目录: {app_dir} — {e}")
        sys.exit(1)

    # EXE 模式: 首次运行复制预置 config.json + Chromium, 设置持久路径
    if getattr(sys, 'frozen', False):
        bundle_dir = get_bundle_dir()
        chromium_dir = bundle_dir / "chromium"
        if chromium_dir.exists():
            # v3.3: 复制 Chromium 到持久目录, 避免从 Temp 目录运行被杀软拦截
            local_chromium = app_dir / "chromium"
            if not local_chromium.exists():
                try:
                    print("[启动] 首次运行, 复制 Chromium 到持久目录...")
                    shutil.copytree(chromium_dir, local_chromium)
                    print(f"[启动] Chromium 已复制: {local_chromium}")
                except OSError as e:
                    print(f"[警告] 复制 Chromium 失败: {e}, 将使用临时目录")
            os.environ['_CHROMIUM_CHECKED'] = '1'

        # 复制预置 config.json (如果目标位置不存在)
        bundle_config = bundle_dir / "config.json"
        local_config = app_dir / "config.json"
        if not local_config.exists() and bundle_config.exists():
            try:
                shutil.copy(bundle_config, local_config)
            except OSError as e:
                print(f"[警告] 复制 config.json 失败: {e}, 将使用默认配置")

    # 确保数据目录
    for subdir in ("data", "downloads", "logs"):
        try:
            Path(f"./{subdir}").mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"[警告] 创建目录 ./{subdir} 失败: {e}")

    host = "127.0.0.1"
    port = 8000

    # v3.5: 自动杀掉占用端口的旧进程
    import socket as _socket
    _sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    _in_use = _sock.connect_ex((host, port)) == 0
    _sock.close()
    if _in_use:
        print(f"[启动] 端口 {port} 已被占用, 正在终止旧进程...")
        if sys.platform == "win32":
            import subprocess as _sp
            try:
                result = _sp.run(
                    f'netstat -ano | findstr :{port} | findstr LISTENING',
                    capture_output=True, text=True, shell=True,
                )
                for line in result.stdout.strip().split('\n'):
                    parts = line.split()
                    if parts and parts[-1].isdigit():
                        pid = parts[-1]
                        _sp.run(f'taskkill /F /PID {pid}', capture_output=True, shell=True)
                        print(f"[启动] 已终止旧进程 PID={pid}")
            except Exception:
                pass
        # 短暂等待端口释放
        time.sleep(1.5)

    # 后台打开浏览器
    def open_browser():
        time.sleep(2.0)
        webbrowser.open(f"http://{host}:{port}")

    threading.Thread(target=open_browser, daemon=True).start()

    # v3.0: 注册强制退出处理器
    _setup_exit_handler()

    print(f"游戏包名爬虫系统 v3.6")
    print(f"启动服务: http://{host}:{port}")
    print(f"工作目录: {os.getcwd()}")
    print("-" * 50)

    try:
        uvicorn.run(
            "backend.main:app",
            host=host,
            port=port,
            log_level="info",
            access_log=False,
            timeout_graceful_shutdown=2,
        )
    except KeyboardInterrupt:
        print("\n用户中断, 正在退出...")
    except Exception as e:
        print(f"\n[服务异常] {e}")
        import traceback
        traceback.print_exc()
        print("\n按 Enter 键退出...")
        input()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[致命错误] {e}")
        import traceback
        traceback.print_exc()
        print("\n按 Enter 键退出...")
        input()
