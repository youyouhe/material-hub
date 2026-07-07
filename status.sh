#!/bin/bash
# MaterialHub 状态检查脚本

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

echo -e "${BLUE}📊 MaterialHub 服务状态${NC}"
echo "========================================"
echo ""

# 检查Backend
echo -e "${BLUE}Backend服务:${NC}"
BACKEND_STATUS="${RED}✗ 未运行${NC}"
BACKEND_PID=""
BACKEND_PORT=""

if [ -f "$BACKEND_PID_FILE" ]; then
    BACKEND_PID=$(cat "$BACKEND_PID_FILE")
    if ps -p $BACKEND_PID > /dev/null 2>&1; then
        BACKEND_STATUS="${GREEN}✓ 运行中${NC}"
        BACKEND_PORT=$(lsof -ti:8201 2>/dev/null || netstat -tlnp 2>/dev/null | grep ":8201" | grep "$BACKEND_PID" || echo "")
        if [ ! -z "$BACKEND_PORT" ]; then
            BACKEND_STATUS="${GREEN}✓ 运行中 (端口: 8201)${NC}"
        fi
    else
        BACKEND_STATUS="${YELLOW}⚠ PID文件存在但进程不存在${NC}"
    fi
fi

echo -e "  状态: $BACKEND_STATUS"
if [ ! -z "$BACKEND_PID" ]; then
    echo -e "  PID: $BACKEND_PID"
fi

# 测试Backend健康检查
if curl -s http://localhost:8201/health > /dev/null 2>&1; then
    HEALTH=$(curl -s http://localhost:8201/health)
    echo -e "  健康检查: ${GREEN}✓ 正常${NC}"
    echo -e "  响应: $HEALTH"
else
    echo -e "  健康检查: ${RED}✗ 无响应${NC}"
fi

echo ""

# 检查Frontend
echo -e "${BLUE}Frontend服务:${NC}"
FRONTEND_STATUS="${RED}✗ 未运行${NC}"
FRONTEND_PID=""
FRONTEND_PORT=""

if [ -f "$FRONTEND_PID_FILE" ]; then
    FRONTEND_PID=$(cat "$FRONTEND_PID_FILE")
    if ps -p $FRONTEND_PID > /dev/null 2>&1; then
        FRONTEND_STATUS="${GREEN}✓ 运行中${NC}"
        # 尝试从日志中获取端口
        if [ -f "$PROJECT_ROOT/frontend.log" ]; then
            FRONTEND_PORT=$(grep -oP "(?<=Local:   http://localhost:)\d+" "$PROJECT_ROOT/frontend.log" | tail -1)
            if [ ! -z "$FRONTEND_PORT" ]; then
                FRONTEND_STATUS="${GREEN}✓ 运行中 (端口: $FRONTEND_PORT)${NC}"
            fi
        fi
    else
        FRONTEND_STATUS="${YELLOW}⚠ PID文件存在但进程不存在${NC}"
    fi
fi

echo -e "  状态: $FRONTEND_STATUS"
if [ ! -z "$FRONTEND_PID" ]; then
    echo -e "  PID: $FRONTEND_PID"
fi

if [ ! -z "$FRONTEND_PORT" ]; then
    LOCAL_IP=$(hostname -I | awk '{print $1}')
    echo -e "  访问地址:"
    echo -e "    ${GREEN}→${NC} http://localhost:$FRONTEND_PORT"
    if [ ! -z "$LOCAL_IP" ]; then
        echo -e "    ${GREEN}→${NC} http://$LOCAL_IP:$FRONTEND_PORT"
    fi
fi

echo ""

# 检查数据库
echo -e "${BLUE}数据库:${NC}"
DB_PATH="$PROJECT_ROOT/backend/data/materials.db"
if [ -f "$DB_PATH" ]; then
    DB_SIZE=$(du -h "$DB_PATH" | cut -f1)
    echo -e "  状态: ${GREEN}✓ 存在${NC}"
    echo -e "  路径: $DB_PATH"
    echo -e "  大小: $DB_SIZE"

    # 统计数据（需要sqlite3）
    if command -v sqlite3 > /dev/null 2>&1; then
        COMPANY_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM companies;" 2>/dev/null || echo "?")
        PERSON_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM persons;" 2>/dev/null || echo "?")
        MATERIAL_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM materials;" 2>/dev/null || echo "?")
        echo -e "  数据统计:"
        echo -e "    - 公司: $COMPANY_COUNT"
        echo -e "    - 人员: $PERSON_COUNT"
        echo -e "    - 材料: $MATERIAL_COUNT"
    fi
else
    echo -e "  状态: ${YELLOW}⚠ 不存在${NC}"
fi

echo ""

# 端口占用情况
echo -e "${BLUE}端口占用:${NC}"
PORT_8201=$(lsof -ti:8201 2>/dev/null || echo "")
PORT_3100=$(lsof -ti:3100 2>/dev/null || echo "")
PORT_3001=$(lsof -ti:3001 2>/dev/null || echo "")
PORT_3002=$(lsof -ti:3002 2>/dev/null || echo "")

[ ! -z "$PORT_8201" ] && echo -e "  ${YELLOW}→${NC} 8201: 占用 (PID: $PORT_8201)" || echo -e "  ${GREEN}→${NC} 8201: 空闲"
[ ! -z "$PORT_3100" ] && echo -e "  ${YELLOW}→${NC} 3100: 占用 (PID: $PORT_3100)" || echo -e "  ${GREEN}→${NC} 3100: 空闲"
[ ! -z "$PORT_3001" ] && echo -e "  ${YELLOW}→${NC} 3001: 占用 (PID: $PORT_3001)" || echo -e "  ${GREEN}→${NC} 3001: 空闲"
[ ! -z "$PORT_3002" ] && echo -e "  ${YELLOW}→${NC} 3002: 占用 (PID: $PORT_3002)" || echo -e "  ${GREEN}→${NC} 3002: 空闲"

echo ""
echo -e "${GREEN}========================================${NC}"
