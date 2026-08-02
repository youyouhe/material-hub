#!/bin/bash
# MaterialHub 清理 mock 测试文档脚本（不影响真实业务数据）
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
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo -e "${BLUE}======================================"
echo -e "MaterialHub Mock 文档清理工具"
echo -e "======================================${NC}"
echo ""

if [ "$1" != "--apply" ]; then
    echo -e "${YELLOW}预览模式（不会删除任何数据）：${NC}"
    echo ""
    cd "$BACKEND_DIR" && "$PYTHON_BIN" scripts/clean_mock_docs.py
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
"$PROJECT_ROOT/backup.sh"

echo ""
echo -e "${BLUE}→${NC} 执行清理..."
cd "$BACKEND_DIR" && "$PYTHON_BIN" scripts/clean_mock_docs.py --apply

echo ""
echo -e "${GREEN}✅ 清理完成${NC}"
echo -e "${BLUE}💡 若需要撤销，可用 ./restore.sh 恢复到清理前的备份${NC}"
