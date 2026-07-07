#!/bin/bash
# MaterialHub 重启脚本

set -e

# 颜色输出
BLUE='\033[0;34m'
NC='\033[0m' # No Color

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${BLUE}🔄 MaterialHub 重启服务${NC}"
echo "========================================"
echo ""

# 停止服务
"$PROJECT_ROOT/stop.sh"

echo ""
sleep 2

# 启动服务
"$PROJECT_ROOT/start.sh"
