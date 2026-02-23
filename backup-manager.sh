#!/bin/bash
# MaterialHub 备份管理工具

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="$PROJECT_ROOT/backups"
LOG_FILE="$PROJECT_ROOT/backup.log"

# 显示菜单
show_menu() {
    clear
    echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║   MaterialHub 备份管理工具            ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${CYAN}1.${NC} 📋 查看所有备份"
    echo -e "${CYAN}2.${NC} ➕ 立即创建备份"
    echo -e "${CYAN}3.${NC} 🔄 恢复备份"
    echo -e "${CYAN}4.${NC} 🗑️  删除备份"
    echo -e "${CYAN}5.${NC} 📊 查看备份统计"
    echo -e "${CYAN}6.${NC} 📜 查看备份日志"
    echo -e "${CYAN}7.${NC} ⏰ 查看定时任务"
    echo -e "${CYAN}0.${NC} 🚪 退出"
    echo ""
    echo -ne "${YELLOW}请选择操作 [0-7]: ${NC}"
}

# 列出所有备份
list_backups() {
    clear
    echo -e "${BLUE}======================================"
    echo -e "📋 所有备份文件"
    echo -e "======================================${NC}"
    echo ""

    if [ ! -d "$BACKUP_DIR" ]; then
        echo -e "${RED}❌ 备份目录不存在${NC}"
        return
    fi

    BACKUPS=($(find "$BACKUP_DIR" -name "materialhub_backup_*.tar.gz" -type f | sort -r))

    if [ ${#BACKUPS[@]} -eq 0 ]; then
        echo -e "${YELLOW}暂无备份文件${NC}"
        return
    fi

    echo -e "${CYAN}序号  日期时间              大小      文件名${NC}"
    echo -e "──────────────────────────────────────────────────────────"

    for i in "${!BACKUPS[@]}"; do
        backup="${BACKUPS[$i]}"
        filename=$(basename "$backup")
        size=$(du -h "$backup" | cut -f1)
        timestamp=$(echo "$filename" | grep -oP '\d{8}_\d{6}')
        date_formatted=$(echo "$timestamp" | sed 's/\([0-9]\{4\}\)\([0-9]\{2\}\)\([0-9]\{2\}\)_\([0-9]\{2\}\)\([0-9]\{2\}\)\([0-9]\{2\}\)/\1-\2-\3 \4:\5:\6/')

        echo -e "${GREEN}[$i]${NC}   $date_formatted  ${YELLOW}$size${NC}    $filename"
    done

    echo ""
    TOTAL_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
    echo -e "${BLUE}总计: ${#BACKUPS[@]} 个备份，占用空间: $TOTAL_SIZE${NC}"
}

# 创建备份
create_backup() {
    clear
    echo -e "${BLUE}======================================"
    echo -e "➕ 创建新备份"
    echo -e "======================================${NC}"
    echo ""

    "$PROJECT_ROOT/backup.sh"

    echo ""
    read -p "按 Enter 返回菜单..."
}

# 恢复备份
restore_backup() {
    clear
    "$PROJECT_ROOT/restore.sh"
    echo ""
    read -p "按 Enter 返回菜单..."
}

# 删除备份
delete_backup() {
    clear
    echo -e "${BLUE}======================================"
    echo -e "🗑️  删除备份"
    echo -e "======================================${NC}"
    echo ""

    if [ ! -d "$BACKUP_DIR" ]; then
        echo -e "${RED}❌ 备份目录不存在${NC}"
        read -p "按 Enter 返回菜单..."
        return
    fi

    BACKUPS=($(find "$BACKUP_DIR" -name "materialhub_backup_*.tar.gz" -type f | sort -r))

    if [ ${#BACKUPS[@]} -eq 0 ]; then
        echo -e "${YELLOW}暂无备份文件${NC}"
        read -p "按 Enter 返回菜单..."
        return
    fi

    echo -e "${CYAN}序号  日期时间              大小${NC}"
    echo -e "──────────────────────────────────────"

    for i in "${!BACKUPS[@]}"; do
        backup="${BACKUPS[$i]}"
        size=$(du -h "$backup" | cut -f1)
        timestamp=$(basename "$backup" | grep -oP '\d{8}_\d{6}')
        date_formatted=$(echo "$timestamp" | sed 's/\([0-9]\{4\}\)\([0-9]\{2\}\)\([0-9]\{2\}\)_\([0-9]\{2\}\)\([0-9]\{2\}\)\([0-9]\{2\}\)/\1-\2-\3 \4:\5:\6/')

        echo -e "${GREEN}[$i]${NC}   $date_formatted  ${YELLOW}$size${NC}"
    done

    echo ""
    read -p "请输入要删除的备份编号 (或 q 返回): " choice

    if [ "$choice" = "q" ]; then
        return
    fi

    if ! [[ "$choice" =~ ^[0-9]+$ ]] || [ "$choice" -ge ${#BACKUPS[@]} ]; then
        echo -e "${RED}❌ 无效的选择${NC}"
        read -p "按 Enter 返回菜单..."
        return
    fi

    SELECTED_BACKUP="${BACKUPS[$choice]}"
    echo ""
    echo -e "${YELLOW}⚠️  确认删除: $(basename "$SELECTED_BACKUP")${NC}"
    read -p "输入 yes 确认删除: " confirm

    if [ "$confirm" = "yes" ]; then
        rm -f "$SELECTED_BACKUP"
        echo -e "${GREEN}✅ 备份已删除${NC}"
    else
        echo -e "${YELLOW}已取消${NC}"
    fi

    read -p "按 Enter 返回菜单..."
}

# 查看统计
show_stats() {
    clear
    echo -e "${BLUE}======================================"
    echo -e "📊 备份统计信息"
    echo -e "======================================${NC}"
    echo ""

    if [ ! -d "$BACKUP_DIR" ]; then
        echo -e "${RED}❌ 备份目录不存在${NC}"
        read -p "按 Enter 返回菜单..."
        return
    fi

    BACKUP_COUNT=$(find "$BACKUP_DIR" -name "materialhub_backup_*.tar.gz" -type f | wc -l)
    TOTAL_SIZE=$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)
    OLDEST=$(find "$BACKUP_DIR" -name "materialhub_backup_*.tar.gz" -type f | sort | head -1)
    NEWEST=$(find "$BACKUP_DIR" -name "materialhub_backup_*.tar.gz" -type f | sort | tail -1)

    echo -e "${CYAN}备份总数:${NC} $BACKUP_COUNT 个"
    echo -e "${CYAN}总占用空间:${NC} $TOTAL_SIZE"
    echo ""

    if [ ! -z "$OLDEST" ]; then
        oldest_name=$(basename "$OLDEST")
        oldest_date=$(echo "$oldest_name" | grep -oP '\d{8}_\d{6}' | sed 's/\([0-9]\{4\}\)\([0-9]\{2\}\)\([0-9]\{2\}\)_\([0-9]\{2\}\)\([0-9]\{2\}\)\([0-9]\{2\}\)/\1-\2-\3 \4:\5:\6/')
        echo -e "${CYAN}最早备份:${NC} $oldest_date"
    fi

    if [ ! -z "$NEWEST" ]; then
        newest_name=$(basename "$NEWEST")
        newest_date=$(echo "$newest_name" | grep -oP '\d{8}_\d{6}' | sed 's/\([0-9]\{4\}\)\([0-9]\{2\}\)\([0-9]\{2\}\)_\([0-9]\{2\}\)\([0-9]\{2\}\)\([0-9]\{2\}\)/\1-\2-\3 \4:\5:\6/')
        echo -e "${CYAN}最新备份:${NC} $newest_date"
    fi

    echo ""
    echo -e "${CYAN}数据库路径:${NC} $PROJECT_ROOT/backend/data/materials.db"
    if [ -f "$PROJECT_ROOT/backend/data/materials.db" ]; then
        DB_SIZE=$(du -h "$PROJECT_ROOT/backend/data/materials.db" | cut -f1)
        echo -e "${CYAN}数据库大小:${NC} $DB_SIZE"
    fi

    echo ""
    echo -e "${CYAN}定时任务:${NC}"
    crontab -l 2>/dev/null | grep -A1 "MaterialHub" | sed 's/^/  /'

    echo ""
    read -p "按 Enter 返回菜单..."
}

# 查看日志
show_logs() {
    clear
    echo -e "${BLUE}======================================"
    echo -e "📜 备份日志 (最近50行)"
    echo -e "======================================${NC}"
    echo ""

    if [ -f "$LOG_FILE" ]; then
        tail -50 "$LOG_FILE"
    else
        echo -e "${YELLOW}暂无日志${NC}"
    fi

    echo ""
    read -p "按 Enter 返回菜单..."
}

# 查看定时任务
show_crontab() {
    clear
    echo -e "${BLUE}======================================"
    echo -e "⏰ 定时任务配置"
    echo -e "======================================${NC}"
    echo ""

    echo -e "${CYAN}MaterialHub 备份任务:${NC}"
    crontab -l 2>/dev/null | grep -A1 "MaterialHub" || echo "  未配置"

    echo ""
    echo -e "${CYAN}下次执行时间:${NC}"
    echo "  每天凌晨 2:00"

    echo ""
    echo -e "${CYAN}备份脚本路径:${NC}"
    echo "  $PROJECT_ROOT/backup.sh"

    echo ""
    echo -e "${CYAN}日志文件路径:${NC}"
    echo "  $PROJECT_ROOT/backup.log"

    echo ""
    read -p "按 Enter 返回菜单..."
}

# 主循环
while true; do
    show_menu
    read choice

    case $choice in
        1) list_backups; read -p "按 Enter 返回菜单..." ;;
        2) create_backup ;;
        3) restore_backup ;;
        4) delete_backup ;;
        5) show_stats ;;
        6) show_logs ;;
        7) show_crontab ;;
        0)
            echo ""
            echo -e "${GREEN}再见！${NC}"
            exit 0
            ;;
        *)
            echo -e "${RED}无效的选择，请重试${NC}"
            sleep 1
            ;;
    esac
done
