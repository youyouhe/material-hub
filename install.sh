#!/usr/bin/env bash
# MaterialHub 一键安装脚本
#
# 自动完成：系统依赖检查 → Python venv → 后端+MCP 依赖 → 前端依赖
#           → PostgreSQL+pgvector → 配置文件初始化 → 依赖验证
#
# 用法：
#   ./install.sh           # 完整安装
#   ./install.sh --skip-pg # 跳过 PostgreSQL（已手动配置时）
#
# 幂等：可重复执行，已安装的部分自动跳过。

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
MCP_DIR="$PROJECT_ROOT/mcp-server"
VENV_DIR="$BACKEND_DIR/venv"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SKIP_PG=false
[ "$1" = "--skip-pg" ] && SKIP_PG=true

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║       MaterialHub 安装向导                 ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════╝${NC}"
echo ""

# ============================================================
# [1/7] 系统依赖检查
# ============================================================
echo -e "${BLUE}[1/7] 检查系统依赖...${NC}"

check_cmd() {
    command -v "$1" &>/dev/null
}

# Python 3.10+
PYTHON_CMD=""
for cmd in python3 python; do
    if check_cmd "$cmd"; then
        ver=$("$cmd" --version 2>&1 | awk '{print $2}')
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON_CMD="$cmd"
            echo -e "  ${GREEN}✓${NC} Python $ver ($cmd)"
            break
        fi
    fi
done
if [ -z "$PYTHON_CMD" ]; then
    echo -e "  ${RED}✗ 未找到 Python 3.10+${NC}"
    echo -e "    Ubuntu:  sudo apt install python3 python3-venv python3-pip"
    echo -e "  macOS:   brew install python@3.12"
    exit 1
fi

# venv 模块
if ! "$PYTHON_CMD" -m venv --help &>/dev/null; then
    echo -e "  ${RED}✗ Python venv 模块不可用${NC}"
    echo -e "    Ubuntu:  sudo apt install python3-venv"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} venv 模块可用"

# Node.js
if check_cmd node; then
    echo -e "  ${GREEN}✓${NC} Node.js $(node --version)"
else
    echo -e "  ${RED}✗ 未找到 Node.js${NC}"
    echo -e "    Ubuntu:  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs"
    echo -e "    macOS:   brew install node"
    exit 1
fi

# npm
if check_cmd npm; then
    echo -e "  ${GREEN}✓${NC} npm $(npm --version)"
else
    echo -e "  ${RED}✗ 未找到 npm${NC}"
    exit 1
fi

# ffmpeg（音视频 ASR 必需，仅警告不阻断）
if check_cmd ffmpeg; then
    echo -e "  ${GREEN}✓${NC} ffmpeg $(ffmpeg -version 2>&1 | head -1 | awk '{print $3}')"
else
    echo -e "  ${YELLOW}⚠${NC} ffmpeg 未安装（音视频转写功能不可用）"
    echo -e "    Ubuntu:  sudo apt install -y ffmpeg"
    echo -e "    macOS:   brew install ffmpeg"
fi

# ============================================================
# [2/7] PostgreSQL + pgvector（知识库必需）
# ============================================================
echo ""
echo -e "${BLUE}[2/7] 检查 PostgreSQL...${NC}"

if [ "$SKIP_PG" = true ]; then
    echo -e "  ${YELLOW}⚠${NC} 已跳过 PostgreSQL（--skip-pg）"
elif check_cmd psql; then
    PG_VER=$(psql --version | awk '{print $3}' | cut -d. -f1)
    echo -e "  ${GREEN}✓${NC} PostgreSQL $PG_VER 已安装"
    # pgvector 由 init-db.sh 自动安装
    echo -e "  ${YELLOW}→${NC} pgvector 扩展将由 ./init-db.sh 自动安装"
