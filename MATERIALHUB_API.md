# MaterialHub API 文档

MaterialHub 后端API文档，基于FastAPI构建。

## 基础信息

- **默认端口**: 8201
- **基础URL**: `http://localhost:8201`
- **文档地址**:
  - Swagger UI: `http://localhost:8201/docs`
  - ReDoc: `http://localhost:8201/redoc`

## 环境变量

```bash
# 数据库
DB_PATH=data/materials.db

# 服务器
HOST=0.0.0.0
PORT=8201

# OCR服务
OCR_SERVICE_URL=http://localhost:8010
OCR_TIMEOUT=120

# LLM配置
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your-api-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

---

## 健康检查

### GET /health

检查服务健康状态。

**响应**:
```json
{
  "status": "healthy",
  "service": "MaterialHub"
}
```

---

## 文档管理 (/api/documents)

### 1. 上传文档

**POST** `/api/documents`

上传DOCX文档，自动提取图片并创建材料记录。

**请求**:
- Content-Type: `multipart/form-data`
- Body: `file` (DOCX文件)

**响应**:
```json
{
  "document_id": 1,
  "filename": "响应文件.docx",
  "section_count": 15,
  "image_count": 185,
  "materials": [
    {
      "id": 1,
      "document_id": 1,
      "source_filename": "响应文件.docx",
      "section": "资质材料",
      "title": "营业执照",
      "heading_level": 2,
      "image_filename": "营业执照.png",
      "image_url": "/api/materials/1/image",
      "file_size": 123456,
      "expiry_date": null,
      "is_expired": null,
      "created_at": "2026-02-18T10:00:00"
    }
  ]
}
```

**说明**:
- 自动提取DOCX中的图片
- 根据标题层级自动分类
- 支持自动检测有效期
- 上传后触发后台OCR处理

---

### 2. 列出文档

**GET** `/api/documents`

获取所有上传的文档列表。

**响应**:
```json
{
  "documents": [
    {
      "id": 1,
      "filename": "响应文件.docx",
      "upload_time": "2026-02-18T10:00:00",
      "section_count": 15,
      "image_count": 185
    }
  ]
}
```

---

### 3. 删除文档

**DELETE** `/api/documents/{document_id}`

删除指定文档及其所有材料。

**响应**:
```json
{
  "message": "Document 1 deleted"
}
```

---

## 材料管理 (/api/materials)

### 1. 搜索材料

**GET** `/api/materials`

搜索和筛选材料。

**查询参数**:
- `q` (可选): 搜索关键词
- `document_id` (可选): 文档ID
- `status` (可选): 过期状态
  - `valid`: 有效期内
  - `expired`: 已过期
  - `all`: 全部

**响应**:
```json
{
  "results": [
    {
      "id": 1,
      "document_id": 1,
      "company_id": 1,
      "person_id": null,
      "source_filename": "响应文件.docx",
      "section": "资质材料",
      "title": "营业执照",
      "heading_level": 2,
      "image_filename": "营业执照.png",
      "image_url": "/api/materials/1/image",
      "file_size": 123456,
      "expiry_date": "2025-12-31",
      "is_expired": false,
      "material_type": "license",
      "ocr_text": "营业执照OCR文本...",
      "extracted_data": {
        "company_name": "XXX公司",
        "credit_code": "91110000...",
        "legal_person": "张三"
      },
      "ocr_status": "completed",
      "ocr_error": null,
      "ocr_processed_at": "2026-02-18T10:05:00",
      "created_at": "2026-02-18T10:00:00"
    }
  ]
}
```

---

### 2. 获取材料详情

**GET** `/api/materials/{material_id}`

获取单个材料的详细信息。

**响应**: 同上materials对象

---

### 3. 更新材料

**PATCH** `/api/materials/{material_id}`

更新材料信息。

**请求体**:
```json
{
  "title": "新标题",
  "section": "新分类",
  "expiry_date": "2025-12-31",
  "company_id": 1,
  "person_id": null
}
```

**响应**: 更新后的材料对象

---

### 4. 删除材料

**DELETE** `/api/materials/{material_id}`

删除指定材料。

**响应**:
```json
{
  "message": "Material 1 deleted"
}
```

---

### 5. 获取材料图片

**GET** `/api/materials/{material_id}/image`

获取材料的原始图片文件。

**响应**: 图片文件 (image/png 或 image/jpeg)

---

### 6. 触发OCR识别

**POST** `/api/materials/{material_id}/ocr`

手动触发材料的OCR识别。

**响应**:
```json
{
  "status": "processing",
  "message": "OCR processing started in background",
  "material_id": 1
}
```

**OCR状态**:
- `pending`: 等待处理
- `processing`: 处理中
- `completed`: 已完成
- `failed`: 失败

---

### 7. 获取OCR结果

**GET** `/api/materials/{material_id}/ocr`

获取材料的OCR识别结果。

**响应**:
```json
{
  "status": "completed",
  "ocr_text": "识别的文本内容...",
  "extracted_data": {
    "material_type": "license",
    "confidence": 0.95,
    "extracted_data": {
      "company_name": "XXX公司",
      "credit_code": "91110000..."
    }
  },
  "material_type": "license",
  "error": null,
  "processed_at": "2026-02-18T10:05:00"
}
```

---

## 公司管理 (/api/companies)

### 1. 列出公司

**GET** `/api/companies`

获取所有公司列表（含材料统计）。

**响应**:
```json
{
  "companies": [
    {
      "id": 1,
      "name": "XXX科技有限公司",
      "legal_person": "张三",
      "credit_code": "91110000...",
      "address": "北京市海淀区...",
      "created_at": "2026-02-18T10:00:00",
      "updated_at": "2026-02-18T10:00:00",
      "document_count": 2,
      "material_count": 15
    }
  ]
}
```

---

### 2. 获取公司详情

**GET** `/api/companies/{company_id}`

获取单个公司的详细信息。

**响应**: 同上company对象

---

### 3. 获取公司材料

**GET** `/api/companies/{company_id}/materials`

获取公司关联的所有材料。

**响应**:
```json
{
  "company": {
    "id": 1,
    "name": "XXX科技有限公司",
    ...
  },
  "materials": [
    {
      "id": 1,
      "title": "营业执照",
      ...
    }
  ]
}
```

---

## 人员管理 (/api/persons)

### 1. 列出人员

**GET** `/api/persons`

获取所有人员列表（含材料统计）。

**查询参数**:
- `company_id` (可选): 按公司筛选

**响应**:
```json
{
  "persons": [
    {
      "id": 1,
      "name": "张三",
      "id_number": "110101199001011234",
      "education": "本科",
      "position": "项目经理",
      "company_id": 1,
      "created_at": "2026-02-18T10:00:00",
      "updated_at": "2026-02-18T10:00:00",
      "material_count": 6
    }
  ]
}
```

---

### 2. 获取人员详情

**GET** `/api/persons/{person_id}`

获取单个人员的详细信息。

**响应**: 同上person对象

---

### 3. 获取人员材料

**GET** `/api/persons/{person_id}/materials`

获取人员关联的所有材料。

**响应**:
```json
{
  "person": {
    "id": 1,
    "name": "张三",
    ...
  },
  "materials": [
    {
      "id": 1,
      "title": "身份证",
      ...
    }
  ]
}
```

---

## 材料关联

### 关联到公司

**PATCH** `/api/materials/{material_id}`
```json
{
  "company_id": 1
}
```

### 关联到人员

**PATCH** `/api/materials/{material_id}`
```json
{
  "person_id": 1
}
```

### 取消关联

**PATCH** `/api/materials/{material_id}`
```json
{
  "company_id": null,
  "person_id": null
}
```

---

## 材料类型

系统自动识别的材料类型：

### 公司材料
- `license`: 营业执照
- `legal_person_cert`: 法定代表人证明
- `qualification`: 资质证书
- `iso_cert`: ISO认证证书
- `certificate`: 其他证书

### 个人材料
- `id_card`: 身份证
- `education`: 学历证书
- `degree`: 学位证书
- `certificate`: 职业证书
- `qualification`: 资格证书

### 其他
- `other`: 其他材料

---

## 错误响应

所有端点可能返回的错误：

| 状态码 | 说明 |
|--------|------|
| 400 | 请求参数错误 |
| 404 | 资源不存在 |
| 413 | 文件过大 |
| 422 | 数据验证失败 |
| 500 | 服务器内部错误 |

**错误响应示例**:
```json
{
  "detail": "Material not found"
}
```

---

## OCR自动处理流程

1. **上传文档** → 自动提取图片并创建材料
2. **后台OCR处理** → 自动触发OCR识别（可配置）
3. **信息提取** → 使用LLM提取结构化信息
4. **智能关联** → 自动创建公司/人员并关联材料
5. **有效期提醒** → 自动检测和标记过期状态

---

## 批量操作示例

### 批量触发OCR
```bash
# 为所有材料触发OCR
for i in {1..185}; do
  curl -X POST http://localhost:8201/api/materials/$i/ocr
  sleep 1
