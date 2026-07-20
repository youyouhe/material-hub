#!/usr/bin/env bash
#
# MaterialHub 一键部署脚本(Docker Compose 模式)
#
# 适用场景:
#   1) 新服务器首次部署:从 GitHub 拉取源码 → 生成 .env → 构建并启动容器
#   2) 已有部署的更新:拉取最新代码 → 重新构建并启动
#
# 用法:
#   新服务器首次(从 GitHub 引导,无需先 clone):
#     curl -fsSL https://raw.githubusercontent.com/youyouhe/material-hub/main/deploy.sh | bash
#
#   仓库内更新:
#     ./deploy.sh
#
#   锁定到指定版本(可复现部署):
#     COMMIT=b195988ca88789fabfa4c074317bda6ef48c4d1a ./deploy.sh
#
#   自定义仓库 / 分支:
#     REPO_URL=... BRANCH=main ./deploy.sh
#
# 注意:本脚本默认使用 Docker Compose 部署。
#       OCR 服务(PaddleOCR 等)需在宿主机单独运行于 8010 端口,详见末尾提示。

set -euo pipefail

# ===== 可配置参数(均可通过环境变量覆盖)=====
REPO_URL="${REPO_URL:-https://github.com/youyouhe/material-hub.git}"
BRANCH="${BRANCH:-main}"
COMMIT="${COMMIT:-}"                       # 留空=跟随分支最新;填 hash=锁定版本
INSTALL_DIR="${INSTALL_DIR:-material-hub}"
BACKEND_PORT="${BACKEND_PORT:-8101}"
FRONTEND_PORT="${FRONTEND_PORT:-3101}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-120}"    # 后端健康检查最长等待秒数

# ===== 颜色输出(与项目其他脚本风格一致)=====
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

APP_DIR=""
COMPOSE_CMD=""

log()   { echo -e "${BLUE}==>${NC} $*"; }
ok()    { echo -e "${GREEN}✓${NC} $*"; }
warn()  { echo -e "${YELLOW}[警告]${NC} $*" >&2; }
die()   { echo -e "${RED}[错误]${NC} $*" >&2; exit 1; }

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║       MaterialHub 部署脚本 (Docker)        ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════╝${NC}"
echo ""

# ============================================================
# 1. 检测 docker compose 命令(v2 插件优先)
# ============================================================
detect_compose() {
    if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
        echo "docker compose"
    elif command -v docker-compose >/dev/null 2>&1; then
        echo "docker-compose"
    else
        echo ""
    fi
}

