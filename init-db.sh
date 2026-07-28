#!/usr/bin/env bash
# MaterialHub PostgreSQL 初始化脚本
#
# 创建知识库所需的 PG 角色、数据库、pgvector 扩展。
# 幂等：重复执行不会报错，已存在的对象自动跳过。
#
# 用法：
#   ./init-db.sh                  # 从 .env 读取配置（默认）
#   ./init-db.sh --docker         # 通过 docker exec 在 materialhub-pg 容器内执行
# 前置：本地已安装 PostgreSQL 14+（pgvector 系统包缺失时本脚本会自动安装）。
#       当前用户需有 sudo 权限（用于 sudo -u postgres + apt 装包）。

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"

# ── 颜色输出 ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🗄️  MaterialHub PostgreSQL 初始化${NC}"
echo "========================================"

# ── 读取 .env ──
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}✗ 未找到 .env 文件: $ENV_FILE${NC}"
    echo -e "  请先复制 .env.example:  cp .env.example .env"
    exit 1
fi

PG_DATABASE=$(grep -E "^PG_DATABASE=" "$ENV_FILE" | cut -d= -f2 | tr -d '[:space:]')
PG_USER=$(grep -E "^PG_USER=" "$ENV_FILE" | cut -d= -f2 | tr -d '[:space:]')
PG_PASSWORD=$(grep -E "^PG_PASSWORD=" "$ENV_FILE" | cut -d= -f2- | tr -d '[:space:]')
PG_HOST=$(grep -E "^PG_HOST=" "$ENV_FILE" | cut -d= -f2 | tr -d '[:space:]')
PG_PORT=$(grep -E "^PG_PORT=" "$ENV_FILE" | cut -d= -f2 | tr -d '[:space:]')

# 兜底默认值（.env 字段缺失时）
PG_DATABASE="${PG_DATABASE:-materialhub_kb}"
PG_USER="${PG_USER:-materialhub}"
PG_HOST="${PG_HOST:-localhost}"
PG_PORT="${PG_PORT:-5432}"

if [ -z "$PG_PASSWORD" ] || [ "$PG_PASSWORD" = "请修改为强密码（必须配置，docker-compose 启动时校验）" ]; then
    echo -e "${RED}✗ PG_PASSWORD 未在 .env 中配置${NC}"
    echo -e "  请编辑 $ENV_FILE 设置一个强密码"
    exit 1
fi

echo -e "  ${YELLOW}→${NC} 数据库: $PG_DATABASE"
echo -e "  ${YELLOW}→${NC} 用户名: $PG_USER"
echo -e "  ${YELLOW}→${NC} 主机:   $PG_HOST:$PG_PORT"
echo ""

# ── 判断执行方式 ──
USE_DOCKER=false
if [ "$1" = "--docker" ]; then
    USE_DOCKER=true
    PG_CONTAINER="${PG_CONTAINER:-materialhub-pg}"
    echo -e "${BLUE}🐳 Docker 模式: 在容器 $PG_CONTAINER 内执行${NC}"
    echo ""
fi

# ── 1. 创建角色（幂等）──
echo -e "${BLUE}[1/5] 创建 PostgreSQL 角色...${NC}"
ROLE_EXISTS_SQL="SELECT 1 FROM pg_roles WHERE rolname='$PG_USER'"
if [ "$USE_DOCKER" = true ]; then
    ROLE_EXISTS=$(docker exec -i "$PG_CONTAINER" psql -U postgres -tAc "$ROLE_EXISTS_SQL" 2>/dev/null || echo "")
else
    ROLE_EXISTS=$(sudo -u postgres psql -tAc "$ROLE_EXISTS_SQL" 2>/dev/null || echo "")
fi

if [ "$ROLE_EXISTS" = "1" ]; then
    echo -e "  ${GREEN}✓${NC} 角色 '$PG_USER' 已存在，跳过"
    # 确保密码与 .env 一致（静默更新）
    if [ "$USE_DOCKER" = true ]; then
        docker exec -i "$PG_CONTAINER" psql -U postgres -c "ALTER ROLE \"$PG_USER\" WITH LOGIN PASSWORD '$PG_PASSWORD';" >/dev/null 2>&1 || true
    else
        sudo -u postgres psql -c "ALTER ROLE \"$PG_USER\" WITH LOGIN PASSWORD '$PG_PASSWORD';" >/dev/null 2>&1 || true
    fi
