@echo off
chcp 65001 >nul
title MaterialHub 安装向导
setlocal

set PROJECT_ROOT=%~dp0
set BACKEND_DIR=%PROJECT_ROOT%backend
set FRONTEND_DIR=%PROJECT_ROOT%frontend
set MCP_DIR=%PROJECT_ROOT%mcp-server
set VENV_DIR=%BACKEND_DIR%\venv

echo.
echo ╔════════════════════════════════════════════╗
echo ║       MaterialHub 安装向导                ║
echo ╚════════════════════════════════════════════╝
echo.

:: ============================================================
:: 1. 检查 Python
:: ============================================================
echo [1/5] 检查 Python 环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+ 并加入 PATH
    echo   下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYTHON_VER=%%v
echo   Python %PYTHON_VER%

:: ============================================================
:: 2. 检查 Node.js
:: ============================================================
echo.
echo [2/5] 检查 Node.js 环境...
node --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Node.js，请先安装 Node.js 18+ 并加入 PATH
    echo   下载地址: https://nodejs.org/
    pause
    exit /b 1
)
for /f %%v in ('node --version 2^>^&1') do set NODE_VER=%%v
echo   Node.js %NODE_VER%

:: ============================================================
:: 3. 创建 Python venv 并安装后端依赖
:: ============================================================
echo.
echo [3/5] 创建 Python 虚拟环境...

if exist "%VENV_DIR%\Scripts\python.exe" (
    echo   虚拟环境已存在，跳过创建
) else (
    echo   创建 venv 到 backend\venv ...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败
        pause
        exit /b 1
    )
    echo   [OK] 虚拟环境已创建
)

:: 激活 venv 并安装依赖
echo.
echo   安装后端依赖...
call "%VENV_DIR%\Scripts\activate.bat"

pip install -r "%BACKEND_DIR%\requirements.txt" -q
if errorlevel 1 (
    echo [错误] 后端依赖安装失败
    pause
    exit /b 1
)
echo   [OK] 后端依赖已安装

:: MCP Server 依赖
echo   安装 MCP Server 依赖...
pip install -r "%MCP_DIR%\requirements.txt" -q
if errorlevel 1 (
    echo [警告] MCP Server 依赖安装失败 (非必须)
) else (
    echo   [OK] MCP Server 依赖已安装
)

:: PaddleOCR (可选)
echo.
set /p INSTALL_PADDLE="  是否安装 PaddleOCR 本地引擎? (y/N): "
if /i not "%INSTALL_PADDLE%"=="y" goto :skip_paddle
echo   安装 PaddleOCR (可能需要几分钟)...
pip install paddlepaddle paddleocr -q
if errorlevel 1 (
    echo   [警告] PaddleOCR 安装失败，可稍后手动安装
) else (
    echo   [OK] PaddleOCR 已安装
)
:skip_paddle

:: ============================================================
:: 4. 安装前端依赖
:: ============================================================
echo.
echo [4/5] 安装前端依赖...
cd /d "%FRONTEND_DIR%"
if exist "node_modules\vite\bin\vite.js" (
    echo   前端依赖已存在，跳过安装
) else (
    call npm install
    if errorlevel 1 (
        echo [错误] 前端依赖安装失败
        pause
        exit /b 1
    )
    echo   [OK] 前端依赖已安装
)

:: ============================================================
:: 5. 初始化配置
:: ============================================================
echo.
echo [5/5] 初始化配置...

:: 创建数据目录
if not exist "%BACKEND_DIR%\data\uploads" mkdir "%BACKEND_DIR%\data\uploads"
if not exist "%BACKEND_DIR%\data\images" mkdir "%BACKEND_DIR%\data\images"
echo   [OK] 数据目录已创建

:: .env 文件
if not exist "%BACKEND_DIR%\.env" (
    copy "%PROJECT_ROOT%.env.example" "%BACKEND_DIR%\.env" >nul 2>&1
    if exist "%BACKEND_DIR%\.env" (
        echo   [OK] .env 配置文件已创建 (请编辑 backend\.env 配置 API 密钥)
    ) else (
        echo   [警告] .env 创建失败，请手动复制 .env.example 到 backend\.env
    )
) else (
    echo   .env 配置文件已存在
)

:: ============================================================
:: 完成
:: ============================================================
echo.
echo ╔════════════════════════════════════════════╗
echo ║       安装完成!                            ║
echo ╚════════════════════════════════════════════╝
echo.
echo   启动服务:  start.bat
echo   停止服务:  stop.bat
echo.
echo   配置文件:  backend\.env
echo   默认账号:  admin / admin123
echo.
echo   前端地址:  http://localhost:3100
echo   后端地址:  http://localhost:8201
echo   API文档:   http://localhost:8201/docs
echo.
pause
