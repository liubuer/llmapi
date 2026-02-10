#!/bin/bash

case "$1" in
    install)
        echo "依存関係をインストール中..."
        pip install -r requirements.txt
        playwright install chromium
        ;;
    edge)
        echo "Edgeブラウザを起動中..."
        python -m app.edge_manager start
        ;;
    api)
        echo "APIサービスを起動中..."
        python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
        ;;
    status)
        python -m app.edge_manager status
        ;;
    *)
        echo "使用方法: ./start.sh [install|edge|api|status]"
        echo ""
        echo "手順:"
        echo "  1. ./start.sh edge   # Edgeを起動してログイン"
        echo "  2. ./start.sh api    # 新しいターミナルでAPIを起動"
        ;;
esac
