# 智能导入系统测试指南

## 🎯 测试准备

### 1. 环境要求

```bash
# 必需配置
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-your-api-key

# 可选配置（增强功能）
OCR_SERVICE_URL=http://localhost:8010
```

### 2. 安装依赖

```bash
# 后端
cd backend
pip install -r requirements.txt

# 前端
cd frontend
npm install
```

### 3. 启动服务

```bash
# 方式1：使用启动脚本
./start.sh

# 方式2：手动启动
# 终端1 - 后端
cd backend
python main.py

# 终端2 - 前端
cd frontend
npm run dev
```

## 📋 测试场景

### 场景1：自动归档测试（高置信度）

**目标**: 测试系统能否自动识别和归档标准格式的材料

**测试步骤**:
1. 准备测试文件（建议使用清晰的扫描件）:
   - `北京琪信通达科技有限公司-营业执照.pdf`
   - `ISO9001认证证书.jpg`

2. 访问前端: `http://localhost:5173`

3. 登录系统（默认账号: admin / admin123）

4. 点击导航栏 "智能导入" 按钮

5. 拖拽或选择准备好的文件

6. 点击 "开始智能导入"

7. 观察处理结果

**预期结果**:
- ✅ 文件名清晰、内容规范的材料应显示为 "自动归档"
- ✅ 置信度应 >= 85%
- ✅ 在 "素材" 页面能看到新归档的材料
- ✅ 材料已关联到正确的公司

**验证点**:
```bash
# 检查数据库
sqlite3 data/materials.db "SELECT id, title, material_type, company_id FROM materials ORDER BY id DESC LIMIT 5;"

# 检查文件存储
ls -lh data/files/
ls -lh data/images/
```

---

### 场景2：人工审核测试（低置信度）

**目标**: 测试待审核队列和人工确认流程

**测试步骤**:
1. 准备模糊或非标准格式的测试文件:
   - 手机拍照的证书照片
   - 文件名不规范的材料

2. 上传文件到 "智能导入"

3. 观察处理结果 - 应显示 "待审核"

4. 点击 "审核队列" 按钮

5. 在左侧队列中选择待审核项

6. 查看右侧识别结果:
   - 文件预览
   - 材料类型
   - 公司匹配结果
   - 提取的信息

7. 如需修正:
   - 修改材料类型
   - 选择正确的公司匹配
   - 调整有效期

8. 点击 "确认归档"

**预期结果**:
- ✅ 低置信度材料进入审核队列
- ✅ 能看到文件预览
- ✅ 能看到LLM识别的结果
- ✅ 可以修正错误信息
- ✅ 批准后材料正确归档

---

### 场景3：公司智能匹配测试

**目标**: 测试公司名称的模糊匹配功能

**准备工作**:
```bash
# 先创建一个测试公司
sqlite3 data/materials.db <<EOF
INSERT INTO companies (name, legal_person, credit_code, created_at, updated_at)
VALUES ('北京测试科技有限公司', '张三', '91110108MA01TEST01', datetime('now'), datetime('now'));
EOF
```

**测试用例**:

| 文件名 | 公司名变体 | 预期匹配 |
|--------|-----------|----------|
| 测试1.pdf | 北京测试科技有限公司 | 精确匹配 |
| 测试2.pdf | 北京测试科技公司 | 高度相似 |
| 测试3.pdf | 测试科技有限公司 | 低相似（需审核） |
| 测试4.pdf | 北京全新科技有限公司 | 新公司 |

**验证方法**:
- 上传包含不同公司名变体的材料
- 观察系统的匹配结果
- 检查置信度分数

---

### 场景4：批量导入测试

**目标**: 测试系统处理大量文件的能力

**测试步骤**:
1. 准备10-20个不同类型的文件

2. 一次性拖拽所有文件到上传区

3. 点击 "开始智能导入"

4. 观察处理进度和结果统计

**预期结果**:
- ✅ 显示处理进度
- ✅ 统计结果准确:
  - X 个自动归档
  - Y 个待审核
  - Z 个失败
- ✅ 能查看每个文件的详细结果

---

### 场景5：多种文件格式测试

**测试文件格式**:
- ✅ JPG/JPEG 图片
- ✅ PNG 图片
- ✅ PDF 文档（文本型）
- ✅ PDF 文档（扫描型）
- ✅ DOCX Word文档

**测试方法**:
每种格式各上传1-2个文件，验证:
- 能正确识别文件类型
- 能提取文本内容
- 能进行智能分析

---

### 场景6：错误处理测试

**测试用例**:

1. **无效文件格式**
   - 上传 `.txt` 或 `.xlsx` 文件
   - 预期: 友好的错误提示

2. **超大文件**
   - 上传 > 50MB 的文件
   - 预期: 大小限制提示

3. **损坏的文件**
   - 上传损坏的PDF
   - 预期: 处理失败，显示错误信息

4. **网络中断**
   - 上传过程中断开网络
   - 预期: 超时提示或重试机制

---

## 🔍 测试检查清单

### 后端测试