else
    if [ "$USE_DOCKER" = true ]; then
        docker exec -i "$PG_CONTAINER" psql -U postgres -c "CREATE ROLE \"$PG_USER\" WITH LOGIN PASSWORD '$PG_PASSWORD' CREATEDB;"
    else
        sudo -u postgres psql -c "CREATE ROLE \"$PG_USER\" WITH LOGIN PASSWORD '$PG_PASSWORD' CREATEDB;"
    fi
    echo -e "  ${GREEN}✓${NC} 角色 '$PG_USER' 已创建"
fi

# ── 2. 创建数据库（幂等）──
echo ""
echo -e "${BLUE}[2/5] 创建数据库...${NC}"
DB_EXISTS_SQL="SELECT 1 FROM pg_database WHERE datname='$PG_DATABASE'"
if [ "$USE_DOCKER" = true ]; then
    DB_EXISTS=$(docker exec -i "$PG_CONTAINER" psql -U postgres -tAc "$DB_EXISTS_SQL" 2>/dev/null || echo "")
else
    DB_EXISTS=$(sudo -u postgres psql -tAc "$DB_EXISTS_SQL" 2>/dev/null || echo "")
fi

if [ "$DB_EXISTS" = "1" ]; then
    echo -e "  ${GREEN}✓${NC} 数据库 '$PG_DATABASE' 已存在，跳过"
else
    if [ "$USE_DOCKER" = true ]; then
        docker exec -i "$PG_CONTAINER" createdb -U postgres -O "$PG_USER" "$PG_DATABASE"
    else
        sudo -u postgres createdb -O "$PG_USER" "$PG_DATABASE"
    fi
    echo -e "  ${GREEN}✓${NC} 数据库 '$PG_DATABASE' 已创建（owner: $PG_USER）"
fi

