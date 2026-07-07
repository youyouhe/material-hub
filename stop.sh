#!/bin/bash
# MaterialHub 宿主机停止脚本

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# PID文件
BACKEND_PID_FILE="$PROJECT_ROOT/.backend.pid"
FRONTEND_PID_FILE="$PROJECT_ROOT/.frontend.pid"

echo -e "${BLUE}🛑 MaterialHub 停止服务${NC}"
echo "========================================"

# 停止Backend
if [ -f "$BACKEND_PID_FILE" ]; then
    BACKEND_PID=$(cat "$BACKEND_PID_FILE")
    if ps -p $BACKEND_PID > /dev/null 2>&1; then
        echo -e "${YELLOW}→${NC} 停止Backend (PID: $BACKEND_PID)..."
        kill $BACKEND_PID 2>/dev/null || true
        # 等待进程结束
        for i in {1..5}; do
            if ! ps -p $BACKEND_PID > /dev/null 2>&1; then
                break
            fi
            sleep 1
        done
        # 强制杀死
        if ps -p $BACKEND_PID > /dev/null 2>&1; then
            kill -9 $BACKEND_PID 2>/dev/null || true
        fi
        echo -e "${GREEN}✓${NC} Backend已停止"
    else
        echo -e "${YELLOW}⚠${NC} Backend进程不存在"
    fi
    rm -f "$BACKEND_PID_FILE"
else
    echo -e "${YELLOW}⚠${NC} 未找到Backend PID文件"
fi

# 停止Frontend
if [ -f "$FRONTEND_PID_FILE" ]; then
    FRONTEND_PID=$(cat "$FRONTEND_PID_FILE")
    if ps -p $FRONTEND_PID > /dev/null 2>&1; then
        echo -e "${YELLOW}→${NC} 停止Frontend (PID: $FRONTEND_PID)..."
        kill $FRONTEND_PID 2>/dev/null || true
        # 等待进程结束
        for i in {1..5}; do
            if ! ps -p $FRONTEND_PID > /dev/null 2>&1; then
                break
            fi
            sleep 1
        done
        # 强制杀死
        if ps -p $FRONTEND_PID > /dev/null 2>&1; then
            kill -9 $FRONTEND_PID 2>/dev/null || true
        fi
        echo -e "${GREEN}✓${NC} Frontend已停止"
    else
        echo -e "${YELLOW}⚠${NC} Frontend进程不存在"
    fi
    rm -f "$FRONTEND_PID_FILE"
else
    echo -e "${YELLOW}⚠${NC} 未找到Frontend PID文件"
fi

# 额外清理：按端口杀死残留进程（最可靠）
echo ""
echo -e "${BLUE}清理残留进程...${NC}"

# 清理占用Backend端口(8201)的进程
BACKEND_PORT_PID=$(lsof -ti :8201 2>/dev/null || true)
if [ ! -z "$BACKEND_PORT_PID" ]; then
    echo -e "${YELLOW}→${NC} 发现占用端口8201的进程: $BACKEND_PORT_PID"
    echo $BACKEND_PORT_PID | xargs kill 2>/dev/null || true
    sleep 1
    # 如果还活着，强杀
    BACKEND_PORT_PID=$(lsof -ti :8201 2>/dev/null || true)
    if [ ! -z "$BACKEND_PORT_PID" ]; then
        echo $BACKEND_PORT_PID | xargs kill -9 2>/dev/null || true
    fi
    echo -e "${GREEN}✓${NC} 已清理"
fi

# 清理占用Frontend端口(3100)的进程
FRONTEND_PORT_PID=$(lsof -ti :3100 2>/dev/null || true)
if [ ! -z "$FRONTEND_PORT_PID" ]; then
    echo -e "${YELLOW}→${NC} 发现占用端口3100的进程: $FRONTEND_PORT_PID"
    echo $FRONTEND_PORT_PID | xargs kill 2>/dev/null || true
    sleep 1
    FRONTEND_PORT_PID=$(lsof -ti :3100 2>/dev/null || true)
    if [ ! -z "$FRONTEND_PORT_PID" ]; then
        echo $FRONTEND_PORT_PID | xargs kill -9 2>/dev/null || true
    fi
    echo -e "${GREEN}✓${NC} 已清理"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✓ MaterialHub 已停止${NC}"
echo -e "${GREEN}========================================${NC}"
