#!/usr/bin/env bash
#
# MaterialHub 回滚脚本（服务器端）
#
# 用法:
#   ./rollback.sh            # 回滚到上一个部署版本
#   ./rollback.sh abc1234    # 回滚到指定 commit
#   ./rollback.sh --list     # 列出部署历史
#
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()   { echo -e "${BLUE}==>${NC} $*"; }
ok()    { echo -e "${GREEN}✓${NC} $*"; }
warn()  { echo -e "${YELLOW}[警告]${NC} $*" >&2; }
die()   { echo -e "${RED}[错误]${NC} $*" >&2; exit 1; }

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_LOG="$PROJECT_ROOT/.deploy-history.log"
cd "$PROJECT_ROOT"

# ===== 列出历史 =====
if [[ "${1:-}" == "--list" ]]; then
    echo "部署历史（新 → 旧）:"
    echo "──────────────────────────────────────────"
    if [ -f "$DEPLOY_LOG" ]; then
        tac "$DEPLOY_LOG" | head -20 | while read -r date commit; do
            msg=$(git log --oneline -1 "$commit" 2>/dev/null | head -c 80 || echo "(不在当前历史中)")
            if [ "$commit" == "$(git rev-parse HEAD)" ]; then
                echo -e "  ${GREEN}▶${NC} $date  $commit  $msg"
            else
                echo "    $date  $commit  $msg"
            fi
        done
    else
        echo "  (无部署历史)"
    fi
    exit 0
fi

# ===== 确定回滚目标 =====
if [ -z "${1:-}" ]; then
    # 默认：回滚到上一个部署版本
    if [ ! -f "$DEPLOY_LOG" ]; then
        die "无部署历史，无法自动确定回滚目标。\n  手动指定: ./rollback.sh <commit>\n  查看历史: ./rollback.sh --list"
    fi
    CURRENT=$(git rev-parse HEAD)
    # 从历史中找到当前 commit 的上一条
    TARGET=""
    PREV=""
    while read -r _ commit; do
        if [ "$commit" = "$CURRENT" ] && [ -n "$PREV" ]; then
            TARGET="$PREV"
            break
        fi
        PREV="$commit"
    done < "$DEPLOY_LOG"
    if [ -z "$TARGET" ]; then
        die "无法找到上一个部署版本。\n  手动指定: ./rollback.sh <commit>\n  查看历史: ./rollback.sh --list"
    fi
else
    TARGET="$1"
fi

# ===== 验证目标 =====
if ! git cat-file -e "$TARGET" 2>/dev/null; then
    die "commit $TARGET 在仓库中不存在"
fi

CURRENT=$(git rev-parse --short HEAD)
TARGET_SHORT=$(git rev-parse --short "$TARGET")

echo ""
echo -e "${YELLOW}╔════════════════════════════════════════════╗${NC}"
echo -e "${YELLOW}║         MaterialHub 回滚                    ║${NC}"
echo -e "${YELLOW}╚════════════════════════════════════════════╝${NC}"
echo ""
echo "  当前: $CURRENT"
echo "  目标: $TARGET_SHORT"
echo ""
git log --oneline "${CURRENT}..${TARGET}" 2>/dev/null | sed 's/^/  回退: /'
echo ""

read -rp "确认回滚? (y/N) " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "已取消"
    exit 0
fi

# ===== 执行回滚 =====
log "切换到 $TARGET_SHORT..."
git reset --hard "$TARGET"
ok "已切换到 $(git rev-parse --short HEAD)"

log "重建并启动..."
docker compose up -d --build

log "等待 Backend 就绪..."
BACKEND_PORT="${BACKEND_PORT:-8101}"
for i in $(seq 1 20); do
    if curl -sf "http://127.0.0.1:$BACKEND_PORT/health" > /dev/null 2>&1; then
        ok "Backend healthy"
        break
    fi
    [ "$i" -eq 20 ] && warn "健康检查超时"
    sleep 1
done

# 记录回滚
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $(git rev-parse HEAD) [rollback]" >> "$DEPLOY_LOG"

echo ""
echo -e "${GREEN}  回滚完成 → $(git rev-parse --short HEAD)${NC}"
