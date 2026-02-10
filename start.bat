@echo off
chcp 65001 >nul
setlocal

echo.
echo ========================================
echo    社内AIツールAPI - エンタープライズ版
echo ========================================
echo.

if "%1"=="" goto help
if "%1"=="edge" goto start_edge
if "%1"=="api" goto start_api
if "%1"=="all" goto start_all
if "%1"=="status" goto check_status
if "%1"=="install" goto install
goto help

:install
echo 依存関係をインストール中...
pip install -r requirements.txt
playwright install chromium
echo インストール完了
goto end

:start_edge
echo Edgeブラウザを起動中...
echo.
echo Edgeでログインを完了後、Edgeを稼働させたまま維持してください
echo 次に新しいターミナルで実行: start.bat api
echo.
python -m app.edge_manager start
goto end

:start_api
echo APIサービスを起動中...
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
goto end

:start_all
echo 一括起動（Edge + API）...
echo.
python -m app.edge_manager all
goto end

:check_status
echo ステータスを確認中...
python -m app.edge_manager status
goto end

:help
echo 使用方法: start.bat [コマンド]
echo.
echo コマンド:
echo   install   依存関係をインストール
echo   all       一括起動（推奨、ターミナル1つでOK）
echo   edge      Edgeブラウザを起動（段階的起動-ステップ1）
echo   api       APIサービスを起動（段階的起動-ステップ2）
echo   status    Edge接続状態を確認
echo.
echo 推奨使用方法:
echo   1. start.bat install    (初回インストール)
echo   2. start.bat all        (サービス起動、ログイン後Enterを押す)
echo.
echo 段階的起動方法（ターミナル2つ必要）:
echo   1. start.bat edge       (Edgeを起動してログイン)
echo   2. start.bat api        (新しいターミナルでAPIを起動)
echo.

:end
