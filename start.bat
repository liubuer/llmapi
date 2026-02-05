@echo off
chcp 65001 >nul
setlocal

echo.
echo ========================================
echo    内部AI工具API - 企业环境版
echo ========================================
echo.

if "%1"=="" goto help
if "%1"=="edge" goto start_edge
if "%1"=="api" goto start_api
if "%1"=="status" goto check_status
if "%1"=="install" goto install
goto help

:install
echo 安装依赖...
pip install -r requirements.txt
playwright install chromium
echo 安装完成
goto end

:start_edge
echo 启动Edge浏览器...
echo.
echo 请在Edge中完成登录后，保持Edge运行
echo 然后在新终端运行: start.bat api
echo.
python -m app.edge_manager start
goto end

:start_api
echo 启动API服务...
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
goto end

:check_status
echo 检查状态...
python -m app.edge_manager status
goto end

:help
echo 用法: start.bat [命令]
echo.
echo 命令:
echo   install   安装依赖
echo   edge      启动Edge浏览器（第一步）
echo   api       启动API服务（第二步）
echo   status    检查Edge连接状态
echo.
echo 使用步骤:
echo   1. start.bat install    (首次)
echo   2. start.bat edge       (启动Edge并登录)
echo   3. start.bat api        (新终端，启动API)
echo.

:end