done
```

### 批量更新有效期
```bash
curl -X PATCH http://localhost:8201/api/materials/1 \
  -H "Content-Type: application/json" \
  -d '{"expiry_date": "2025-12-31"}'
```

---

## 开发指南

### 启动服务
```bash
# 宿主机环境
./start.sh

# Docker环境
docker-compose up -d
```

### 查看日志
```bash
# 宿主机
tail -f backend.log

# Docker
docker-compose logs -f backend
```

### 调试技巧
```bash
# 直接访问API文档
open http://localhost:8201/docs

# 测试健康检查
curl http://localhost:8201/health

# 查看数据库
cd backend
source venv/bin/activate
python -c "from database import *; # your code"
```

---

## 性能优化

1. **批量处理**: OCR处理使用后台线程，不阻塞API响应
2. **缓存策略**: OCR结果存储在数据库中，避免重复处理
3. **智能筛选**: LLM预筛选减少不必要的OCR调用
4. **图片优化**: 自动调整图片大小以提高处理速度

---

## 安全注意事项

1. **文件验证**: 上传文件类型和大小限制
2. **路径安全**: 防止路径遍历攻击
3. **SQL注入**: 使用ORM防止SQL注入
4. **API限流**: 建议在生产环境添加限流
5. **认证授权**: 当前未实现，生产环境需添加

---

## 相关文档

- [宿主机开发指南](HOST_DEVELOPMENT.md)
- [OCR功能说明](OCR_FEATURE.md)
- [OCR服务API](api.md)
- [Docker配置](docker-compose.yml)
