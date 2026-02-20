# MaterialHub 宿主机开发指南

本指南说明如何在宿主机上进行开发调试。

## 🚀 快速开始

### 启动服务
```bash
./start.sh
```

服务启动后会显示访问地址，例如：
```
访问地址:
  → http://localhost:3100
  → http://192.168.8.107:3100
```

### 停止服务
```bash
./stop.sh
```

### 重启服务
```bash
./restart.sh
```

### 查看状态
```bash
./status.sh
```

## 📁 目录结构

```
material-hub/
├── backend/
│   ├── data/              # 数据目录（与Docker共享）
│   │   ├── materials.db   # 数据库文件
│   │   ├── uploads/       # 上传的文档
│   │   └── images/        # 提取的图片
│   ├── venv/              # Python虚拟环境
│   └── main.py            # Backend入口
├── frontend/
│   ├── node_modules/      # Node依赖
│   └── src/               # 前端源码
├── start.sh               # 启动脚本
├── stop.sh                # 停止脚本
├── status.sh              # 状态检查脚本
├── restart.sh             # 重启脚本
├── backend.log            # Backend日志
└── frontend.log           # Frontend日志
```

## 🔧 服务配置

### Backend
- **端口**: 8201
- **环境**: Python虚拟环境 (backend/venv)
- **配置**: .env 文件
- **日志**: backend.log

### Frontend
- **端口**: 3100 (如被占用会自动选择其他端口)
- **开发服务器**: Vite
- **日志**: frontend.log
- **代理**: API请求自动转发到Backend (8201端口)

## 🐳 Docker 集成

宿主机和Docker共享数据目录：

```yaml
# docker-compose.yml
volumes:
  - ./backend/data:/app/data  # 共享数据目录
```

### 切换到Docker运行

1. 停止宿主机服务：
```bash
./stop.sh
```

2. 启动Docker：
```bash
docker-compose up -d
```

3. 访问：http://192.168.8.107:3101

### 切换回宿主机运行

1. 停止Docker：
```bash
docker-compose down
```

2. 启动宿主机服务：
```bash
./start.sh
```

## 📝 开发工作流

### 修改Backend代码
1. 编辑 `backend/*.py` 文件
2. Backend会自动重载（如果使用uvicorn的--reload模式）
3. 或手动重启：`./restart.sh`

### 修改Frontend代码
1. 编辑 `frontend/src/**` 文件
2. Vite会自动热重载
3. 浏览器自动刷新

### 查看日志
```bash
# 实时查看Backend日志
tail -f backend.log

# 实时查看Frontend日志
tail -f frontend.log

# 同时查看两个日志
tail -f backend.log frontend.log
```

## 🔍 调试技巧

### 查看数据库内容
```bash
# 使用SQLite命令行
sqlite3 backend/data/materials.db

# 查看表结构
sqlite> .schema

# 查看公司数据
sqlite> SELECT * FROM companies;

# 查看材料数据
sqlite> SELECT * FROM materials LIMIT 10;
```

### Python虚拟环境
```bash
# 激活虚拟环境
cd backend
source venv/bin/activate

# 手动运行Backend
python main.py

# 运行Python脚本
python -c "from database import *; print('测试')"
```

### 检查端口占用
```bash
# 检查8201端口
lsof -i:8201

# 检查3100-3002端口
lsof -i:3100-3002
```

## ⚠️ 常见问题

### 端口被占用
如果端口被占用，可以：
1. 使用 `./stop.sh` 清理残留进程
2. 手动杀死进程：`kill -9 <PID>`
3. 或者修改端口配置

### 虚拟环境问题
如果遇到Python包导入错误：
```bash
cd backend
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 前端依赖问题
如果遇到前端编译错误：
```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
```

### 数据库锁定
如果数据库被锁定：
```bash
# 停止所有服务
./stop.sh

# 删除SQLite的临时文件
rm -f backend/data/materials.db-shm
rm -f backend/data/materials.db-wal

# 重新启动
./start.sh
```

## 📊 性能监控

### 查看系统资源
```bash
# CPU和内存使用
top -p $(cat .backend.pid .frontend.pid | tr '\n' ',')

# 磁盘使用
du -sh backend/data/
```

### 数据库大小
```bash
# 查看数据库文件大小
ls -lh backend/data/materials.db

# 查看数据统计
./status.sh
```

## 🎯 最佳实践

1. **定期查看状态**: `./status.sh`
2. **监控日志**: 使用 `tail -f` 实时查看日志
3. **及时提交代码**: 修改后及时commit
4. **数据备份**: 定期备份 `backend/data/` 目录
5. **环境一致**: 保持宿主机和Docker环境配置一致

## 🔗 相关文档

- [Backend API文档](api.md)
- [OCR功能说明](OCR_FEATURE.md)
- [Docker配置](docker-compose.yml)
- [环境变量配置](.env.example)