```bash
# 1. 测试文件处理器
cd backend
python test_smart_import.py

# 2. 查看日志
tail -f backend.log | grep "smart_import"

# 3. 检查数据库
sqlite3 data/materials.db <<EOF
.tables
SELECT * FROM pending_reviews;
SELECT * FROM materials ORDER BY created_at DESC LIMIT 5;
EOF

# 4. 检查临时文件清理
ls -lh data/temp/
```

### 前端测试

```bash
# 1. 检查控制台错误
# 打开浏览器开发者工具 -> Console

# 2. 检查网络请求
# 打开 Network 标签，观察API调用

# 3. 测试响应式布局
# 调整浏览器窗口大小
```

### API测试

```bash
TOKEN="your-token-here"

# 1. 测试批量导入API
curl -X POST "http://localhost:8201/api/smart-import/batch" \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@test1.pdf" \
  -F "files=@test2.jpg"

# 2. 获取待审核列表
curl "http://localhost:8201/api/smart-import/pending-reviews" \
  -H "Authorization: Bearer $TOKEN"

# 3. 获取统计信息
curl "http://localhost:8201/api/smart-import/stats" \
  -H "Authorization: Bearer $TOKEN"

# 4. 批准审核
curl -X POST "http://localhost:8201/api/smart-import/pending-reviews/1/approve" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"company_id": 1}'
```

---

## 📊 性能测试

### 1. 响应时间测试

| 操作 | 文件数 | 预期时间 |
|------|--------|---------|
| 单文件上传 | 1 | < 10秒 |
| 小批量上传 | 5 | < 30秒 |
| 中批量上传 | 20 | < 2分钟 |
| 大批量上传 | 50 | < 5分钟 |

### 2. 并发测试

```bash
# 使用 ab (Apache Bench) 测试
ab -n 10 -c 2 -T 'multipart/form-data; boundary=----WebKitFormBoundary' \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost:8201/api/smart-import/batch
```

---

## 🐛 常见问题排查

### 问题1: LLM分析失败

**症状**: 所有文件都标记为 "未知类型"

**排查步骤**:
```bash
# 1. 检查环境变量
echo $DEEPSEEK_API_KEY

# 2. 测试LLM连接
cd backend
python -c "
from llm_provider import get_llm_provider
llm = get_llm_provider()
print(llm.chat('测试连接'))
"

# 3. 查看错误日志
grep "LLM" backend.log
```

---

### 问题2: OCR识别失败

**症状**: 图片无法提取文字

**排查步骤**:
```bash
# 1. 检查OCR服务
curl http://localhost:8010/health

# 2. 手动测试OCR
cd backend
python -c "
from ocr_client import ocr_image, check_ocr_service
print('OCR可用:', check_ocr_service())
result = ocr_image('test.jpg')
print('结果:', result[:100])
"
```

---

### 问题3: 文件无法预览

**症状**: 审核队列中文件预览显示404

**排查步骤**:
```bash
# 1. 检查临时文件目录
ls -lh data/temp/

# 2. 检查文件权限
ls -la data/temp/*.pdf

# 3. 查看API日志
grep "preview" backend.log
```

---

## ✅ 验收标准

### 功能完整性
- [ ] 支持图片、PDF、Word等多种格式
- [ ] LLM智能分析材料类型和内容
- [ ] 公司/人员智能匹配
- [ ] 高置信度自动归档
- [ ] 低置信度人工审核
- [ ] 批量上传处理
- [ ] 审核队列管理

### 用户体验
- [ ] 界面友好，操作直观
- [ ] 拖拽上传流畅
- [ ] 处理进度清晰
- [ ] 错误提示明确
- [ ] 响应速度快（< 10秒/文件）

### 数据准确性
- [ ] 公司名称识别准确率 > 90%
- [ ] 材料类型识别准确率 > 85%
- [ ] 有效期提取准确率 > 80%
- [ ] 无数据丢失或重复

### 稳定性
- [ ] 连续处理100个文件不崩溃
- [ ] 网络异常能友好处理
- [ ] 文件格式错误能捕获
- [ ] 临时文件正确清理

---

## 📝 测试报告模板

```markdown
# 智能导入系统测试报告

**测试日期**: YYYY-MM-DD
**测试人员**: XXX
**测试环境**: 开发/生产

## 测试结果概览
- 测试场景数: X
- 通过场景数: Y
- 失败场景数: Z
- 通过率: Y/X

## 详细测试结果

### 场景1: 自动归档测试
- 状态: ✅ 通过 / ❌ 失败
- 测试文件: 10个
- 自动归档: 8个
- 待审核: 2个
- 失败: 0个
- 问题: 无 / XXX

### 场景2: ...

## 发现的问题
1. [严重] XXX
2. [一般] XXX

## 改进建议
1. XXX
2. XXX

## 结论
系统功能基本完整，建议进入生产环境 / 需要修复XXX后再测试
```

---

## 🎓 最佳实践

1. **渐进式测试**: 先单文件 → 小批量 → 大批量
2. **准备测试数据集**: 提前准备各类材料的标准样本
3. **记录测试用例**: 建立可重复的测试用例库
4. **自动化测试**: 编写自动化脚本定期回归测试
5. **性能基准**: 记录性能数据，监控变化

---

**Happy Testing!** 🚀