else
    echo -e "  ${YELLOW}⚠${NC} PostgreSQL 未安装"
    echo -e "    PostgreSQL 是知识库（向量搜索/多跳推理）的必需依赖。"
    echo -e "    不装也能运行，但知识库相关功能不可用。"
    echo ""
    read -p "  是否现在安装 PostgreSQL 14? (y/N): " INSTALL_PG
    if [[ "$INSTALL_PG" =~ ^[Yy]$ ]]; then
        echo -e "  ${YELLOW}→${NC} 安装 PostgreSQL..."
        if check_cmd apt-get; then
            sudo apt-get update -qq
            sudo apt-get install -y postgresql postgresql-contrib >/dev/null 2>&1
            sudo systemctl start postgresql 2>/dev/null || true
            echo -e "  ${GREEN}✓${NC} PostgreSQL 已安装并启动"
        elif check_cmd brew; then
            brew install postgresql@14
            brew services start postgresql@14
            echo -e "  ${GREEN}✓${NC} PostgreSQL 已安装并启动"
        else
            echo -e "  ${RED}✗${NC} 无法自动安装，请手动安装 PostgreSQL 14+"
        fi
    else
        echo -e "  ${YELLOW}⚠${NC} 跳过 PostgreSQL（知识库功能将不可用）"
    fi
fi

# ============================================================
# [3/7] 创建 Python venv
# ============================================================
echo ""
echo -e "${BLUE}[3/7] 创建 Python 虚拟环境...${NC}"

if [ -f "$VENV_DIR/bin/activate" ]; then
    echo -e "  ${GREEN}✓${NC} venv 已存在，复用"
else
    "$PYTHON_CMD" -m venv "$VENV_DIR"
    echo -e "  ${GREEN}✓${NC} venv 已创建 ($VENV_DIR)"
fi

# 激活 venv
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q

# ============================================================
# [4/7] 安装 Python 依赖（后端 + MCP）
# ============================================================
echo ""
echo -e "${BLUE}[4/7] 安装 Python 依赖...${NC}"

echo -e "  ${YELLOW}→${NC} 后端依赖 (FastAPI, SQLAlchemy, PyMuPDF, pgvector, tiktoken...)..."
pip install -r "$BACKEND_DIR/requirements.txt" -q
echo -e "  ${GREEN}✓${NC} 后端依赖已安装"

echo -e "  ${YELLOW}→${NC} MCP Server 依赖 (mcp[cli] <2.0.0, httpx)..."
pip install -r "$MCP_DIR/requirements.txt" -q && echo -e "  ${GREEN}✓${NC} MCP Server 依赖已安装" || echo -e "  ${YELLOW}⚠${NC} MCP Server 依赖安装失败（非必须，MCP 远程接入不可用）"

# PaddleOCR（可选，大依赖）
echo ""
read -p "  是否安装 PaddleOCR 本地引擎? (y/N): " INSTALL_PADDLE
if [[ "$INSTALL_PADDLE" =~ ^[Yy]$ ]]; then
    echo -e "  ${YELLOW}→${NC} 安装 PaddleOCR（可能需要几分钟）..."
    pip install paddlepaddle paddleocr -q && echo -e "  ${GREEN}✓${NC} PaddleOCR 已安装" || echo -e "  ${YELLOW}⚠${NC} PaddleOCR 安装失败，可稍后手动安装"
else
    echo -e "  ${YELLOW}⚠${NC} 跳过 PaddleOCR（可用云端 OCR 替代，在 .env 配置 OCR_PROVIDER）"
fi

# ============================================================
# [5/7] 安装前端依赖
# ============================================================
echo ""
echo -e "${BLUE}[5/7] 安装前端依赖...${NC}"

cd "$FRONTEND_DIR"
if [ -d "node_modules/vite" ]; then
    echo -e "  ${GREEN}✓${NC} 前端依赖已存在，跳过"
else
    npm install --no-audit --no-fund
    echo -e "  ${GREEN}✓${NC} 前端依赖已安装"
fi
cd "$PROJECT_ROOT"

# ============================================================
# [6/7] 初始化配置 + 数据库
# ============================================================
echo ""
echo -e "${BLUE}[6/7] 初始化配置...${NC}"

# 数据目录
mkdir -p "$BACKEND_DIR/data/uploads" "$BACKEND_DIR/data/images"
echo -e "  ${GREEN}✓${NC} 数据目录已创建"

