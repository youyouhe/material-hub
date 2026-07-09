# MaterialHub 📦

MaterialHub 是一个 AI 驱动的企业文档管理系统（DMS），集成知识库、多跳推理、智能体（Agent）与知识图谱能力。支持 PDF / 图片 / 音频 / 视频 / Word 全格式自动入库，从原始文件到可推理的知识，端到端自动化。

> 从「存文档」进化到「懂文档」——不仅管理材料，更能跨文档、跨实体推理。

## ✨ 核心能力

### 🤖 AI Agent（智能体）
内置会话式 Agent，配备 **20+ 工具**，可自主查询、归类、创建文件夹、探索知识图谱：

| 工具类别 | 能力 |
|---------|------|
| **KB 深度搜索** `kb_deep_search` | 语义 + 知识图谱多跳推理，回答跨实体复杂问题 |
| **图谱探索** `kb_graph_explore` | 以实体为中心展开关系网、关联事件、文档 |
| **文件夹管理** `create/update/delete_folder` | Agent 可自主创建、重命名、移动文件夹 |
| **文档归类** `update_document` / `set_folder_mapping` | 自动类型映射、批量归类 |
| **文档查询** `search/read/list/get_statistics` | 全部分页，避免上下文溢出 |

Agent 同步暴露给 **MCP 客户端**（Claude Desktop 等），支持文件夹级权限隔离。

### 📚 知识库与多跳推理（移植自 SAG）
- **双数据库架构**：SQLite（主库）+ PostgreSQL/pgvector（知识库）
- **8 步多跳管道**：查询向量化 → 实体召回 → 事件召回 → 图谱扩展 → 切片检索 → 粗排 → 重排 → 结果聚合
- **混合搜索**：向量语义 + FTS5 关键词，RRF 融合排序
- **Rerank**：qwen3-rerank 远程 + 本地 lexical fallback
- **Embedding**：SiliconFlow Qwen3-Embedding-0.6B（1024d，HNSW 索引）

### 🎬 全格式自动入库
| 格式 | 提取方式 | 入库流程 |
|------|---------|---------|
| PDF / 图片 | OCR（PaddleOCR） | OCR → LLM 分类 → 实体链接 → FTS + KB |
| 音频 MP3/WAV | GLM ASR 语音转文字 | 切片转写 → LLM 分类 → 实体链接 |
| 视频 MP4/MKV | ffmpeg 提取音轨 → ASR | 同上 |
| Word DOCX | python-docx | 文本提取 → LLM 分类 |
| 纯文本 TXT | 直接读取 | LLM 分类 |

所有格式统一进入 KB 管道（chunk → embed → entity → event → 可多跳搜索）。

### 🕸️ 知识图谱可视化
- **实体多类型**：org / person / project / product / certificate / topic / concept / location（LLM 自由分类，无白名单）
- **vis-network 力导向图**：文档为中心的星型 + 同类型实体网状集群 + 显式关系边
- **交互**：拖拽 / 缩放 / 双击展开 / 点击查看边含义 / 全屏模式
- **Agent 出图**：聊天中 Agent 调用 `kb_graph_explore` 时自动渲染内嵌图谱

### 🏢 DMS 核心与权限
- **RBAC**：admin / editor / viewer 三级角色
- **文件夹级权限**：`get_accessible_folder_ids()` 控制可见范围
- **文档全生命周期**：draft → active → expired → archived
- **版本管理**：文档多版本、PDF 分页、缩略图
- **投标子系统**：项目、需求清单、团队、文档关联

## 🏗️ 技术栈

### 前端
- **React 18** + **TypeScript** + **Vite**
- **Tailwind CSS**（自定义 cp-* 暗色主题）
- **vis-network** — 知识图谱可视化
- **Lucide React** / **React Hot Toast**

### 后端
- **FastAPI** + **SQLAlchemy 2.0** + **uvicorn**
- **SQLite**（DMS 主库）+ **PostgreSQL + pgvector**（知识库）
- **PyMuPDF**（PDF）/ **python-docx** + **mammoth**（Word）/ **ffmpeg**（音视频）
- **tiktoken**（切片）/ **httpx**（LLM/ASR 调用）

### AI 服务
- **LLM**：DeepSeek / OpenRouter / Anthropic（统一 `llm_provider.py` 抽象）
- **Embedding**：SiliconFlow Qwen3-Embedding-0.6B（独立端点）
- **Rerank**：qwen3-rerank
- **ASR**：智谱 GLM `glm-asr-2512`
- **OCR**：外部 PaddleOCR 服务

## 📁 项目结构

