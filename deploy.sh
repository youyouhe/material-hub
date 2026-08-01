#!/usr/bin/env bash
#
# MaterialHub 部署脚本（服务器端，Docker Compose 模式）
#
# 用法:
#   ./deploy.sh              # 拉取最新 main 并部署
#   ./deploy.sh --check      # 只拉取预览变更，不实际部署
#
# 前置条件:
#   - Docker + Docker Compose 已安装
#   - 当前目录为 material-hub 仓库根目录
#   - .env 文件已配置
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

CHECK_ONLY=false
if [[ "${1:-}" == "--check" ]]; then
    CHECK_ONLY=true
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_LOG="$PROJECT_ROOT/.deploy-history.log"

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     MaterialHub 部署 (Docker Compose)      ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════╝${NC}"
echo ""

# ===== 1. 检查前置条件 =====
log "检查环境..."
command -v docker >/dev/null 2>&1 || die "Docker 未安装"
docker compose version >/dev/null 2>&1 || die "docker compose 不可用"
cd "$PROJECT_ROOT"
if [ ! -f ".env" ]; then
    die ".env 文件不存在，请先配置"
fi
ok "环境就绪"

# ===== 2. 记录当前版本 =====
OLD_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
log "当前版本: $OLD_COMMIT"

# ===== 3. 拉取最新代码 =====
log "拉取最新代码..."
git fetch origin main
NEW_COMMIT=$(git rev-parse --short origin/main)

if [ "$OLD_COMMIT" == "$NEW_COMMIT" ] && [ "$CHECK_ONLY" = false ]; then
    ok "已是最新版本 ($NEW_COMMIT)，无需部署"
    exit 0
fi

# 显示变更
echo ""
echo "  变更范围: $OLD_COMMIT → $NEW_COMMIT"
git log --oneline "$OLD_COMMIT..$NEW_COMMIT" 2>/dev/null || echo "  (新仓库，首次部署)"
echo ""

if $CHECK_ONLY; then
    ok "检查完成（--check 模式，未实际部署）"
    exit 0
fi

# ===== 4. 合并代码 =====
log "合并代码..."
git merge --ff-only origin/main
ok "已更新到 $(git rev-parse --short HEAD)"

# ===== 5. 构建 + 启动 =====
log "构建镜像并重启服务..."
docker compose up -d --build
ok "容器已启动"

# ===== 6. 健康检查 =====
log "等待 Backend 就绪..."
BACKEND_PORT="${BACKEND_PORT:-8101}"
for i in $(seq 1 20); do
    if curl -sf "http://127.0.0.1:$BACKEND_PORT/health" > /dev/null 2>&1; then
        ok "Backend healthy (${i}s)"
        break
    fi
    if [ "$i" -eq 20 ]; then
        warn "Backend 健康检查超时，请检查日志"
        echo "---- 最近后端日志 ----"
        docker compose logs --tail=30 backend 2>/dev/null || true
    fi
    sleep 1
done

# ===== 7. 记录部署历史 =====
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $(git rev-parse HEAD)" >> "$DEPLOY_LOG"
# 保留最近 20 条
tail -20 "$DEPLOY_LOG" > "$DEPLOY_LOG.tmp" && mv "$DEPLOY_LOG.tmp" "$DEPLOY_LOG"

# ===== 8. 汇总 =====
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  部署完成${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "  版本: $(git rev-parse --short HEAD)"
echo "  容器:"
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""
echo "  回滚: ./rollback.sh"
echo "  历史: tail -5 $DEPLOY_LOG"
