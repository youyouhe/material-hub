# MaterialHub 备份系统

MaterialHub 的完整数据备份和恢复解决方案。

## 📋 功能特性

- ✅ 自动每日备份（凌晨 2:00）
- ✅ 完整备份（数据库 + 图片 + 上传文件）
- ✅ 压缩存储，节省空间
- ✅ 自动清理 30 天前的旧备份
- ✅ 一键恢复功能
- ✅ 图形化管理界面
- ✅ 详细的备份日志

## 🚀 快速开始

### 立即创建备份

```bash
./backup.sh
```

### 使用管理界面

```bash
./backup-manager.sh
```

管理界面提供以下功能：
1. 📋 查看所有备份
2. ➕ 立即创建备份
3. 🔄 恢复备份
4. 🗑️ 删除备份
5. 📊 查看备份统计
6. 📜 查看备份日志
7. ⏰ 查看定时任务

### 恢复备份

```bash
./restore.sh
```

按照提示选择要恢复的备份。

## 📂 备份内容

每次备份包含：

1. **数据库** - `backend/data/materials.db`
   - 用户账号
   - 材料元数据
   - 公司和人员信息
   - OCR 识别结果

2. **图片文件** - `backend/data/images/`
   - 所有上传的材料图片
   - OCR 识别的图片

3. **上传文件** - `backend/data/uploads/`
   - 原始上传文件（如有）

4. **元信息** - `backup_info.txt`
   - 备份时间
   - 文件统计
   - 系统信息

## 🗂️ 备份文件结构

```
backups/
├── materialhub_backup_20260223_123608.tar.gz
├── materialhub_backup_20260224_020000.tar.gz
└── ...
```

备份文件命名格式：`materialhub_backup_YYYYMMDD_HHMMSS.tar.gz`

## ⏰ 自动备份配置

自动备份已通过 crontab 配置：

```bash
# 每天凌晨 2:00 执行备份
0 2 * * * /mnt/oldroot/home/bird/material-hub/backup.sh >> /mnt/oldroot/home/bird/material-hub/backup.log 2>&1
```

查看 crontab：
```bash
crontab -l
```

## 📊 备份策略

- **频率**: 每天自动备份一次
- **时间**: 凌晨 2:00（避开业务高峰）
- **保留**: 最近 30 天的备份
- **存储**: 压缩格式（.tar.gz）
- **位置**: `./backups/` 目录

## 🔄 恢复流程

恢复操作会自动：

1. ✅ 停止 MaterialHub 服务
2. ✅ 备份当前数据（防止误操作）
3. ✅ 解压选中的备份
4. ✅ 恢复数据库和文件
5. ✅ 询问是否重启服务

**恢复前的数据会保存到**: `backups/before_restore_YYYYMMDD_HHMMSS/`

## 📝 日志文件

所有备份操作都会记录到日志：

```bash
# 查看备份日志
tail -f backup.log

# 或使用管理界面查看
./backup-manager.sh  # 选择 6. 查看备份日志
```

## 🛠️ 手动操作

### 手动创建备份

```bash
./backup.sh
```

### 查看备份列表

```bash
ls -lh backups/
```

### 解压查看备份内容

```bash
tar -xzf backups/materialhub_backup_YYYYMMDD_HHMMSS.tar.gz
```

### 删除特定备份

```bash
rm backups/materialhub_backup_YYYYMMDD_HHMMSS.tar.gz
```

### 修改保留天数

编辑 `backup.sh`，修改：
```bash
KEEP_DAYS=30  # 改为你想要的天数
```

## ⚠️ 注意事项

1. **恢复操作会覆盖现有数据**
   恢复前请确认选择了正确的备份

2. **定期检查备份**
   建议定期检查备份日志和备份文件

3. **磁盘空间**
   确保有足够的磁盘空间存储备份

4. **权限问题**
   确保脚本有执行权限和文件访问权限

5. **服务停止**
   恢复操作会自动停止服务，完成后需要重启

## 📞 故障排查

### 备份失败

1. 检查磁盘空间
   ```bash
   df -h
   ```

2. 检查文件权限
   ```bash
   ls -la backend/data/
   ```

3. 查看错误日志
   ```bash
   tail -50 backup.log
   ```

### 恢复失败

1. 确认备份文件完整
   ```bash
   tar -tzf backups/materialhub_backup_YYYYMMDD_HHMMSS.tar.gz
   ```

2. 检查服务是否已停止
   ```bash
   ./status.sh
   ```

3. 手动恢复
   ```bash
   # 停止服务
   ./stop.sh

   # 解压备份
   cd backups
   tar -xzf materialhub_backup_YYYYMMDD_HHMMSS.tar.gz

   # 复制文件
   cp materialhub_backup_YYYYMMDD_HHMMSS/materials.db ../backend/data/
   cp -r materialhub_backup_YYYYMMDD_HHMMSS/images ../backend/data/

   # 重启服务
   ./start.sh
   ```

## 🔗 相关脚本

- `backup.sh` - 备份脚本
- `restore.sh` - 恢复脚本
- `backup-manager.sh` - 管理界面
- `start.sh` - 启动服务
- `stop.sh` - 停止服务
- `status.sh` - 查看状态

## 📈 最佳实践

1. **定期测试恢复**
   每月至少测试一次恢复流程

2. **异地备份**
   定期将备份复制到其他服务器或云存储

3. **监控备份**
   设置告警，确保备份任务正常执行

4. **文档记录**
   记录重要操作和配置变更

## 📮 技术支持

如有问题，请查看：
- 备份日志：`backup.log`
- 服务日志：`backend.log`
- 系统状态：`./status.sh`
