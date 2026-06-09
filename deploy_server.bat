@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 游戏包名爬虫系统 v3.0 — 服务器部署

echo ============================================
echo   游戏包名爬虫系统 v3.0 — 服务器部署
echo ============================================
echo.

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 请右键 → 以管理员身份运行
    pause
    exit /b 1
)

:: 1. 防火墙放行 8000 端口
echo [1/3] 配置 Windows 防火墙...
netsh advfirewall firewall add rule name="Crawler8000" dir=in action=allow protocol=tcp localport=8000 >nul 2>&1
echo   端口 8000 已放行

:: 2. 开机自启
echo [2/3] 设置开机自启...
set "EXE_PATH=%~dp0游戏包名爬虫系统.exe"
schtasks /delete /tn "游戏包名爬虫系统" /f >nul 2>&1
schtasks /create /tn "游戏包名爬虫系统" /tr "\"%EXE_PATH%\"" /sc onstart /delay 0000:30 /rl highest /f >nul 2>&1
echo   开机自启已设置

:: 3. 启动
echo [3/3] 启动服务...
start "" "%EXE_PATH%"
echo   服务已启动

echo ============================================
echo   ✅ 部署完成!
echo ============================================
echo.
echo   内网: http://localhost:8000
echo   外网: http://你的IP:8000
echo.
echo   ⚠️ 如果外网不通，进腾讯云控制台 →
echo      安全组 → 添加入站规则: TCP 8000 0.0.0.0/0
pause
