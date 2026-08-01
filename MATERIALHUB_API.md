# MaterialHub API v2 文档

MaterialHub DMS (文档管理系统) 后端 API，基于 FastAPI 构建。

## 基础信息

- **默认端口**: 8201
- **基础URL**: `http://localhost:8201`
- **API 前缀**: `/api/v2/`（认证端点除外，使用 `/api/auth/`）
- **文档地址**:
  - Swagger UI: `http://localhost:8201/docs`
  - ReDoc: `http://localhost:8201/redoc`

## 认证

使用 Session-based Authentication。

### 认证端点 — `/api/auth`

**这些端点不受 `/api/v2/` 前缀影响，路径为 `/api/auth/...`**

#### POST /api/auth/login

```json
// Request
{"username": "admin", "password": "admin123"}

// Response
{"token": "a1b2c3d4...", "user": {"id": 1, "username": "admin", ...}, "expires_at": "..."}
```

#### POST /api/auth/logout — 需要 Bearer token

#### GET /api/auth/check — 需要 Bearer token

```json
{"valid": true, "user": {"id": 1, "username": "admin", ...}}
```

**默认管理员**: admin / admin123

---

## 健康检查

### GET /health

```json
{"status": "healthy", "service": "MaterialHub"}
```

---

## 文档管理

### 上传 — `POST /api/v2/upload/`

上传文件（PDF/DOCX/图片等），自动触发 OCR + 分类 + 实体抽取流水线。

**权限**: editor+

**请求**: `multipart/form-data`，字段 `file`

**响应**:
```json
{
  "doc_id": 42,
  "status": "pending",
  "message": "文件已接收，正在排队处理"
}
```

### 文档列表/搜索 — `GET /api/v2/documents`

**查询参数**:
- `status` — active/draft/expired/archived
- `doc_type_id` — 按文档类型筛选
- `folder_id` — 按文件夹筛选
- `entity_id` — 按关联实体筛选（即"某公司/人员的材料"）
- `q` — 关键词搜索

**响应**:
```json
{
  "results": [
    {
      "id": 1,
      "title": "营业执照",
      "status": "active",
      "doc_type": {"id": 1, "name": "营业执照", "code": "business-license"},
      "folder": {"id": 2, "name": "企业资质", "path": "/企业资质/营业执照"},
      "entities": [{"name": "XX科技有限公司", "type": "org", "role": "owner"}],
      "expiry_date": "2025-12-31",
      "created_at": "2026-02-18T10:00:00"
    }
  ],
  "total": 35,
  "limit": 30,
  "offset": 0
}
```

### 文档详情 — `GET /api/v2/documents/{doc_id}`

### 更新文档 — `PATCH /api/v2/documents/{doc_id}` — editor+

```json
// Request
{"title": "新标题", "status": "archived", "expiry_date": "2026-12-31"}
```

### 删除文档 — `DELETE /api/v2/documents/{doc_id}` — editor+

### 文档实体管理

- `POST /api/v2/documents/{doc_id}/entities/` — 关联实体 — editor+
- `DELETE /api/v2/documents/{doc_id}/entities/{entity_id}` — 取消关联 — editor+

### 文档标签

- `POST /api/v2/documents/{doc_id}/tags/` — 添加标签 — editor+
- `DELETE /api/v2/documents/{doc_id}/tags/{tag_id}` — 移除标签 — editor+

### 重处理 — `POST /api/v2/documents/actions/reprocess` — editor+

对已有文档重新执行 OCR + 分类 + 实体抽取流水线。

---

## 文件获取 — `GET /api/v2/files/{file_id}`

通过 DMS 文件记录 ID 获取原始文件。返回文件流。

Mock 文档图片: `GET /api/v2/mock/files/{filename}`

---

## 实体管理

实体统一了旧版的"公司"和"人员"概念。`entity_type` 为 `org` 表示组织/公司，`person` 表示人员。

### 列出实体 — `GET /api/v2/entities`

**查询参数**: `type` — org/person，`q` — 关键词

```json
{
  "results": [
    {
      "id": 1,
      "name": "XX科技有限公司",
      "entity_type": "org",
      "attributes": {"credit_code": "91110000..."},
      "document_count": 15
    }
  ]
}
```

### 实体详情 — `GET /api/v2/entities/{entity_id}`

### 创建/更新/删除实体 — editor+

- `POST /api/v2/entities/`
- `PATCH /api/v2/entities/{entity_id}`
- `DELETE /api/v2/entities/{entity_id}`

### 实体关系 — `GET /api/v2/entities/relations`

查询实体间关系（如雇佣、隶属等）。

---

## 聚合端点（投标场景）

一次性返回完整信息，避免多次 API 调用。

### 公司完整信息 — `GET /api/v2/companies/{entity_id}/complete`