```
material-hub/
├── backend/
│   ├── main.py                  # FastAPI 入口
│   ├── dms_models.py            # DMS v2 数据模型(SQLite)
│   ├── dms_processor.py         # 文档处理主管道(OCR/ASR/docx/KB)
│   ├── dms_search.py            # FTS5 全文搜索
│   ├── dms_auth.py              # RBAC + 文件夹权限
│   ├── llm_provider.py          # 统一 LLM/Embedding 抽象
│   ├── ocr_agent.py             # LLM 信息提取 + 实体创建
│   ├── chat_tools.py            # Agent 工具定义(20+ 工具)
│   ├── # 知识库模块
│   ├── kb_database.py           # PostgreSQL 连接管理
│   ├── kb_models.py             # KB 表模型(chunks/events/entities)
│   ├── kb_chunking.py           # 文本切片(token 窗口 + 中文标题)
│   ├── kb_embedding.py          # 批量 embedding
│   ├── kb_ingest.py             # 文档入库管道
│   ├── kb_search.py             # 向量 + 混合搜索(RRF)
│   ├── kb_extraction.py         # LLM 事件/实体提取
│   ├── kb_entity_sync.py        # SQLite→PG 实体同步
│   ├── kb_event_ingest.py       # 事件存储 + 关联
│   ├── kb_graph.py              # 图谱 BFS 扩展
│   ├── kb_multihop.py           # 8 步多跳搜索管道
│   ├── kb_rerank.py             # Rerank 服务
│   ├── kb_asr.py                # GLM 语音转文字
│   ├── kb_docx.py               # Word 文本提取
│   └── routers/                 # API 路由(v2_*.py 为 DMS v2)
├── frontend/
│   ├── src/
│   │   ├── pages/               # 22 个页面
│   │   ├── components/
│   │   │   ├── KnowledgeGraphPanel.tsx   # 知识图谱可视化
│   │   │   ├── DocumentDetailPanel.tsx   # 文档详情(含图谱入口)
│   │   │   └── ...
│   │   ├── services/api-v2.ts   # DMS v2 + KB API
│   │   └── types/dms.ts         # 类型定义(含 KB)
├── mcp-server/
│   └── server.py                # FastMCP 服务(Agent 工具 + 文件夹权限)
├── .gitea/workflows/
│   └── ci-cd.yml                # Gitea CI/CD(check + deploy)
├── docker-compose.yml           # PostgreSQL + 前后端
└── .env.example
```

## 🚀 快速开始

### Docker（推荐）

```bash
git clone <repo>
cd material-hub
cp .env.example .env
# 编辑 .env: 配置 LLM API key、OCR 服务、PG、Embedding、ASR
docker-compose up -d
```

### 本地开发

```bash
# 后端(Python 3.10+)
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py          # :8201

# 前端
cd frontend
npm install
npm run dev             # :3100
```

### 便捷脚本

```bash
./start.sh    # 启动
./status.sh   # 状态
./stop.sh     # 停止
./restart.sh  # 重启
```

## ⚙️ 关键配置（.env）

```bash
# LLM(聊天 + 分类)
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxx

# Embedding(独立端点,推荐 SiliconFlow BGE/Qwen3)
EMBEDDING_BASE_URL=https://api.siliconflow.cn
EMBEDDING_API_KEY=sk-xxx
EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B
EMBEDDING_DIMENSIONS=1024

# 知识库 PostgreSQL
PG_HOST=localhost
PG_PORT=5433
PG_DATABASE=materialhub_kb
PG_USER=materialhub
PG_PASSWORD=materialhub

# OCR / ASR
OCR_SERVICE_URL=http://localhost:8010
ASR_API_KEY=<glm-key>
ASR_MODEL=glm-asr-2512
```

## 🤖 Agent 能力示例

聊天中直接用自然语言指挥 Agent：

```
用户: 恒远科技有哪些认证证书?签过什么合同?
Agent: [调 kb_graph_explore] → 展开恒远科技关系网
       [调 kb_deep_search]   → 多跳找关联文档
       → 返回: ISO 9001 + ISO 27001; 2份合同(智慧园区580万 + 智慧政务720万)
       → 内嵌渲染知识图谱

用户: 把这几个视频归类到培训资料文件夹
Agent: [调 create_folder]    → 创建 /公司资质/培训资料/
       [调 update_document]  → 批量归类
       [调 set_folder_mapping] → 绑定自动归档映射

用户: 哪些人做过培训?
Agent: [调 kb_deep_search mode=multihop] → 多跳推理
       → 刘杰(财务系统培训)、王芳(票据系统培训)...
```

## 🔌 MCP 集成

MaterialHub 通过 FastMCP 暴露工具给外部 LLM 客户端：

```json
// .mcp.json
{
  "materialhub": {
    "url": "http://10.0.0.2:8202/sse?token=mh-agent-xxx"
  }
}
```

- **只读 Token**：可搜索/查询，不可修改
- **导入 Token**：可上传/归类文档
- **文件夹隔离**：每个 Agent 只能看授权范围内的文档

## 🔧 CI/CD（Gitea Actions）

推送到 main 自动触发：

```
check  → 前端 tsc + build / 后端 pip + import 检查
deploy → git 同步 → Python 3.12 venv → npm build → launchd 重启 → 健康检查
```

详见 [`.gitea/workflows/ci-cd.yml`](.gitea/workflows/ci-cd.yml)。

## 📖 API 文档

启动后访问 Swagger UI：
```
http://localhost:8201/docs
```

核心端点：
- `GET /api/v2/search?mode=multihop` — 多跳知识图谱搜索
- `GET /api/v2/kb/entities/{name}/graph` — 实体关系图谱
- `POST /api/v2/upload/` — 全格式上传（PDF/图片/音频/视频/Word/TXT）
- `POST /api/v2/chat/stream` — Agent 流式对话

## 📝 许可证

MIT License. 详见 [LICENSE](LICENSE)。

---

**MaterialHub** — 从文档管理到知识推理 🚀
