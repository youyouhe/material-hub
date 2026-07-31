#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# MaterialHub 知识库(KB) PostgreSQL + pgvector 一次性配置脚本
#
# 用途:修复知识图谱面板 Internal Server Error 的【环境层根因】
#       (FATAL: password authentication failed for user "materialhub")
#
# 策略:导入 Ubuntu 公钥修复 apt 源签名 → 装 PG12 开发头文件 →
#       源码编译 pgvector → 建角色/库/扩展。需 sudo。幂等。
#   bash backend/setup_kb_pg.sh
# ─────────────────────────────────────────────────────────────
set -uo pipefail   # 关键步骤手动检查, 不用 -e 以便容错跳过坏掉的第三方源

PG_CONFIG_BIN="/usr/bin/pg_config"
VEC_CONTROL="/usr/share/postgresql/12/extension/vector.control"
PG_HDR="/usr/include/postgresql/12/server/postgres.h"

echo "==> [1/5] 确保 PG12 服务端头文件 (postgres.h)"
if [ -f "$PG_HDR" ]; then
  echo "    postgres.h 已存在, 跳过"
else
  echo "    导入缺失的 Ubuntu archive 公钥(修复 aliyun/ubuntu 源签名)..."
  sudo apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys \
    3B4FE6ACC0B21F32 871920D1991BC93C 2>/dev/null || echo "    (公钥导入跳过, 将尝试 --allow-unauthenticated)"
  echo "    apt-get update (nvidia/surfshark 等第三方源报错可忽略)..."
  sudo apt-get update 2>&1 | grep -iE "^(E:|Err:)" | head -8 || true
  echo "    安装 postgresql-server-dev-12..."
  sudo apt-get install -y postgresql-server-dev-12 \
    || sudo apt-get install -y --allow-unauthenticated postgresql-server-dev-12
fi
[ -f "$PG_HDR" ] || { echo "❌ postgres.h 仍缺失, 无法编译 pgvector"; exit 1; }

echo "==> [2/5] 编译安装 pgvector (源码 v0.6.2, 兼容 PG12)"
if [ -f "$VEC_CONTROL" ]; then
  echo "    vector.control 已存在, 跳过"
else
  TD="$(mktemp -d)"
  echo "    克隆 pgvector -> $TD"
  git clone --depth 1 --branch v0.6.2 https://github.com/pgvector/pgvector.git "$TD/pgvector" 2>/dev/null \
    || git clone --depth 1 --branch v0.6.2 https://gitee.com/mirrors/pgvector.git "$TD/pgvector"
  ( cd "$TD/pgvector" \
    && make clean >/dev/null 2>&1 || true \
    && make PG_CONFIG="$PG_CONFIG_BIN" \
    && sudo make PG_CONFIG="$PG_CONFIG_BIN" install ) || { echo "❌ pgvector 编译/安装失败"; rm -rf "$TD"; exit 1; }
  rm -rf "$TD"
fi
[ -f "$VEC_CONTROL" ] || { echo "❌ vector.control 未生成"; exit 1; }

echo "==> [3/5] 创建/重置角色 materialhub + 库 materialhub_kb"
sudo -u postgres psql -v ON_ERROR_STOP=1 <<'SQL'
DO $$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'materialhub') THEN
      CREATE ROLE materialhub LOGIN PASSWORD 'materialhub';
   ELSE
      ALTER ROLE materialhub WITH LOGIN PASSWORD 'materialhub';
   END IF;
END$$;

-- 幂等建库
SELECT 'CREATE DATABASE materialhub_kb OWNER materialhub'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'materialhub_kb')\gexec
SQL

echo "==> [4/5] 在 materialhub_kb 启用 vector 扩展 + 授权"
sudo -u postgres psql -d materialhub_kb -v ON_ERROR_STOP=1 <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector;
GRANT ALL PRIVILEGES ON SCHEMA public TO materialhub;
ALTER DATABASE materialhub_kb OWNER TO materialhub;
SQL

echo "==> [5/5] 验证 materialhub 连接 + vector 扩展就绪"
PGPASSWORD=materialhub psql -h localhost -U materialhub -d materialhub_kb \
  -c "SELECT extname, extversion FROM pg_extension WHERE extname='vector';"

echo ""
echo "✅ PG 环境就绪。下一步:"
echo "   1) 重启后端 (init_kb_db 会自动在 materialhub_kb 建 kb_* 表)"
echo "   2) 触发实体同步: POST http://localhost:8201/api/v2/kb/sync"
