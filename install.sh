#!/usr/bin/env bash
set -e

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
MCP_DIR="$PROJECT_ROOT/mcp-server"
VENV_DIR="$BACKEND_DIR/venv"

echo ""
echo "╔════════════════════════════════════════════╗"
echo "║       MaterialHub 安装向导                ║"
echo "╚════════════════════════════════════════════╝"
echo ""

# ============================================================
# 1. 检查 Python
# ============================================================
echo "[1/5] 检查 Python 环境..."

PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" --version 2>&1 | awk '{print $2}')
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON_CMD="$cmd"
            echo "  $($PYTHON_CMD --version)"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "[错误] 未找到 Python 3.10+，请先安装"
    echo "  Ubuntu:  sudo apt install python3 python3-venv python3-pip"
    echo "  macOS:   brew install python@3.12"
    exit 1
fi

# 检查 venv 模块
if ! "$PYTHON_CMD" -m venv --help &>/dev/null; then
    echo "[错误] Python venv 模块不可用"
    echo "  Ubuntu:  sudo apt install python3-venv"
    exit 1
fi

# ============================================================
# 2. 检查 Node.js
# ============================================================
echo ""
echo "[2/5] 检查 Node.js 环境..."

if ! command -v node &>/dev/null; then
    echo "[错误] 未找到 Node.js，请先安装 Node.js 18+"
    echo "  https://nodejs.org/"
    exit 1
fi
echo "  Node.js $(node --version)"

if ! command -v npm &>/dev/null; then
    echo "[错误] 未找到 npm"
    exit 1
fi

# ============================================================
# 3. 创建 Python venv 并安装后端依赖
# ============================================================
echo ""
echo "[3/5] 创建 Python 虚拟环境..."

if [ -f "$VENV_DIR/bin/python" ]; then
    echo "  虚拟环境已存在，跳过创建"
else
    echo "  创建 venv 到 backend/venv ..."
    "$PYTHON_CMD" -m venv "$VENV_DIR"
    echo "  [OK] 虚拟环境已创建"
fi

# 激活 venv
source "$VENV_DIR/bin/activate"

echo ""
echo "  安装后端依赖..."
pip install -r "$BACKEND_DIR/requirements.txt" -q
echo "  [OK] 后端依赖已安装"

echo "  安装 MCP Server 依赖..."
pip install -r "$MCP_DIR/requirements.txt" -q && echo "  [OK] MCP Server 依赖已安装" || echo "  [警告] MCP Server 依赖安装失败 (非必须)"

# PaddleOCR (可选)
echo ""
read -p "  是否安装 PaddleOCR 本地引擎? (y/N): " INSTALL_PADDLE
if [[ "$INSTALL_PADDLE" =~ ^[Yy]$ ]]; then
    echo "  安装 PaddleOCR (可能需要几分钟)..."
    pip install paddlepaddle paddleocr -q && echo "  [OK] PaddleOCR 已安装" || echo "  [警告] PaddleOCR 安装失败，可稍后手动安装"
fi

# ============================================================
# 4. 安装前端依赖
# ============================================================
echo ""
echo "[4/5] 安装前端依赖..."

cd "$FRONTEND_DIR"
if [ -f "node_modules/vite/bin/vite.js" ]; then
    echo "  前端依赖已存在，跳过安装"
else
    npm install
    echo "  [OK] 前端依赖已安装"
fi

# ============================================================
# 5. 初始化配置
# ============================================================
echo ""
echo "[5/5] 初始化配置..."

mkdir -p "$BACKEND_DIR/data/uploads" "$BACKEND_DIR/data/images"
echo "  [OK] 数据目录已创建"

if [ ! -f "$BACKEND_DIR/.env" ]; then
    if [ -f "$PROJECT_ROOT/.env.example" ]; then
        cp "$PROJECT_ROOT/.env.example" "$BACKEND_DIR/.env"
        echo "  [OK] .env 配置文件已创建 (请编辑 backend/.env 配置 API 密钥)"
    else
        echo "  [警告] 未找到 .env.example，请手动创建 backend/.env"
    fi
else
    echo "  .env 配置文件已存在"
fi

# ============================================================
# 完成
# ============================================================
echo ""
echo "╔════════════════════════════════════════════╗"
echo "║       安装完成!                            ║"
echo "╚════════════════════════════════════════════╝"
echo ""
echo "  启动服务:  ./start.sh"
echo "  停止服务:  ./stop.sh"
echo ""
echo "  配置文件:  backend/.env"
echo "  默认账号:  admin / admin123"
echo ""
echo "  前端地址:  http://localhost:3100"
echo "  后端地址:  http://localhost:8201"
echo "  API文档:   http://localhost:8201/docs"
echo ""
