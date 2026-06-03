@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo 游戏包名爬虫系统 v2.0 — 打包
echo ============================================
echo.

REM Build frontend first
echo [1/2] 构建前端...
cd frontend
call npm run build
cd ..

echo.
echo [2/2] PyInstaller 打包...
pyinstaller --clean --noconfirm build.spec

echo.
echo ============================================
echo 完成! 输出: dist\游戏包名爬虫系统.exe
echo ============================================
pause
