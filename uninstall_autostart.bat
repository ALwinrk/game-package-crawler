@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 游戏包名爬虫系统 — 卸载开机自启

echo ============================================
echo   游戏包名爬虫系统 — 卸载开机自启
echo ============================================
echo.

:: 检查管理员权限
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 请右键此文件 → "以管理员身份运行"
    echo.
    pause
    exit /b 1
)

:: 删除任务计划
schtasks /delete /tn "游戏包名爬虫系统" /f >nul 2>&1

if %errorlevel% equ 0 (
    echo ============================================
    echo   ✅ 卸载成功!
    echo ============================================
    echo.
    echo   开机自启已取消，下次开机不会自动启动
    echo   程序文件未被删除，可手动运行 exe
    echo.
    echo   如需重新安装: 右键运行 install_autostart.bat
) else (
    echo ============================================
    echo   ⚠️  未找到开机自启任务
    echo ============================================
    echo   可能已经卸载过了，无需再次操作
)

echo.
pause
