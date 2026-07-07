# 智能材料导入系统

## 📋 功能概述

智能材料导入系统能够自动识别、分类和归档各类材料文件（图片、PDF、Word），大幅减少手工整理工作量。

### 核心能力

1. **多格式支持**
   - 图片：jpg, jpeg, png, bmp, tiff, gif
   - 文档：pdf, docx, doc

2. **智能识别**
   - 自动OCR识别文字
   - LLM智能分析材料类型和内容
   - 自动提取公司信息、人员信息、有效期等

3. **实体匹配**
   - 智能匹配已有公司（精确匹配、模糊匹配）
   - 自动关联人员信息
   - 避免重复创建

4. **版本管理**
   - 自动检测材料更新（续期、勘误）
   - 维护版本历史关系

5. **人工审核**
   - 置信度不足时加入审核队列
   - 提供智能建议供人工确认

## 🏗️ 系统架构

```
[用户上传文件]
    ↓
[FileProcessor] - 识别文件格式，提取文件名提示
    ↓
[ContentExtractor] - 提取文本内容（OCR/直接提取）
    ↓
[IntelligentAnalyzer] - LLM智能分析材料信息
    ↓
[EntityMatcher] - 匹配已有公司/人员实体
    ↓
置信度判断
    ↓              ↓
自动归档      待人工审核
```

## 📊 当前进度

### ✅ 已完成 (Phase 1 - Backend Core)

- [x] 多格式文件处理器
- [x] 内容提取器（图片OCR、PDF、Word）
- [x] LLM智能分析器
- [x] 实体匹配器（公司/人员）
- [x] 智能导入流水线
- [x] 待审核数据库模型
- [x] API路由基础框架

### 🚧 进行中 (Phase 2)

- [ ] 自动归档功能实现
- [ ] 版本检测逻辑完善
- [ ] 前端批量上传页面
- [ ] 前端审核队列界面

### 📅 计划中 (Phase 3+)

- [ ] 学习用户选择优化匹配
- [ ] 批量操作优化
- [ ] 异步任务队列
- [ ] 进度实时推送

## 🔌 API接口

### 1. 批量导入

```http
POST /api/smart-import/batch
Content-Type: multipart/form-data

files: [文件列表]
```

**响应示例：**
```json
{
  "total": 10,
  "auto_archived": 7,
  "pending_review": 2,
  "failed": 1,
  "items": [
    {
      "status": "auto_archived",
      "filename": "营业执照.pdf",
      "confidence": 0.95
    },
    {
      "status": "pending_review",
      "pending_id": 123,
      "filename": "资质证书.jpg",
      "confidence": 0.72,
      "message": "置信度不足，需人工审核"
    }
  ]
}
```

### 2. 获取待审核列表

```http
GET /api/smart-import/pending-reviews?status=pending&limit=50
```

**响应示例：**
```json
{
  "total": 5,
  "items": [
    {
      "id": 123,
      "filename": "资质证书.jpg",
      "confidence": 72,
      "status": "pending",
      "analysis": {
        "material_type": "qualification",
        "material_name": "建筑业企业资质证书",
        "company_info": {
          "name": "北京XX建设有限公司"
        }
      },
      "entities": {
        "company_match_type": "fuzzy_low",
        "alternatives": [
          {"company_id": 1, "company_name": "北京XX建设集团有限公司", "similarity": 0.85}
        ]
      }
    }
  ]
}
```

### 3. 批准审核

```http
POST /api/smart-import/pending-reviews/123/approve
Content-Type: application/json

{
  "company_id": 1,
  "material_type": "qualification",
  "expiry_date": "2026-12-31"
}
```

### 4. 拒绝审核

```http
POST /api/smart-import/pending-reviews/123/reject
Content-Type: application/json

{
  "reason": "图片模糊无法识别"
}
```

### 5. 获取导入统计

```http
GET /api/smart-import/stats
```

## 🧪 测试

```bash
cd backend
python test_smart_import.py
```

## ⚙️ 配置要求

### 必需配置

```env
# LLM Provider (智能分析必需)
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-your-api-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

### 可选配置

```env
# OCR服务（图片识别，可选但推荐）
OCR_SERVICE_URL=http://localhost:8010
OCR_TIMEOUT=120
```

## 📖 使用示例

### Python客户端示例

```python
import requests

# 批量上传文件
files = [
    ('files', open('营业执照.pdf', 'rb')),
    ('files', open('资质证书.jpg', 'rb')),
]

response = requests.post(
    'http://localhost:8201/api/smart-import/batch',
    files=files,
    headers={'Authorization': 'Bearer YOUR_TOKEN'}
)

result = response.json()
print(f"成功: {result['auto_archived']}, 待审核: {result['pending_review']}")

