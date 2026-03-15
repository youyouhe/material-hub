@echo off
chcp 65001 >nul
echo 正在停止 MaterialHub 服务...

:: 用 PowerShell 精确查找端口对应的 PID 并杀掉进程树
:: 比 netstat + findstr + for /f 解析更可靠

echo 停止 Backend (端口 8201)...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8201 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Write-Host ('  杀掉 PID: ' + $_.OwningProcess); Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"

echo 停止 Frontend (端口 3100)...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 3100 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Write-Host ('  杀掉 PID: ' + $_.OwningProcess); Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"

:: 兜底：按窗口标题匹配 start.bat 创建的窗口
taskkill /FI "WINDOWTITLE eq MaterialHub-Backend*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq MaterialHub-Frontend*" /T /F >nul 2>&1

:: 等一秒让端口释放
timeout /t 1 /nobreak >nul

:: 二次检查
powershell -NoProfile -Command "$ports = @(8201, 3100); foreach ($p in $ports) { $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue; if ($c) { Write-Host ('[!] 端口' + $p + '仍被占用，强制清理 PID:' + $c.OwningProcess); Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue } }"

echo [OK] 服务已停止
pause
