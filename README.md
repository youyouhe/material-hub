# MaterialHub 📦

MaterialHub 是一个智能材料管理系统，专为处理和管理各类文档材料（营业执照、资质证书、合同等）而设计。系统支持从Word文档自动提取图片、OCR识别、智能信息提取，并能自动关联到公司和人员实体。

## ✨ 主要功能

### 📄 文档处理
- **DOCX文档提取**：自动从Word文档中提取图片，识别章节结构
- **手动图片上传**：支持单张图片直接上传
- **批量材料管理**：按文档、类型、来源分组展示

### 🤖 智能识别
- **OCR文字识别**：集成外部OCR服务，识别图片中的文字
- **LLM智能提取**：使用大语言模型智能提取结构化信息
  - 营业执照：公司名称、法人、统一社会信用代码、地址
  - 资质证书：证书类型、编号、有效期
  - 身份证：姓名、身份证号
  - 合同：甲方、乙方、合同内容
- **智能材料筛选**：使用LLM预判断哪些材料值得OCR（节省成本）
- **自动实体创建**：识别到的公司或人员信息自动创建实体

### 🏢 实体管理
- **公司管理**：公司信息维护，材料关联展示
- **人员管理**：人员信息维护，材料关联展示
- **多对多关联**：材料可同时关联到公司和人员
- **自定义分组**：支持按section自定义材料分类

### 🔍 高级筛选
- **有效期过滤**：查看有效、过期或全部材料
- **关联状态**：查看已关联公司、已关联人员或未关联材料
- **来源类型**：区分DOCX提取和手动上传
- **公司筛选**：按公司查看其关联的材料

### 🎯 用户体验
- **批量选择**：MaterialPicker支持按文档分组，一键全选同文档所有页
- **折叠控制**：全部展开/折叠功能，快速查看概况或详情
- **实时刷新**：OCR处理自动轮询状态更新
- **响应式设计**：适配桌面和移动端

## 🏗️ 技术栈

### 前端
- **React 18** + **TypeScript**
- **Vite** - 快速构建工具
- **Tailwind CSS** - 样式框架
- **Lucide React** - 图标库
- **React Hot Toast** - 通知提示

### 后端
- **FastAPI** - 现代Python Web框架
- **SQLAlchemy** - ORM框架
- **SQLite** - 轻量级数据库
- **Python-docx** - Word文档处理
- **PIL/Pillow** - 图片处理

### AI集成
- **OCR服务**：外部OCR API（需自行部署）
- **LLM提供商**：
  - DeepSeek（推荐）
  - OpenRouter
  - Anthropic Claude

## 📁 项目结构

```
material-hub/
├── backend/                    # 后端服务
│   ├── main.py                # FastAPI主入口
│   ├── database.py            # 数据库模型和连接
│   ├── models.py              # Pydantic数据模型
│   ├── extractor.py           # DOCX提取逻辑
│   ├── ocr_client.py          # OCR服务客户端
│   ├── ocr_agent.py           # LLM智能提取
│   ├── material_filter.py     # 材料预筛选
│   ├── llm_provider.py        # LLM提供商集成
│   ├── auto_processor.py      # 自动实体处理
│   ├── routers/               # API路由
│   │   ├── documents.py       # 文档相关
│   │   ├── materials.py       # 材料相关
│   │   ├── companies.py       # 公司相关
│   │   └── persons.py         # 人员相关
│   ├── Dockerfile             # 后端Docker配置
│   └── requirements.txt       # Python依赖
│
├── frontend/                   # 前端应用
│   ├── src/
│   │   ├── components/        # React组件
│   │   │   ├── CompanyCard.tsx
│   │   │   ├── CompanyDetailModal.tsx
│   │   │   ├── PersonCard.tsx
│   │   │   ├── PersonDetailModal.tsx
│   │   │   ├── MaterialCard.tsx
│   │   │   ├── MaterialPicker.tsx
│   │   │   ├── OCRResultViewer.tsx
│   │   │   └── ...
│   │   ├── pages/             # 页面组件
│   │   │   ├── HomePage.tsx
│   │   │   ├── CompaniesPage.tsx
│   │   │   ├── PersonsPage.tsx
│   │   │   ├── BrowsePage.tsx
│   │   │   └── UploadPage.tsx
│   │   ├── services/          # API服务
│   │   │   └── api.ts
│   │   ├── hooks/             # 自定义Hooks
│   │   ├── types.ts           # TypeScript类型
│   │   └── App.tsx            # 主应用组件
│   ├── Dockerfile             # 前端Docker配置
│   ├── nginx.conf             # Nginx配置
│   └── package.json           # 前端依赖
│
├── data/                       # 数据目录（运行时生成）
│   ├── materials.db           # SQLite数据库
│   ├── files/                 # 提取的图片文件
│   └── images/                # 手动上传的图片
│
├── docker-compose.yml          # Docker编排配置
├── .env.example               # 环境变量示例
├── start.sh                   # 启动脚本
├── stop.sh                    # 停止脚本
├── restart.sh                 # 重启脚本
└── README.md                  # 本文件
```

