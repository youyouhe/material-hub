#!/bin/bash
# MaterialHub 数据库和文件备份脚本

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

# 备份配置
BACKUP_DIR="$PROJECT_ROOT/backups"
DB_PATH="$BACKEND_DIR/data/materials.db"
IMAGES_DIR="$BACKEND_DIR/data/images"
UPLOADS_DIR="$BACKEND_DIR/data/uploads"

# 保留天数
KEEP_DAYS=30

# 日志文件
LOG_FILE="$PROJECT_ROOT/backup.log"

# 日志函数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ❌ $1${NC}" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] ✅ $1${NC}" | tee -a "$LOG_FILE"
}

log_info() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')] ℹ️  $1${NC}" | tee -a "$LOG_FILE"
}

# 开始备份
log_info "======================================"
log_info "开始备份 MaterialHub 数据"
log_info "======================================"

# 创建备份目录
mkdir -p "$BACKUP_DIR"

# 生成备份文件名（带时间戳）
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
BACKUP_NAME="materialhub_backup_${TIMESTAMP}"
BACKUP_PATH="$BACKUP_DIR/$BACKUP_NAME"

# 创建临时备份目录
mkdir -p "$BACKUP_PATH"

# 1. 备份数据库
if [ -f "$DB_PATH" ]; then
    log_info "备份数据库..."
    cp "$DB_PATH" "$BACKUP_PATH/materials.db"
    DB_SIZE=$(du -h "$DB_PATH" | cut -f1)
    log_success "数据库备份完成 (大小: $DB_SIZE)"
else
    log_error "数据库文件不存在: $DB_PATH"
    exit 1
fi

# 2. 备份图片文件
if [ -d "$IMAGES_DIR" ]; then
    log_info "备份图片文件..."
    cp -r "$IMAGES_DIR" "$BACKUP_PATH/"
    IMAGES_COUNT=$(find "$IMAGES_DIR" -type f | wc -l)
    IMAGES_SIZE=$(du -sh "$IMAGES_DIR" | cut -f1)
    log_success "图片备份完成 ($IMAGES_COUNT 个文件, 大小: $IMAGES_SIZE)"
else
    log_info "图片目录不存在，跳过"
fi

# 3. 备份上传文件
if [ -d "$UPLOADS_DIR" ]; then
    log_info "备份上传文件..."
    cp -r "$UPLOADS_DIR" "$BACKUP_PATH/"
    UPLOADS_COUNT=$(find "$UPLOADS_DIR" -type f | wc -l)
    UPLOADS_SIZE=$(du -sh "$UPLOADS_DIR" | cut -f1)
    log_success "上传文件备份完成 ($UPLOADS_COUNT 个文件, 大小: $UPLOADS_SIZE)"
else
    log_info "上传目录不存在，跳过"
fi

# 4. 添加备份元信息
cat > "$BACKUP_PATH/backup_info.txt" << EOF
MaterialHub 备份信息
====================
备份时间: $(date '+%Y-%m-%d %H:%M:%S')
备份版本: $TIMESTAMP
数据库大小: $DB_SIZE
图片文件数: ${IMAGES_COUNT:-0}
上传文件数: ${UPLOADS_COUNT:-0}
主机名: $(hostname)
====================
EOF

# 5. 压缩备份
log_info "压缩备份文件..."
cd "$BACKUP_DIR"
tar -czf "${BACKUP_NAME}.tar.gz" "$BACKUP_NAME"
COMPRESSED_SIZE=$(du -h "${BACKUP_NAME}.tar.gz" | cut -f1)
log_success "压缩完成 (大小: $COMPRESSED_SIZE)"

# 6. 删除临时目录
rm -rf "$BACKUP_PATH"
log_info "清理临时文件..."

# 7. 清理旧备份（保留最近30天）
log_info "清理 ${KEEP_DAYS} 天前的旧备份..."
DELETED_COUNT=0
if [ -d "$BACKUP_DIR" ]; then
    while IFS= read -r old_backup; do
        rm -f "$old_backup"
        DELETED_COUNT=$((DELETED_COUNT + 1))
        log_info "删除旧备份: $(basename "$old_backup")"
    done < <(find "$BACKUP_DIR" -name "materialhub_backup_*.tar.gz" -type f -mtime +${KEEP_DAYS})
fi

if [ $DELETED_COUNT -gt 0 ]; then
    log_success "清理了 $DELETED_COUNT 个旧备份"
else
    log_info "无需清理旧备份"
fi

# 8. 显示备份摘要
TOTAL_BACKUPS=$(find "$BACKUP_DIR" -name "materialhub_backup_*.tar.gz" -type f | wc -l)
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)

log_info "======================================"
log_success "备份完成！"
log_info "======================================"
log_info "备份文件: $BACKUP_DIR/${BACKUP_NAME}.tar.gz"
log_info "压缩大小: $COMPRESSED_SIZE"
log_info "备份总数: $TOTAL_BACKUPS 个"
log_info "总占用空间: $TOTAL_SIZE"
log_info "======================================"

# 如果是交互式终端，额外显示彩色输出
if [ -t 1 ]; then
    echo ""
    echo -e "${GREEN}✅ 备份成功！${NC}"
    echo -e "${BLUE}📁 备份位置: $BACKUP_DIR/${BACKUP_NAME}.tar.gz${NC}"
    echo -e "${BLUE}📊 压缩大小: $COMPRESSED_SIZE${NC}"
    echo ""
fi

exit 0