# ============================================================
# 2. 依赖检查
# ============================================================
ensure_tools() {
    log "[1/6] 检查依赖..."
    local missing=()
    command -v git    >/dev/null 2>&1 || missing+=(git)
    command -v docker >/dev/null 2>&1 || missing+=(docker)
    command -v curl   >/dev/null 2>&1 || missing+=(curl)
    if [ ${#missing[@]} -gt 0 ]; then
        die "缺少依赖: ${missing[*]}。请先安装后再运行本脚本。"
    fi

    COMPOSE_CMD="$(detect_compose)"
    [ -n "$COMPOSE_CMD" ] || die "未检测到 docker compose,请安装 Docker Compose v2 或 docker-compose。"

    docker info >/dev/null 2>&1 || die "docker 守护进程未运行,请先启动 docker (systemctl start docker)。"
    ok "依赖检查通过 ($COMPOSE_CMD)"
}

# ============================================================
# 3. 拉取 / 更新源码
#    - 若当前已在仓库内(检测到 docker-compose.yml 的 git 工作树):就地更新
#    - 否则:克隆到 ./INSTALL_DIR
# ============================================================
fetch_source() {
    log "[2/6] 获取源码..."

    local toplevel=""
    toplevel="$(git rev-parse --show-toplevel 2>/dev/null || true)"

    if [ -n "$toplevel" ] && [ -f "$toplevel/docker-compose.yml" ]; then
        # 仓库内执行:就地更新
        APP_DIR="$toplevel"
        log "仓库内更新: $APP_DIR"
        # 确保 origin 指向目标仓库
        if [ "$(git remote get-url origin 2>/dev/null || true)" != "$REPO_URL" ]; then
            git remote set-url origin "$REPO_URL" 2>/dev/null || git remote add origin "$REPO_URL"
        fi
        git fetch --force origin "$BRANCH"
        git checkout "$BRANCH"
        git reset --hard "${COMMIT:-origin/$BRANCH}"
    else
        # 全新部署:克隆
        APP_DIR="$(pwd)/$INSTALL_DIR"
        if [ -d "$APP_DIR/.git" ]; then
            log "目录已存在,增量更新: $APP_DIR"
            git -C "$APP_DIR" fetch --force origin "$BRANCH"
            git -C "$APP_DIR" checkout "$BRANCH"
            git -C "$APP_DIR" reset --hard "${COMMIT:-origin/$BRANCH}"
        else
            log "全新部署,克隆仓库到: $APP_DIR"
            git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
            [ -n "$COMMIT" ] && git -C "$APP_DIR" reset --hard "$COMMIT"
        fi
    fi

    cd "$APP_DIR"
    ok "代码就绪: $(git log -1 --format='%h %s')"
}

# ============================================================
# 4. 配置 .env
# ============================================================
ensure_env() {
    log "[3/6] 配置 .env..."
    [ -f .env.example ] || die "缺少 .env.example,仓库可能不完整。"

    if [ ! -f .env ]; then
        log "首次部署,从 .env.example 创建 .env"
        cp .env.example .env
        warn ".env 已生成(默认值),关键项需按需修改 —— 见末尾提示。"
    else
        ok ".env 已存在,保留现有配置"
    fi
}

# ============================================================
# 5. .env 关键项检查(尽力而为,不阻断启动)
# ============================================================
check_env() {
    log "[4/6] 检查 .env 关键项..."
    local hit=0

    # DEEPSEEK_API_KEY 占位符或空值
    if grep -qE '^DEEPSEEK_API_KEY=(your-|sk-xxx|xxx|<)' .env 2>/dev/null \
       || grep -qx 'DEEPSEEK_API_KEY=' .env 2>/dev/null; then
        warn "DEEPSEEK_API_KEY 未填写真实值,LLM 智能提取将不可用"
        hit=1
    fi

    # EMBEDDING_API_KEY 被注释或缺失(DeepSeek 不提供 embedding,需独立端点)
    if ! grep -qE '^[[:space:]]*EMBEDDING_API_KEY=.+' .env 2>/dev/null; then
        warn "EMBEDDING_API_KEY 未配置,知识库 / 向量检索将不可用"
        hit=1
    fi

    # OCR_SERVICE_URL 指向 localhost —— Docker 容器内无法访问宿主机
    if grep -qE '^OCR_SERVICE_URL=.*(localhost|127\.0\.0\.1)' .env 2>/dev/null; then
        warn "OCR_SERVICE_URL 指向 localhost,容器内无法访问宿主机 —— Docker 模式应改为 http://host.docker.internal:8010"
        hit=1
    fi

    if [ "$hit" -eq 0 ]; then
        ok ".env 关键项检查通过"
    else
        warn "以上项可先启动,稍后在 .env 补全后重跑 ./deploy.sh 即可生效"
    fi
}

# ============================================================
# 6. 构建 + 启动
# ============================================================
build_and_up() {
    log "[5/6] 构建并启动容器(首次较慢,需拉取镜像 + 构建)..."
    $COMPOSE_CMD up -d --build
    ok "容器已启动"
}

# ============================================================
# 7. 健康检查(尽力而为,不阻断)
# ============================================================
wait_health() {
    log "[6/6] 等待后端就绪(最长 ${HEALTH_TIMEOUT}s)..."
    local i=0
    while [ "$i" -lt "$HEALTH_TIMEOUT" ]; do
        if curl -fsSL "http://localhost:${BACKEND_PORT}/docs" >/dev/null 2>&1; then
            ok "后端已就绪(耗时约 ${i}s)"
            return 0
        fi
        sleep 2
        i=$((i + 2))
    done
    warn "后端在 ${HEALTH_TIMEOUT}s 内未响应 —— 通常是 OCR/embedding 配置缺失或初始化较慢"
    warn "请查看日志: $COMPOSE_CMD logs -f backend"
}

# ============================================================
# 8. 汇总输出
# ============================================================
print_summary() {
    local ip=""
    ip="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
    [ -z "$ip" ] && ip="<服务器IP>"

    cat <<EOF

${GREEN}╔════════════════════════════════════════════╗${NC}
${GREEN}║            ✅  部署完成                    ║${NC}
${GREEN}╚════════════════════════════════════════════╝${NC}

  仓库版本 : $(git log -1 --format='%h %s')

  访问地址 :
     前端   : http://${ip}:${FRONTEND_PORT}
     后端   : http://${ip}:${BACKEND_PORT}/docs
     默认账号 : admin / admin123

  常用命令(在 ${APP_DIR} 下执行):
     查看日志 : ${COMPOSE_CMD} logs -f
     重启服务 : ${COMPOSE_CMD} restart
     停止服务 : ${COMPOSE_CMD} down
     更新部署 : ./deploy.sh

${YELLOW}部署后请务必确认:${NC}
   1. OCR 服务已在宿主机 8010 端口运行,且 .env 的 OCR_SERVICE_URL
      在 Docker 模式下应为 http://host.docker.internal:8010
   2. .env 中 LLM 密钥与 EMBEDDING_API_KEY 已填入真实值
EOF
}

main() {
    ensure_tools
    fetch_source
    ensure_env
    check_env
    build_and_up
    wait_health
    print_summary
}

main "$@"