## 🚀 快速开始

### 环境要求

- Docker & Docker Compose
- 或者：Node.js 18+ 和 Python 3.8+

### 1. Docker部署（推荐）

```bash
# 克隆项目
git clone https://github.com/youyouhe/material-hub.git
cd material-hub

# 配置环境变量
cp .env.example .env
# 编辑.env文件，配置OCR服务和LLM API

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 访问应用
# 前端: http://localhost:5173
# 后端: http://localhost:8101
```

### 2. 本地开发部署

#### 后端

```bash
cd backend

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp ../.env.example ../.env
# 编辑.env文件

# 运行后端
python main.py
# 后端运行在 http://localhost:8101
```

#### 前端

```bash
cd frontend

# 安装依赖
npm install

# 运行开发服务器
npm run dev
# 前端运行在 http://localhost:5173
```

### 3. 使用便捷脚本

```bash
# 启动所有服务
./start.sh

# 查看服务状态
./status.sh

# 停止所有服务
./stop.sh

# 重启服务
./restart.sh
```

## ⚙️ 配置说明

### 环境变量配置

编辑 `.env` 文件：

```bash
# 数据库路径
DB_PATH=data/materials.db

# 服务器配置
HOST=0.0.0.0
PORT=8101

# OCR服务配置（需要外部OCR服务）
OCR_SERVICE_URL=http://host.docker.internal:8010
OCR_TIMEOUT=120

# LLM配置（选择一个提供商）
LLM_PROVIDER=deepseek  # deepseek | openrouter | anthropic

# DeepSeek配置
DEEPSEEK_API_KEY=sk-your-api-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# 智能筛选（推荐开启，节省OCR成本）
ENABLE_LLM_FILTER=true
```

### OCR服务配置

MaterialHub需要外部OCR服务支持。您需要：

1. 部署一个OCR服务（如PaddleOCR、Tesseract等）
2. OCR服务应提供POST接口接收图片并返回识别文本
3. 配置`OCR_SERVICE_URL`指向您的OCR服务地址

OCR服务接口规范：
- 请求：POST multipart/form-data，包含图片文件
- 响应：JSON格式，包含识别的文本

## 📖 使用指南

### 上传文档

1. 进入"上传"页面
2. 选择DOCX文档或单张图片
3. （可选）选择关联的公司
4. 点击上传，系统自动提取图片并创建材料记录

### OCR识别

1. 在材料卡片上点击"OCR"按钮
2. 系统自动调用OCR服务识别文字
3. 使用LLM智能提取结构化信息
4. 自动创建公司/人员实体并关联
5. 查看提取的有效期等信息

### 批量关联材料

1. 打开公司或人员详情页
2. 点击"关联材料"按钮
3. 在MaterialPicker中：
   - 搜索材料
   - 按文档分组展示
   - 使用"全选"按钮选择整个文档
   - 输入自定义section名称（可选）
4. 点击"确认关联"

### 材料分组查看

- 公司/人员详情页中，材料按section或类型分组
- 点击分组标题可展开/折叠
- 使用"全部展开"/"全部折叠"快速切换

### 筛选和搜索

在浏览页面使用筛选器：
- **文档筛选**：按来源文档过滤
- **有效期**：Valid（有效）、Expired（过期）、All（全部）
- **关联状态**：已关联公司、已关联人员、未关联
- **来源类型**：DOCX提取、手动上传
- **公司筛选**：查看特定公司的材料

## 🔧 开发说明

### API文档

后端API文档（Swagger UI）：
```
http://localhost:8101/docs
```

主要API端点：
- `POST /api/documents` - 上传DOCX文档
- `POST /api/materials/upload` - 上传单张图片
- `GET /api/materials` - 搜索材料
- `POST /api/materials/{id}/ocr` - 触发OCR识别
- `GET /api/companies` - 获取公司列表
- `GET /api/persons` - 获取人员列表

### 数据库结构

主要表：
- `documents` - 文档记录
- `materials` - 材料记录（包含OCR结果和提取数据）
- `companies` - 公司实体
- `persons` - 人员实体

关联关系：
- Material → Document (多对一)
- Material → Company (多对一)
- Material → Person (多对一)

### 添加新的材料类型

1. 在 `backend/ocr_agent.py` 中添加识别规则
2. 在 `backend/auto_processor.py` 中添加实体创建逻辑
3. 在前端 `TYPE_LABELS` 中添加显示标签

## 🤝 贡献指南

欢迎贡献代码！请遵循以下步骤：

1. Fork本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交Pull Request

## 📝 许可证

本项目采用MIT许可证。详见 [LICENSE](LICENSE) 文件。

## 🙏 致谢

- FastAPI - 现代Python Web框架
- React - 前端UI库
- Tailwind CSS - 实用优先的CSS框架
- DeepSeek - 高性价比LLM服务

## 📮 联系方式

如有问题或建议，请提交Issue或Pull Request。

---

**MaterialHub** - 让材料管理更智能 🚀