```json
{
  "company": {"id": 1, "name": "琪信通达（北京）科技有限公司", ...},
  "employees": [{"id": 11, "name": "周杨", "position": "高级工程师", ...}],
  "materials": [{"id": 10, "title": "营业执照", "material_type": "license", ...}],
  "aggregated_info": {
    "registered_capital": "2001万元",
    "establishment_date": "2008-04-14",
    "company_type": "有限责任公司"
  },
  "statistics": {"total_materials": 74, "total_employees": 12}
}
```

### 人员完整信息 — `GET /api/v2/persons/{entity_id}/complete`

```json
{
  "person": {"id": 11, "name": "周杨", ...},
  "company": {"id": 1, "name": "琪信通达（北京）科技有限公司", ...},
  "materials": [{"id": 5, "title": "身份证", ...}],
  "aggregated_info": {"gender": "女", "birth_date": "2001-12-04", "age": 24, ...},
  "certificates": [{"title": "PMP认证", "cert_number": "PMI98765", "expiry_date": "2026-03-15"}],
  "statistics": {"total_materials": 8, "total_certificates": 2}
}
```

---

## 过期提醒 — `GET /api/v2/expiry`

```json
{
  "summary": {"total": 35, "expiring_30d": 3, "expired": 1},
  "expiring": [{"id": 5, "title": "ISO证书", "expiry_date": "2026-03-01", "days_remaining": 15}]
}
```

---

## Mock 文档生成 — `/api/v2/mock`

用于生成测试数据。

### 列出可 mock 类型 — `GET /api/v2/mock/types`

### 生成 Mock 文档 — `POST /api/v2/mock/generate` — editor+

```json
// Request
{"doc_type_code": "business-license", "entity_name": "XX科技有限公司", "person_name": "张三"}

// Response
{
  "success": true,
  "doc_type_code": "business-license",
  "mock_data": {"company_name": "XX科技有限公司", "legal_person": "张三", ...},
  "image_url": "/api/v2/mock/files/XX科技有限公司_business-license_20260801.png",
  "document_id": 42
}
```

---

## 设置 — `/api/v2/settings` — admin

管理系统配置（LLM provider、OCR、Embedding 等）。提供 test 端点验证连通性。

- `GET /api/v2/settings/` — 列出所有设置
- `PUT /api/v2/settings/batch` — 批量更新
- `POST /api/v2/settings/llm/test` — 测试 LLM 配置
- `POST /api/v2/settings/ocr/test` — 测试 OCR 配置
- `POST /api/v2/settings/embedding/test` — 测试 Embedding 配置

---

## 完整端点索引

| 模块 | 路径前缀 | 端点示例 |
|---|---|---|
| 认证 | `/api/auth/` | login, logout, check |
| 健康 | `/` | /health |
| 文档 | `/api/v2/documents/` | CRUD, entities, tags, revisions |
| 上传 | `/api/v2/upload/` | upload, process, queue |
| 文件 | `/api/v2/files/` | GET /{file_id} |
| 实体 | `/api/v2/entities/` | CRUD, relations |
| 搜索 | `/api/v2/search/` | 全文搜索 |
| 聚合 | `/api/v2/` | /companies/{id}/complete, /persons/{id}/complete |
| 过期 | `/api/v2/expiry/` | 过期提醒 |
| Mock | `/api/v2/mock/` | types, generate, files |
| 文件夹 | `/api/v2/folders/` | 文件夹树管理 |
| 文档类型 | `/api/v2/doc-types/` | 文档类型管理 |
| 标签 | `/api/v2/tags/` | 标签管理 |
| 设置 | `/api/v2/settings/` | 系统设置 + LLM/OCR/Embedding 测试 |
| 管理 | `/api/v2/admin/` | 用户、Agent、角色、迁移、审计 |
| 知识库 | `/api/v2/kb/` | 向量搜索、多跳推理、知识图谱 |
| 投标 | `/api/v2/bids/` | 投标需求分析 |

---

## 错误响应

| 状态码 | 含义 |
|---|---|
| 400 | 请求参数错误 |
| 401 | 未认证或会话过期 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 413 | 文件过大 |
| 422 | 数据验证失败 |
| 500 | 服务器内部错误 |

---

## 变更说明（v1 → v2）

| 旧版 (v1) | 新版 (v2) | 说明 |
|---|---|---|
| `/api/materials` | `/api/v2/documents` | 材料统一为文档模型 |
| `/api/companies` | `/api/v2/entities?type=org` | 公司统一为实体 |
| `/api/persons` | `/api/v2/entities?type=person` | 人员统一为实体 |
| `/api/documents` | `/api/v2/upload/` | 文档概念变为上传 |
| `/api/files/{filename}` | `/api/v2/files/{file_id}` | 通过文件记录 ID 获取 |
| `/api/materials/{id}/ocr` | `/api/v2/documents/actions/reprocess` | 统一为重处理 |
| `/api/companies/{id}/complete` | `/api/v2/companies/{id}/complete` | 路径变更 |
| `/api/persons/{id}/complete` | `/api/v2/persons/{id}/complete` | 路径变更 |
