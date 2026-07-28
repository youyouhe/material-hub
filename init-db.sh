#!/usr/bin/env bash
# MaterialHub PostgreSQL 初始化脚本
#
# 创建知识库所需的 PG 角色、数据库、pgvector 扩展。
# 幂等：重复执行不会报错，已存在的对象自动跳过。
#
# 用法：
#   ./init-db.sh                  # 从 .env 读取配置（默认）
#   ./init-db.sh --docker         # 通过 docker exec 在 materialhub-pg 容器内执行
#
# 前置：本地已安装 PostgreSQL 14+，当前用户有 sudo 权限（用于 sudo -u postgres）。
# 凭据来源：项目根目录 .env 中的 PG_HOST / PG_PORT / PG_DATABASE / PG_USER / PG_PASSWORD。

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
echo -e "${BLUE}[1/4] 创建 PostgreSQL 角色...${NC}"
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
echo -e "${BLUE}[2/4] 创建数据库...${NC}"
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

# ── 3. 创建 pgvector 扩展（幂等）──
echo ""
echo -e "${BLUE}[3/4] 创建 pgvector 扩展...${NC}"
if [ "$USE_DOCKER" = true ]; then
    docker exec -i "$PG_CONTAINER" psql -U postgres -d "$PG_DATABASE" -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>&1 | grep -v "^CREATE EXTENSION$" || true
else
    sudo -u postgres psql -d "$PG_DATABASE" -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>&1 | grep -v "^CREATE EXTENSION$" || true
fi
echo -e "  ${GREEN}✓${NC} pgvector 扩展已就绪"

# ── 4. 授予权限 ──
echo ""
echo -e "${BLUE}[4/4] 授予权限...${NC}"
if [ "$USE_DOCKER" = true ]; then
    docker exec -i "$PG_CONTAINER" psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE \"$PG_DATABASE\" TO \"$PG_USER\";" >/dev/null 2>&1 || true
    docker exec -i "$PG_CONTAINER" psql -U postgres -d "$PG_DATABASE" -c "GRANT ALL ON SCHEMA public TO \"$PG_USER\";" >/dev/null 2>&1 || true
else
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE \"$PG_DATABASE\" TO \"$PG_USER\";" >/dev/null 2>&1 || true
    sudo -u postgres psql -d "$PG_DATABASE" -c "GRANT ALL ON SCHEMA public TO \"$PG_USER\";" >/dev/null 2>&1 || true
fi
echo -e "  ${GREEN}✓${NC} 权限已授予"

# ── 5. 连接验证 ──
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