# .env 文件（项目根，与 main.py 的读取路径一致）
ENV_FILE="$PROJECT_ROOT/.env"
if [ ! -f "$ENV_FILE" ]; then
    if [ -f "$PROJECT_ROOT/.env.example" ]; then
        cp "$PROJECT_ROOT/.env.example" "$ENV_FILE"
        echo -e "  ${GREEN}✓${NC} .env 已创建（请编辑 $ENV_FILE 配置 API 密钥）"
    else
        echo -e "  ${YELLOW}⚠${NC} 未找到 .env.example"
    fi
else
    echo -e "  ${GREEN}✓${NC} .env 已存在"
fi

# PostgreSQL 初始化（如有 psql 且未跳过）
if [ "$SKIP_PG" = false ] && check_cmd psql; then
    echo ""
    if [ -f "$PROJECT_ROOT/init-db.sh" ]; then
        echo -e "  ${YELLOW}→${NC} 运行 init-db.sh 初始化 PostgreSQL（角色/库/pgvector）..."
        chmod +x "$PROJECT_ROOT/init-db.sh"
        bash "$PROJECT_ROOT/init-db.sh" && echo -e "  ${GREEN}✓${NC} PostgreSQL 初始化完成" || echo -e "  ${YELLOW}⚠${NC} init-db.sh 执行失败，请手动检查（可能需要先配置 .env 中的 PG_PASSWORD）"
    fi
fi

# ============================================================
# [7/7] 依赖验证（确保关键 import 成功）
# ============================================================
echo ""
echo -e "${BLUE}[7/7] 验证依赖...${NC}"

cd "$BACKEND_DIR"
VERIFY_OK=true

# 后端核心模块
echo -n "  后端核心模块..."
if python -c "import main" 2>/dev/null; then
    echo -e " ${GREEN}✓${NC}"
else
    echo -e " ${RED}✗${NC}"
    python -c "import main" 2>&1 | head -3 | sed 's/^/      /'
    VERIFY_OK=false
fi

# MCP server
echo -n "  MCP FastMCP..."
if python -c "from mcp.server.fastmcp import FastMCP" 2>/dev/null; then
    echo -e " ${GREEN}✓${NC}"
else
    echo -e " ${RED}✗${NC} (mcp 版本可能 >=2.0.0，运行: pip install 'mcp[cli]<2.0.0')"
    VERIFY_OK=false
fi

# pgvector
echo -n "  pgvector (Python)..."
if python -c "from pgvector.sqlalchemy import Vector" 2>/dev/null; then
    echo -e " ${GREEN}✓${NC}"
else
    echo -e " ${RED}✗${NC}"
    VERIFY_OK=false
fi

# PyMuPDF
echo -n "  PyMuPDF (PDF)..."
if python -c "import fitz; print(fitz.__version__)" 2>/dev/null; then
    echo -e " ${GREEN}✓${NC}"
else
    echo -e " ${RED}✗${NC}"
    VERIFY_OK=false
fi

cd "$PROJECT_ROOT"

# ============================================================
# 完成
# ============================================================
echo ""
if [ "$VERIFY_OK" = true ]; then
    echo -e "${GREEN}╔════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║       ✅ 安装完成!                         ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════╝${NC}"
else
    echo -e "${YELLOW}╔════════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}║       ⚠️  安装完成（部分依赖验证失败）      ║${NC}"
    echo -e "${YELLOW}╚════════════════════════════════════════════╝${NC}"
    echo -e "  请按上方提示修复后重新运行 ./install.sh"
fi
echo ""
echo -e "${BLUE}下一步:${NC}"
echo -e "  1. 编辑配置:  ${YELLOW}nano .env${NC}（填入 DEEPSEEK_API_KEY、EMBEDDING_API_KEY 等）"
echo -e "  2. 启动服务:  ${YELLOW}./start.sh${NC}"
echo -e "  3. 访问:      ${YELLOW}http://localhost:3100${NC}（admin / admin123）"
echo ""
echo -e "${BLUE}可选:${NC}"
echo -e "  - PG 初始化:   ${YELLOW}./init-db.sh${NC}（如未在安装时自动运行）"
echo -e "  - 开启 Swagger: 在 .env 中设 ${YELLOW}ENABLE_DOCS=true${NC}"
echo -e "  - OCR 配置:    在 .env 中设 ${YELLOW}OCR_PROVIDER=bigmodel${NC}（云端，免装 PaddleOCR）"
echo ""
