#!/bin/bash
# MaterialHub 清理 mock 测试文档脚本（不影响真实业务数据）
#
# 自动检测运行方式：
#   - 若检测到容器 material-hub-backend-1 在跑，走 docker exec（Docker Compose 部署）
#   - 否则假定裸机部署，直接用本机 python3 跑（backend/venv 或系统 python）
#
# 用法:
#   ./clean_mock_docs.sh          # 预览将删除的文档（不执行）
#   ./clean_mock_docs.sh --apply  # 先自动备份，再实际删除

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
CONTAINER_NAME="${CONTAINER_NAME:-material-hub-backend-1}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo -e "${BLUE}======================================"
echo -e "MaterialHub Mock 文档清理工具"
echo -e "======================================${NC}"
echo ""

USE_DOCKER=false
if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$CONTAINER_NAME"; then
    USE_DOCKER=true
    echo -e "${BLUE}ℹ️  检测到容器 ${CONTAINER_NAME} 正在运行，将通过 docker exec 在容器内执行${NC}"
else
    echo -e "${BLUE}ℹ️  未检测到 Docker 容器，按裸机部署方式直接执行${NC}"
fi
echo ""

run_clean() {
    if $USE_DOCKER; then
        docker exec "$CONTAINER_NAME" python3 scripts/clean_mock_docs.py "$@"
    else
        (cd "$BACKEND_DIR" && "$PYTHON_BIN" scripts/clean_mock_docs.py "$@")
    fi
}

if [ "$1" != "--apply" ]; then
    echo -e "${YELLOW}预览模式（不会删除任何数据）：${NC}"
    echo ""
    run_clean
    echo ""
    echo -e "${BLUE}💡 确认无误后运行: $0 --apply${NC}"
    exit 0
fi

echo -e "${YELLOW}⚠️  即将删除所有 mock 生成的文档（不影响真实业务数据）${NC}"
read -p "确认继续？(yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo -e "${YELLOW}已取消${NC}"
    exit 0
fi

echo ""
echo -e "${BLUE}→${NC} 清理前先做一次安全备份..."
if $USE_DOCKER; then
    mkdir -p "$PROJECT_ROOT/backups"
    TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
    SAFETY_DB="$PROJECT_ROOT/backups/materials_${TIMESTAMP}_before_clean_mock.db"
    docker cp "$CONTAINER_NAME:/app/data/materials.db" "$SAFETY_DB"
    echo -e "${GREEN}✓${NC} 已备份数据库到: $SAFETY_DB"
else
    "$PROJECT_ROOT/backup.sh"
fi

echo ""
echo -e "${BLUE}→${NC} 执行清理..."
run_clean --apply

echo ""
echo -e "${GREEN}✅ 清理完成${NC}"
if $USE_DOCKER; then
    echo -e "${BLUE}💡 若需要撤销，可用 docker cp \"$SAFETY_DB\" $CONTAINER_NAME:/app/data/materials.db 后重启容器${NC}"
else
    echo -e "${BLUE}💡 若需要撤销，可用 ./restore.sh 恢复到清理前的备份${NC}"
fi
