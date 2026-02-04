#!/bin/bash

# 内部AI工具API启动脚本 - 企业环境优化版

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
print_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }
print_blue() { echo -e "${BLUE}$1${NC}"; }

# 检查Python环境
check_python() {
    if ! command -v python3 &> /dev/null; then
        print_error "Python3 未安装"
        exit 1
    fi
    print_info "Python版本: $(python3 --version)"
}

# 检查依赖
check_dependencies() {
    print_info "检查依赖..."
    
    if [ ! -d "venv" ]; then
        print_warn "虚拟环境不存在，正在创建..."
        python3 -m venv venv
    fi
    
    source venv/bin/activate
    pip install -q -r requirements.txt
    
    # 检查Playwright浏览器
    if ! python -c "from playwright.sync_api import sync_playwright" 2>/dev/null; then
        print_info "安装Playwright..."
        pip install playwright
    fi
    
    # 安装Chromium
    print_info "确保Chromium浏览器已安装..."
    playwright install chromium 2>/dev/null || true
}

# 检查登录状态
check_login() {
    source venv/bin/activate
    python -m app.browser_manager --check
    return $?
}

# 手动登录
do_login() {
    print_info "启动手动登录流程..."
    source venv/bin/activate
    
    if [ -n "$1" ]; then
        python -m app.browser_manager --login "$1"
    else
        python -m app.browser_manager --login
    fi
}

# 测试浏览器
test_browser() {
    print_info "测试浏览器..."
    source venv/bin/activate
    
    export BROWSER_HEADLESS=false
    
    if [ -n "$1" ]; then
        python -m app.browser_manager --test "$1"
    else
        python -m app.browser_manager --test
    fi
}

# 启动服务
start_server() {
    print_info "启动API服务..."
    source venv/bin/activate
    
    mkdir -p logs
    
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
}

# 生产模式启动
start_production() {
    print_info "启动API服务（生产模式）..."
    source venv/bin/activate
    
    mkdir -p logs
    
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
}

# 分析页面
analyze_page() {
    print_info "启动页面分析工具..."
    source venv/bin/activate
    python tools/analyze_page.py "$@"
}

# 清理数据
clean_data() {
    print_warn "这将删除所有浏览器数据和登录状态！"
    read -p "确认删除？(y/N): " confirm
    
    if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
        source venv/bin/activate
        python -m app.browser_manager --clean
        rm -rf auth_state/
        print_info "数据已清理"
    else
        print_info "已取消"
    fi
}

# 运行测试
run_tests() {
    print_info "运行测试..."
    source venv/bin/activate
    pytest tests/ -v
}

# 显示帮助
show_help() {
    echo ""
    print_blue "=========================================="
    print_blue "    内部AI工具 API - 企业环境版"
    print_blue "=========================================="
    echo ""
    echo "用法: ./start.sh [命令] [参数]"
    echo ""
    echo "首次使用命令:"
    echo "  login [url]     手动登录并保存状态（首次必须执行）"
    echo "  check           检查登录状态"
    echo ""
    echo "启动命令:"
    echo "  start           启动API服务（开发模式）"
    echo "  production      启动API服务（生产模式）"
    echo ""
    echo "工具命令:"
    echo "  test [url]      测试浏览器（可见模式）"
    echo "  analyze         分析AI工具页面结构"
    echo "  clean           清理所有浏览器数据"
    echo "  help            显示此帮助"
    echo ""
    echo "首次使用步骤:"
    echo "  1. ./start.sh login           # 打开浏览器，手动登录"
    echo "  2. ./start.sh check           # 确认登录状态"
    echo "  3. ./start.sh start           # 启动服务"
    echo ""
    echo "数据目录说明:"
    echo "  ./browser_data/   浏览器数据（包含登录状态）"
    echo "  ./auth_state/     认证状态备份"
    echo "  ./logs/           日志文件"
    echo ""
}

# 主逻辑
main() {
    case "${1:-help}" in
        login)
            check_python
            check_dependencies
            do_login "$2"
            ;;
        check)
            check_python
            check_dependencies
            check_login
            ;;
        start)
            check_python
            check_dependencies
            start_server
            ;;
        production)
            check_python
            check_dependencies
            start_production
            ;;
        test)
            check_python
            check_dependencies
            test_browser "$2"
            ;;
        analyze)
            check_python
            check_dependencies
            shift
            analyze_page "$@"
            ;;
        clean)
            clean_data
            ;;
        help|--help|-h|"")
            show_help
            ;;
        *)
            print_error "未知命令: $1"
            show_help
            exit 1
            ;;
    esac
}

main "$@"
