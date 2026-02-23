#!/bin/bash
# MaterialHub 数据恢复脚本

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
BACKUP_DIR="$PROJECT_ROOT/backups"

echo -e "${BLUE}======================================"
echo -e "MaterialHub 数据恢复工具"
echo -e "======================================${NC}"
echo ""

# 检查备份目录
if [ ! -d "$BACKUP_DIR" ]; then
    echo -e "${RED}❌ 备份目录不存在: $BACKUP_DIR${NC}"
    exit 1
fi

# 列出可用的备份
echo -e "${BLUE}📋 可用的备份文件:${NC}"
echo ""
BACKUPS=($(find "$BACKUP_DIR" -name "materialhub_backup_*.tar.gz" -type f | sort -r))

if [ ${#BACKUPS[@]} -eq 0 ]; then
    echo -e "${RED}❌ 未找到任何备份文件${NC}"
    exit 1
fi

# 显示备份列表
for i in "${!BACKUPS[@]}"; do
    backup="${BACKUPS[$i]}"
    filename=$(basename "$backup")
    size=$(du -h "$backup" | cut -f1)
    timestamp=$(echo "$filename" | grep -oP '\d{8}_\d{6}')
    date_formatted=$(echo "$timestamp" | sed 's/\([0-9]\{4\}\)\([0-9]\{2\}\)\([0-9]\{2\}\)_\([0-9]\{2\}\)\([0-9]\{2\}\)\([0-9]\{2\}\)/\1-\2-\3 \4:\5:\6/')

    echo -e "  ${GREEN}[$i]${NC} $date_formatted ($size)"
done

echo ""
echo -e "${YELLOW}⚠️  警告: 恢复操作会覆盖现有数据！${NC}"
echo ""

# 让用户选择
read -p "请输入要恢复的备份编号 (或按 Ctrl+C 取消): " choice

if ! [[ "$choice" =~ ^[0-9]+$ ]] || [ "$choice" -ge ${#BACKUPS[@]} ]; then
    echo -e "${RED}❌ 无效的选择${NC}"
    exit 1
fi

SELECTED_BACKUP="${BACKUPS[$choice]}"
echo ""
echo -e "${BLUE}选择的备份: $(basename "$SELECTED_BACKUP")${NC}"
echo ""

# 二次确认
read -p "确认恢复？这将覆盖现有数据 (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo -e "${YELLOW}已取消恢复${NC}"
    exit 0
fi

echo ""
echo -e "${BLUE}======================================"
echo -e "开始恢复..."
echo -e "======================================${NC}"

# 1. 停止服务
echo -e "${YELLOW}→${NC} 停止服务..."
if [ -f "$PROJECT_ROOT/stop.sh" ]; then
    "$PROJECT_ROOT/stop.sh" > /dev/null 2>&1 || true
    sleep 2
    echo -e "${GREEN}✓${NC} 服务已停止"
else
    echo -e "${YELLOW}⚠${NC}  未找到 stop.sh，请手动确保服务已停止"
    read -p "按 Enter 继续..."
fi

# 2. 备份当前数据（以防万一）
echo -e "${YELLOW}→${NC} 备份当前数据..."
SAFETY_BACKUP="$BACKUP_DIR/before_restore_$(date '+%Y%m%d_%H%M%S')"
mkdir -p "$SAFETY_BACKUP"
if [ -f "$BACKEND_DIR/data/materials.db" ]; then
    cp "$BACKEND_DIR/data/materials.db" "$SAFETY_BACKUP/"
fi
if [ -d "$BACKEND_DIR/data/images" ]; then
    cp -r "$BACKEND_DIR/data/images" "$SAFETY_BACKUP/"
fi
if [ -d "$BACKEND_DIR/data/uploads" ]; then
    cp -r "$BACKEND_DIR/data/uploads" "$SAFETY_BACKUP/"
fi
echo -e "${GREEN}✓${NC} 当前数据已备份到: $SAFETY_BACKUP"

# 3. 解压备份
echo -e "${YELLOW}→${NC} 解压备份文件..."
TEMP_DIR=$(mktemp -d)
tar -xzf "$SELECTED_BACKUP" -C "$TEMP_DIR"
BACKUP_NAME=$(basename "$SELECTED_BACKUP" .tar.gz)
EXTRACTED_PATH="$TEMP_DIR/$BACKUP_NAME"

if [ ! -d "$EXTRACTED_PATH" ]; then
    echo -e "${RED}❌ 解压失败${NC}"
    rm -rf "$TEMP_DIR"
    exit 1
fi
echo -e "${GREEN}✓${NC} 解压完成"

# 4. 恢复数据库
echo -e "${YELLOW}→${NC} 恢复数据库..."
if [ -f "$EXTRACTED_PATH/materials.db" ]; then
    mkdir -p "$BACKEND_DIR/data"
    cp "$EXTRACTED_PATH/materials.db" "$BACKEND_DIR/data/"
    echo -e "${GREEN}✓${NC} 数据库恢复完成"
else
    echo -e "${RED}❌ 备份中未找到数据库文件${NC}"
fi

# 5. 恢复图片
echo -e "${YELLOW}→${NC} 恢复图片文件..."
if [ -d "$EXTRACTED_PATH/images" ]; then
    rm -rf "$BACKEND_DIR/data/images"
    cp -r "$EXTRACTED_PATH/images" "$BACKEND_DIR/data/"
    IMAGES_COUNT=$(find "$BACKEND_DIR/data/images" -type f | wc -l)
    echo -e "${GREEN}✓${NC} 图片恢复完成 ($IMAGES_COUNT 个文件)"
else
    echo -e "${YELLOW}⚠${NC}  备份中未找到图片目录"
fi

# 6. 恢复上传文件
echo -e "${YELLOW}→${NC} 恢复上传文件..."
if [ -d "$EXTRACTED_PATH/uploads" ]; then
    rm -rf "$BACKEND_DIR/data/uploads"
    cp -r "$EXTRACTED_PATH/uploads" "$BACKEND_DIR/data/"
    UPLOADS_COUNT=$(find "$BACKEND_DIR/data/uploads" -type f | wc -l)
    echo -e "${GREEN}✓${NC} 上传文件恢复完成 ($UPLOADS_COUNT 个文件)"
else
    echo -e "${YELLOW}⚠${NC}  备份中未找到上传目录"
fi

# 7. 清理临时文件
rm -rf "$TEMP_DIR"

# 8. 显示备份信息
if [ -f "$EXTRACTED_PATH/backup_info.txt" ]; then
    echo ""
    echo -e "${BLUE}======================================"
    echo -e "备份信息:"
    echo -e "======================================${NC}"
    cat "$EXTRACTED_PATH/backup_info.txt"
fi

echo ""
echo -e "${GREEN}======================================"
echo -e "✅ 恢复完成！"
echo -e "======================================${NC}"
echo ""
echo -e "${BLUE}💡 提示:${NC}"
echo -e "  1. 当前数据已安全备份到: $SAFETY_BACKUP"
echo -e "  2. 运行 ./start.sh 重启服务"
echo ""

# 询问是否启动服务
read -p "是否现在启动服务？(yes/no): " start_service
if [ "$start_service" = "yes" ]; then
    echo ""
    "$PROJECT_ROOT/start.sh"
fi
