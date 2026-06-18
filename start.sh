#!/bin/bash
# WMS RAG V2 — 本地开发环境启动/停止脚本
# 用法:
#   ./start.sh             启动前后端
#   ./start.sh stop        停止前后端
#   ./start.sh restart     重启前后端
#   ./start.sh status      查看运行状态

set -e

PID_DIR=".pids"
mkdir -p "$PID_DIR"
BACKEND_PID="$PID_DIR/backend.pid"
FRONTEND_PID="$PID_DIR/frontend.pid"

stop_services() {
    echo "=== 停止服务 ==="

    if [ -f "$BACKEND_PID" ]; then
        PID=$(cat "$BACKEND_PID")
        if kill -0 "$PID" 2>/dev/null; then
            echo "  停止后端 (PID $PID)..."
            kill "$PID" 2>/dev/null
            sleep 1
            kill -0 "$PID" 2>/dev/null && kill -9 "$PID" 2>/dev/null
            echo "  后端已停止"
        else
            echo "  后端未运行 (stale PID file)"
        fi
        rm -f "$BACKEND_PID"
    else
        echo "  后端未运行"
    fi

    if [ -f "$FRONTEND_PID" ]; then
        PID=$(cat "$FRONTEND_PID")
        if kill -0 "$PID" 2>/dev/null; then
            echo "  停止前端 (PID $PID)..."
            # Vite 会 fork 子进程，需要杀整个进程树
            kill "$PID" 2>/dev/null
            sleep 2
            kill -0 "$PID" 2>/dev/null && kill -9 "$PID" 2>/dev/null
            echo "  前端已停止"
        else
            echo "  前端未运行 (stale PID file)"
        fi
        rm -f "$FRONTEND_PID"
    else
        echo "  前端未运行"
    fi

    # 清理端口占用 (兜底)
    echo "  检查端口占用..."
    if netstat -ano 2>/dev/null | grep -q ":8812.*LISTEN"; then
        echo "  端口 8812 仍被占用，尝试释放..."
        PID=$(netstat -ano 2>/dev/null | grep ":8812.*LISTEN" | awk '{print $5}' | head -1)
        [ -n "$PID" ] && taskkill //PID "$PID" //F 2>/dev/null && echo "  端口 8812 已释放"
    fi
    if netstat -ano 2>/dev/null | grep -q ":5173.*LISTEN"; then
        echo "  端口 5173 仍被占用，尝试释放..."
        PID=$(netstat -ano 2>/dev/null | grep ":5173.*LISTEN" | awk '{print $5}' | head -1)
        [ -n "$PID" ] && taskkill //PID "$PID" //F 2>/dev/null && echo "  端口 5173 已释放"
    fi
}

start_services() {
    echo "=== 启动 WMS RAG V2 开发环境 ==="

    # 检查 Python
    PYTHON=""
    for py in python python3; do
        if command -v $py &>/dev/null; then
            $py --version &>/dev/null && PYTHON=$py && break
        fi
    done
    if [ -z "$PYTHON" ]; then
        echo "错误: 找不到可用的 Python，请先安装 Python 3.11+"
        exit 1
    fi

    # 检查 Node
    if ! command -v npm &>/dev/null; then
        echo "错误: 找不到 npm，请先安装 Node.js"
        exit 1
    fi

    # 后端
    echo ""
    echo "--- 后端 (FastAPI :8812) ---"
    cd backend
    $PYTHON -m uvicorn app.main:app --host 0.0.0.0 --port 8812 --reload &
    BACKEND_PID=$!
    cd ..
    echo $BACKEND_PID > "$BACKEND_PID"
    echo "  后端启动中 (PID $BACKEND_PID)..."

    # 等后端就绪
    echo "  等待后端就绪..."
    for i in $(seq 1 30); do
        if curl -s http://localhost:8812/health > /dev/null 2>&1; then
            echo "  后端已就绪: http://localhost:8812"
            break
        fi
        if [ $i -eq 30 ]; then
            echo "  警告: 后端 30s 未就绪，请检查日志"
        fi
        sleep 1
    done

    # 前端
    echo ""
    echo "--- 前端 (Vite :5173) ---"
    cd frontend/vue-app
    npm run dev &
    FRONTEND_PID=$!
    cd ../..
    echo $FRONTEND_PID > "$FRONTEND_PID"
    echo "  前端启动中 (PID $FRONTEND_PID)..."
    echo "  等待前端就绪..."

    for i in $(seq 1 20); do
        if curl -s http://localhost:5173 > /dev/null 2>&1; then
            echo "  前端已就绪: http://localhost:5173"
            break
        fi
        if [ $i -eq 20 ]; then
            echo "  警告: 前端 20s 未就绪，请检查日志"
        fi
        sleep 1
    done

    echo ""
    echo "=============================================="
    echo "  WMS RAG V2 开发环境已启动"
    echo "  前端: http://localhost:5173"
    echo "  后端: http://localhost:8812"
    echo "  API:  http://localhost:8812/api/v1"
    echo "=============================================="
    echo "  运行 ./start.sh stop 停止服务"
    echo "  运行 ./start.sh restart 重启服务"
}

status_services() {
    echo "=== 服务状态 ==="
    echo ""

    # 后端
    if curl -s http://localhost:8812/health > /dev/null 2>&1; then
        echo "  后端 :8812 — 运行中 ✅"
    else
        echo "  后端 :8812 — 未运行 ❌"
    fi

    # 前端
    if curl -s http://localhost:5173 > /dev/null 2>&1; then
        echo "  前端 :5173 — 运行中 ✅"
    else
        echo "  前端 :5173 — 未运行 ❌"
    fi

    echo ""
    if [ -f "$BACKEND_PID" ] || [ -f "$FRONTEND_PID" ]; then
        echo "  PID 文件:"
        [ -f "$BACKEND_PID" ] && echo "    后端: $(cat $BACKEND_PID)"
        [ -f "$FRONTEND_PID" ] && echo "    前端: $(cat $FRONTEND_PID)"
    fi
}

case "${1:-start}" in
    stop)
        stop_services
        ;;
    restart)
        stop_services
        sleep 1
        start_services
        ;;
    status)
        status_services
        ;;
    start|*)
        # 先检查是否已在运行
        if curl -s http://localhost:8812/health > /dev/null 2>&1; then
            echo "后端已在运行，如需重启请运行: ./start.sh restart"
            echo "运行 ./start.sh status 查看状态"
            exit 1
        fi
        start_services
        ;;
esac
