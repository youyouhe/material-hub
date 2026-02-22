#!/bin/bash
# MaterialHub 宿主机启动脚本

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

# PID文件
BACKEND_PID_FILE="$PROJECT_ROOT/.backend.pid"
FRONTEND_PID_FILE="$PROJECT_ROOT/.frontend.pid"

echo -e "${BLUE}🚀 MaterialHub 宿主机启动${NC}"
echo "========================================"

# 检查并创建数据目录
mkdir -p "$BACKEND_DIR/data/uploads"
mkdir -p "$BACKEND_DIR/data/images"
echo -e "${GREEN}✓${NC} 数据目录已准备"

# 启动Backend
echo ""
echo -e "${BLUE}📦 启动Backend服务...${NC}"
cd "$BACKEND_DIR"

# 检查venv
if [ ! -d "venv" ]; then
    echo -e "${RED}✗ 虚拟环境不存在，正在创建...${NC}"
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# 启动backend (设置OCR服务地址为localhost)
# 使用 setsid 确保进程完全脱离终端会话
export OCR_SERVICE_URL=http://localhost:8010
setsid python main.py > "$PROJECT_ROOT/backend.log" 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID > "$BACKEND_PID_FILE"
echo -e "${GREEN}✓${NC} Backend已启动 (PID: $BACKEND_PID)"
echo -e "  ${YELLOW}→${NC} 端口: 8201"
echo -e "  ${YELLOW}→${NC} 日志: $PROJECT_ROOT/backend.log"
echo -e "  ${YELLOW}→${NC} 提示: 进程已完全脱离终端，关闭终端不会影响服务"

# 等待backend启动
echo -n "  等待Backend就绪"
for i in {1..10}; do
    if curl -s http://localhost:8201/health > /dev/null 2>&1; then
        echo -e " ${GREEN}✓${NC}"
        break
    fi
    echo -n "."
    sleep 1
done

# 启动Frontend
echo ""
echo -e "${BLUE}🎨 启动Frontend服务...${NC}"
cd "$FRONTEND_DIR"

# 检查node_modules
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}⚠${NC} 依赖未安装，正在安装..."
    npm install
fi

# 启动frontend
# 使用 setsid 确保进程完全脱离终端会话
setsid npm run dev > "$PROJECT_ROOT/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo $FRONTEND_PID > "$FRONTEND_PID_FILE"
echo -e "${GREEN}✓${NC} Frontend已启动 (PID: $FRONTEND_PID)"
echo -e "  ${YELLOW}→${NC} 端口: 3100 (如被占用会自动选择其他端口)"
echo -e "  ${YELLOW}→${NC} 日志: $PROJECT_ROOT/frontend.log"

# 等待frontend启动并获取实际端口
echo -n "  等待Frontend就绪"
ACTUAL_PORT=""
for i in {1..15}; do
    if [ -f "$PROJECT_ROOT/frontend.log" ]; then
        ACTUAL_PORT=$(grep -oP "(?<=Local:   http://localhost:)\d+" "$PROJECT_ROOT/frontend.log" | tail -1)
        if [ ! -z "$ACTUAL_PORT" ]; then
            echo -e " ${GREEN}✓${NC}"
            break
        fi
    fi
    echo -n "."
    sleep 1
done

# 显示访问信息
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}🎉 MaterialHub 启动成功！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}访问地址:${NC}"
if [ ! -z "$ACTUAL_PORT" ]; then
    echo -e "  ${GREEN}→${NC} http://localhost:$ACTUAL_PORT"
    # 获取本机IP
    LOCAL_IP=$(hostname -I | awk '{print $1}')
    if [ ! -z "$LOCAL_IP" ]; then
        echo -e "  ${GREEN}→${NC} http://$LOCAL_IP:$ACTUAL_PORT"
    fi
else
    echo -e "  ${GREEN}→${NC} 请查看日志获取端口: tail -f frontend.log"
fi
echo ""
echo -e "${BLUE}管理命令:${NC}"
echo -e "  ${YELLOW}→${NC} 停止服务: ./stop.sh"
echo -e "  ${YELLOW}→${NC} 查看状态: ./status.sh"
echo -e "  ${YELLOW}→${NC} 查看日志: tail -f backend.log frontend.log"
echo ""
echo -e "${GREEN}========================================${NC}"