# 如果有待审核项，获取列表
if result['pending_review'] > 0:
    pending = requests.get(
        'http://localhost:8201/api/smart-import/pending-reviews',
        headers={'Authorization': 'Bearer YOUR_TOKEN'}
    ).json()

    for item in pending['items']:
        print(f"待审核: {item['filename']}, 置信度: {item['confidence']}%")
```

### cURL示例

```bash
# 批量上传
curl -X POST "http://localhost:8201/api/smart-import/batch" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "files=@营业执照.pdf" \
  -F "files=@资质证书.jpg"

# 获取待审核列表
curl "http://localhost:8201/api/smart-import/pending-reviews" \
  -H "Authorization: Bearer YOUR_TOKEN"

# 批准审核
curl -X POST "http://localhost:8201/api/smart-import/pending-reviews/123/approve" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"company_id": 1}'
```

## 🎯 典型使用流程

### 场景1：全自动导入（高置信度）

1. 用户批量上传文件
2. 系统自动识别、分类、归档
3. 用户在"材料"页面看到已归档的材料

### 场景2：人工审核流程（低置信度）

1. 用户批量上传文件
2. 系统识别后发现置信度不足
3. 材料进入待审核队列
4. 用户在审核界面：
   - 查看识别结果和建议
   - 修正错误信息
   - 选择匹配的公司
   - 批准归档
5. 系统完成归档

### 场景3：材料更新

1. 用户上传新版本营业执照
2. 系统识别出这是已有材料的更新
3. 提示用户：
   - 这是"北京XX公司"营业执照的续期版本
   - 旧版本有效期：2020-2023
   - 新版本有效期：2023-2026
4. 用户确认后，系统：
   - 创建新版本材料
   - 建立版本关系
   - 保留历史记录

## 🔍 智能匹配规则

### 公司匹配优先级

1. **精确匹配（置信度 1.0）**
   - 统一社会信用代码完全一致
   - 公司名称完全一致

2. **高度相似（置信度 0.95+）**
   - 名称相似度 > 95%
   - 自动匹配，无需人工确认

3. **低相似度（置信度 0.5-0.95）**
   - 名称相似度 80-95%
   - 提供候选列表，需人工选择

4. **新公司（置信度 0.7）**
   - 无匹配结果
   - 需人工确认后创建

### 人员匹配优先级

1. 身份证号精确匹配（置信度 1.0）
2. 姓名+公司匹配（置信度 0.9）
3. 姓名匹配（置信度 0.7，可能重名）
4. 新人员（置信度 0.6）

## 📝 数据库结构

### pending_reviews 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| file_path | String | 临时文件路径 |
| filename | String | 原始文件名 |
| file_type | String | image/document |
| analysis_json | String | LLM分析结果（JSON） |
| entities_json | String | 实体匹配结果（JSON） |
| confidence | Integer | 置信度（0-100） |
| status | String | pending/approved/rejected |
| created_at | DateTime | 创建时间 |
| reviewed_at | DateTime | 审核时间 |

### material_versions 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| material_id | Integer | 当前材料ID |
| previous_material_id | Integer | 前一版本材料ID |
| relation_type | String | renewal/correction/upgrade |
| created_at | DateTime | 创建时间 |

## 🐛 故障排查

### 问题：LLM分析失败

**可能原因：**
- LLM API未配置或配置错误
- API额度不足
- 网络连接问题

**解决方法：**
```bash
# 检查配置
echo $DEEPSEEK_API_KEY

# 测试LLM连接
cd backend
python -c "from llm_provider import get_llm_provider; llm = get_llm_provider(); print(llm.chat('测试'))"
```

### 问题：OCR识别失败

**可能原因：**
- OCR服务未启动
- 图片质量过低

**解决方法：**
```bash
# 检查OCR服务
curl http://localhost:8010/health

# 查看日志
tail -f backend.log | grep OCR
```

### 问题：文件上传失败

**可能原因：**
- 文件过大
- 格式不支持

**解决方法：**
- 检查文件大小限制
- 确认文件格式在支持列表中

## 🚀 下一步开发

1. **完善自动归档功能**
   - 实现材料自动创建
   - 实现版本管理逻辑
   - 优化文件存储

2. **前端界面开发**
   - 批量上传页面（拖拽上传）
   - 审核队列页面（可视化审核）
   - 实时进度显示

3. **性能优化**
   - 异步处理大文件
   - 批量操作优化
   - 缓存机制

4. **学习能力**
   - 记录用户选择
   - 优化匹配算法
   - 个性化建议

## 📞 联系方式

如有问题或建议，请提交Issue。

---

**MaterialHub Smart Import** - 让材料导入更智能 🚀
