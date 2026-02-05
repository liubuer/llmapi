#!/bin/bash

case "$1" in
    install)
        echo "安装依赖..."
        pip install -r requirements.txt
        playwright install chromium
        ;;
    edge)
        echo "启动Edge浏览器..."
        python -m app.edge_manager start
        ;;
    api)
        echo "启动API服务..."
        python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
        ;;
    status)
        python -m app.edge_manager status
        ;;
    *)
        echo "用法: ./start.sh [install|edge|api|status]"
        echo ""
        echo "步骤:"
        echo "  1. ./start.sh edge   # 启动Edge并登录"
        echo "  2. ./start.sh api    # 新终端启动API"
        ;;
esac
