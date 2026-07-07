#!/bin/bash
# Backend 进程监控脚本 - 用于调试自动停止问题

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PID_FILE="$PROJECT_ROOT/.backend.pid"
LOG_FILE="$PROJECT_ROOT/monitor.log"

if [ ! -f "$BACKEND_PID_FILE" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 错误: PID文件不存在" | tee -a "$LOG_FILE"
    exit 1
fi

BACKEND_PID=$(cat "$BACKEND_PID_FILE")

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始监控 Backend PID: $BACKEND_PID" | tee -a "$LOG_FILE"
echo "按 Ctrl+C 停止监控" | tee -a "$LOG_FILE"
echo "---" | tee -a "$LOG_FILE"

# 每5秒检查一次
while true; do
    if ps -p $BACKEND_PID > /dev/null 2>&1; then
        # 进程还在运行，记录状态
        PROC_INFO=$(ps -p $BACKEND_PID -o pid,ppid,pgid,sid,stat,rss,vsz,etime,comm --no-headers)
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✓ 运行中: $PROC_INFO" | tee -a "$LOG_FILE"
    else
        # 进程已停止
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✗ 进程已停止!" | tee -a "$LOG_FILE"

        # 检查退出状态
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 最后10行 backend.log:" | tee -a "$LOG_FILE"
        tail -10 "$PROJECT_ROOT/backend.log" | tee -a "$LOG_FILE"

        # 检查系统日志
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 检查 dmesg (最后20行):" | tee -a "$LOG_FILE"
        dmesg -T 2>/dev/null | tail -20 | tee -a "$LOG_FILE"

        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 监控结束" | tee -a "$LOG_FILE"
        exit 1
    fi

    sleep 5
done