# ── 3. 确保 pgvector 扩展可用（缺失则自动安装系统包）──
echo ""
echo -e "${BLUE}[3/5] 检查 pgvector 扩展...${NC}"
_ensure_pgvector() {
    # 尝试创建扩展，成功说明系统包已就绪
    local create_out
    if [ "$USE_DOCKER" = true ]; then
        create_out=$(docker exec -i "$PG_CONTAINER" psql -U postgres -d "$PG_DATABASE" -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>&1)
    else
        create_out=$(sudo -u postgres psql -d "$PG_DATABASE" -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>&1)
    fi
    if echo "$create_out" | grep -qiE "CREATE EXTENSION|already exists"; then
        echo -e "  ${GREEN}✓${NC} pgvector 扩展已就绪"
        return 0
    fi

    # 创建失败 —— 大概率是系统包未装。仅本地模式自动修复，Docker 模式报错引导
    if [ "$USE_DOCKER" = true ]; then
        echo -e "  ${YELLOW}⚠${NC} pgvector 不可用，Docker 镜像需内置 pgvector（如 pgvector/pgvector:pg16）"
        echo -e "  $create_out"
        return 1
    fi

    echo -e "  ${YELLOW}→${NC} pgvector 系统包未装，自动安装..."

    # 探测 PG 主版本号以拼对包名（如 postgresql-14-pgvector）
    local pg_version
    pg_version=$(sudo -u postgres psql -tAc "SHOW server_version;" 2>/dev/null | grep -oE '^[0-9]+' || echo "")
    if [ -z "$pg_version" ]; then
        echo -e "  ${RED}✗ 无法探测 PostgreSQL 版本号${NC}"
        return 1
    fi
    echo -e "  ${YELLOW}→${NC} PostgreSQL 版本: $pg_version"

    # 检查 PGDG 源是否已配置，没有则添加（官方推荐方式）
    if ! ls /etc/apt/sources.list.d/*pgdg* >/dev/null 2>&1; then
        echo -e "  ${YELLOW}→${NC} 添加 PostgreSQL 官方 APT 源 (PGDG)..."
        local codename
        codename=$(lsb_release -cs 2>/dev/null || echo "")
        if [ -z "$codename" ]; then
            echo -e "  ${RED}✗ 无法探测发行版代号 (lsb_release)${NC}"
            return 1
        fi
        sudo install -d /etc/apt/keyrings
        curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
            | sudo gpg --dearmor -o /etc/apt/keyrings/postgresql.gpg 2>/dev/null
        echo "deb [signed-by=/etc/apt/keyrings/postgresql.gpg] https://apt.postgresql.org/pub/repos/apt $codename-pgdg main" \
            | sudo tee /etc/apt/sources.list.d/pgdg.list >/dev/null
        echo -e "  ${GREEN}✓${NC} PGDG 源已添加 ($codename)"
    else
        echo -e "  ${GREEN}✓${NC} PGDG 源已存在"
    fi

    # 安装 pgvector 系统包
    echo -e "  ${YELLOW}→${NC} 安装 postgresql-${pg_version}-pgvector..."
    sudo apt-get update -qq
    sudo apt-get install -y "postgresql-${pg_version}-pgvector" >/dev/null 2>&1
    echo -e "  ${GREEN}✓${NC} postgresql-${pg_version}-pgvector 已安装"

    # 重试创建扩展
    if sudo -u postgres psql -d "$PG_DATABASE" -c "CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} pgvector 扩展已就绪（自动安装完成）"
        return 0
    else
        echo -e "  ${RED}✗ 安装后仍无法创建扩展，请手动检查${NC}"
        return 1
    fi
}
_ensure_pgvector

# ── 4. 授予权限 ──
echo ""
echo -e "${BLUE}[4/5] 授予权限...${NC}"
if [ "$USE_DOCKER" = true ]; then
    docker exec -i "$PG_CONTAINER" psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE \"$PG_DATABASE\" TO \"$PG_USER\";" >/dev/null 2>&1 || true
    docker exec -i "$PG_CONTAINER" psql -U postgres -d "$PG_DATABASE" -c "GRANT ALL ON SCHEMA public TO \"$PG_USER\";" >/dev/null 2>&1 || true
else
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE \"$PG_DATABASE\" TO \"$PG_USER\";" >/dev/null 2>&1 || true
    sudo -u postgres psql -d "$PG_DATABASE" -c "GRANT ALL ON SCHEMA public TO \"$PG_USER\";" >/dev/null 2>&1 || true
fi
echo -e "  ${GREEN}✓${NC} 权限已授予"

# ── 5/5. 连接验证 ──
echo ""
echo -e "${BLUE}🔍 验证连接...${NC}"
VERIFY=$(PGPASSWORD="$PG_PASSWORD" psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DATABASE" -tAc "SELECT current_user, current_database();" 2>&1 || echo "")

if echo "$VERIFY" | grep -q "$PG_USER"; then
    echo -e "  ${GREEN}✓${NC} 连接成功: $(echo "$VERIFY" | tr -d ' ')"
    echo -e "  ${GREEN}✓${NC} pgvector 可用: $(PGPASSWORD="$PG_PASSWORD" psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DATABASE" -tAc "SELECT extversion FROM pg_extension WHERE extname='vector';" 2>/dev/null | tr -d '[:space:]')"
else
    echo -e "${RED}✗ 连接失败${NC}"
    echo -e "  $VERIFY"
    echo ""
    echo -e "  ${YELLOW}排查建议:${NC}"
    echo -e "    1. 确认 PostgreSQL 服务已启动:  sudo systemctl status postgresql"
    echo -e "    2. 确认 pg_hba.conf 允许 $PG_USER 从 $PG_HOST 连接"
    echo -e "    3. Docker 部署改用:  ./init-db.sh --docker"
    exit 1
fi

# ── 完成 ──
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}🎉 PostgreSQL 初始化完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}知识库配置（.env 已就绪）:${NC}"
echo -e "  PG_HOST=$PG_HOST"
echo -e "  PG_PORT=$PG_PORT"
echo -e "  PG_DATABASE=$PG_DATABASE"
echo -e "  PG_USER=$PG_USER"
echo ""
