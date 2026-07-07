# 数据库迁移

本目录包含数据库schema变更的SQL脚本。

## 迁移列表

- `001_initial_schema.sql` - 初始数据库结构（由database.py自动创建）
- `002_add_processing_progress.sql` - 添加实时进度追踪字段

## 如何应用迁移

### 自动方式（推荐）
数据库会在启动时自动创建所需的表和字段（通过SQLAlchemy）。

### 手动方式
如果需要手动应用迁移：

```bash
cd backend
sqlite3 data/materials.db < migrations/002_add_processing_progress.sql
```

## 如何创建新迁移

1. 修改 `database.py` 中的模型
2. 创建新的迁移脚本 `migrations/00X_description.sql`
3. 使用 `ALTER TABLE` 命令添加/修改列
4. 更新此 README

## 注意事项

- SQLite 不支持 `ALTER COLUMN` 或 `DROP COLUMN`
- 如果需要修改列类型或删除列，需要：
  1. 创建新表
  2. 复制数据
  3. 删除旧表
  4. 重命名新表

## 当前Schema版本

当前版本：002
最后更新：2026-03-01
