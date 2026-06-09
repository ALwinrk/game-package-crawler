@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 游戏包名爬虫系统 — 安装开机自启

echo ============================================
echo   游戏包名爬虫系统 — 安装开机自启
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

:: 确认 exe 存在
set "EXE_PATH=%~dp0dist\游戏包名爬虫系统.exe"
if not exist "%EXE_PATH%" (
    echo [错误] 未找到程序文件: dist\游戏包名爬虫系统.exe
    echo        请先将 exe 放到 dist 目录下再运行本脚本
    echo.
    pause
    exit /b 1
)

echo [信息] 程序路径: %EXE_PATH%
echo.

:: 先删除旧任务（如果存在）
schtasks /delete /tn "游戏包名爬虫系统" /f >nul 2>&1

:: 创建任务计划: 开机自启, 延迟30秒, 最高权限, 失败后自动重启
schtasks /create ^
    /tn "游戏包名爬虫系统" ^
    /tr "\"%EXE_PATH%\"" ^
    /sc onstart ^
    /delay 0000:30 ^
    /rl highest ^
    /f >nul 2>&1

if %errorlevel% equ 0 (
    echo ============================================
    echo   ✅ 安装成功!
    echo ============================================
    echo.
    echo   开机时将自动延迟 30 秒启动程序
    echo   程序窗口会显示在桌面上（Ctrl+C 可关闭）
    echo.
    echo   任务名称: 游戏包名爬虫系统
    echo   程序路径: %EXE_PATH%
    echo.
    echo   如需卸载: 右键运行 uninstall_autostart.bat
) else (
    echo ============================================
    echo   ❌ 安装失败
    echo ============================================
    echo   请检查是否有杀毒软件拦截
)

echo.
pause
