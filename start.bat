@echo off
chcp 65001 >nul
title MaterialHub

set PROJECT_ROOT=%~dp0
set BACKEND_DIR=%PROJECT_ROOT%backend
set FRONTEND_DIR=%PROJECT_ROOT%frontend
set VENV_DIR=%BACKEND_DIR%\venv

echo ========================================
echo   MaterialHub 启动
echo ========================================

:: 检查是否已安装
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [错误] 未找到虚拟环境，请先运行 install.bat
    pause
    exit /b 1
)

:: 创建数据目录
if not exist "%BACKEND_DIR%\data\uploads" mkdir "%BACKEND_DIR%\data\uploads"
if not exist "%BACKEND_DIR%\data\images" mkdir "%BACKEND_DIR%\data\images"

:: 生成 Backend 启动脚本
echo @echo off > "%BACKEND_DIR%\_run.bat"
echo cd /d %BACKEND_DIR% >> "%BACKEND_DIR%\_run.bat"
echo call venv\Scripts\activate.bat >> "%BACKEND_DIR%\_run.bat"
echo python -u main.py >> "%BACKEND_DIR%\_run.bat"
echo pause >> "%BACKEND_DIR%\_run.bat"

:: 启动 Backend
echo.
echo [1/2] 启动 Backend 服务 (端口 8201)...
start "MaterialHub-Backend" cmd /k "%BACKEND_DIR%\_run.bat"
echo [OK] Backend 已启动 (新窗口)

:: 等待 Backend 就绪
echo 等待 Backend 就绪...
timeout /t 3 /nobreak >nul

:: 启动 Frontend
echo.
echo [2/2] 启动 Frontend 服务 (端口 3100)...
cd /d "%FRONTEND_DIR%"
if not exist "node_modules" (
    echo 安装前端依赖...
    call npm install
)
start "MaterialHub-Frontend" cmd /k "npm run dev"
echo [OK] Frontend 已启动 (新窗口)

timeout /t 3 /nobreak >nul

echo.
echo ========================================
echo   MaterialHub 启动成功!
echo ========================================
echo.
echo   前端: http://localhost:3100
echo   后端: http://localhost:8201
echo   API文档: http://localhost:8201/docs
echo.
echo   关闭服务: 关闭对应的 cmd 窗口
echo   或运行: stop.bat
echo ========================================
echo.
pause
