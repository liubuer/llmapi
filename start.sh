#!/bin/bash

# 内部AI工具API启动脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_blue() {
    echo -e "${BLUE}$1${NC}"
}

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
    
    # 检查虚拟环境
    if [ ! -d "venv" ]; then
        print_warn "虚拟环境不存在，正在创建..."
        python3 -m venv venv
    fi
    
    # 激活虚拟环境
    source venv/bin/activate
    
    # 安装依赖
    pip install -q -r requirements.txt
    
    # 安装Playwright浏览器
    if [ ! -d "$HOME/.cache/ms-playwright" ]; then
        print_info "安装Playwright浏览器..."
        playwright install chromium
    fi
}

# 检查认证状态
check_auth() {
    if [ ! -f "auth_state/state.json" ]; then
        print_warn "未找到认证状态文件"
        print_info "请先运行以下命令之一："
        print_info "  ./start.sh import-edge  # 从Edge导入（推荐）"
        print_info "  ./start.sh login        # 手动登录"
        return 1
    fi
    return 0
}

# 从Edge导入登录状态
import_edge() {
    print_info "启动Edge登录状态导入工具..."
    source venv/bin/activate
    python tools/import_edge_session.py
}

# 检查Edge配置
check_edge() {
    print_info "检查Edge浏览器配置..."
    source venv/bin/activate
    python -m app.browser_manager --check-edge
}

# 手动登录
do_login() {
    print_info "启动手动登录流程..."
    source venv/bin/activate
    python -m app.browser_manager --login
}

# 启动服务（使用Edge配置文件模式）
start_with_edge() {
    print_info "启动API服务（Edge配置文件模式）..."
    print_warn "请确保已关闭所有Edge浏览器窗口！"
    source venv/bin/activate
    
    mkdir -p logs
    
    # 设置环境变量启用Edge模式
    export USE_EDGE_PROFILE=true
    export EDGE_PROFILE="${1:-Default}"
    
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
}

# 启动服务
start_server() {
    print_info "启动API服务..."
    source venv/bin/activate
    
    # 创建日志目录
    mkdir -p logs
    
    # 启动服务
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
}

# 启动服务（生产模式）
start_production() {
    print_info "启动API服务（生产模式）..."
    source venv/bin/activate
    
    mkdir -p logs
    
    # 使用多个worker
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
}

# 分析页面
analyze() {
    print_info "启动页面分析工具..."
    source venv/bin/activate
    python tools/analyze_page.py "$@"
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
    print_blue "    内部AI工具 API 启动脚本"
    print_blue "=========================================="
    echo ""
    echo "用法: ./start.sh [命令]"
    echo ""
    echo "登录命令:"
    echo "  import-edge   - 从Edge浏览器导入登录状态（推荐）"
    echo "  check-edge    - 检查Edge浏览器配置"
    echo "  login         - 手动登录并保存认证状态"
    echo ""
    echo "启动命令:"
    echo "  start         - 启动API服务（开发模式，使用保存的状态）"
    echo "  start-edge    - 启动API服务（直接使用Edge登录状态）"
    echo "  production    - 启动API服务（生产模式）"
    echo ""
    echo "工具命令:"
    echo "  analyze       - 分析AI工具页面结构"
    echo "  test          - 运行测试"
    echo "  help          - 显示此帮助信息"
    echo ""
    echo "首次使用步骤（推荐）:"
    echo "  1. ./start.sh import-edge   # 从Edge导入登录状态"
    echo "  2. ./start.sh start         # 启动服务"
    echo ""
    echo "或者使用Edge配置文件模式（无需导入）:"
    echo "  1. 关闭所有Edge窗口"
    echo "  2. ./start.sh start-edge    # 直接使用Edge登录状态启动"
    echo ""
}

# 主逻辑
main() {
    check_python
    check_dependencies
    
    case "${1:-help}" in
        import-edge|import)
            import_edge
            ;;
        check-edge)
            check_edge
            ;;
        login)
            do_login
            ;;
        start)
            if check_auth; then
                start_server
            fi
            ;;
        start-edge)
            shift
            start_with_edge "$@"
            ;;
        production)
            if check_auth; then
                start_production
            fi
            ;;
        analyze)
            shift
            analyze "$@"
            ;;
        test)
            run_tests
            ;;
        help|--help|-h)
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
