# 数据模型迁移计划

## 背景与目标

MaterialHub 正处于从**旧版扁平化 Material 数据模型**向**DMS v2 规范化模型**的迁移过程中。两套模型共存于同一个 SQLite 文件，新旧 API 路由并行运行。

**迁移目标：**
- 消除双模型维护负担，全面切换到 DMS v2
- 保留所有历史数据（含 OCR 结果、版本历史、人员-公司关联）
- 不中断线上服务（可回滚、分阶段执行）

---

## 当前状态：旧表 → 新表映射总览

| 旧表 | 新表 | 迁移状态 | 关键缺口 |
|---|---|---|---|
| `users` | ❌ 无对应 | **未迁移** | 认证系统完全驻留旧模型 |
| `sessions` | ❌ 无对应 | **未迁移** | Token 管理无 DMS 等价物 |
| `companies` | `dms_entities` (org) | 部分完成（`v2_migrate`） | `credit_code` 降级为 JSON blob，无法 SQL 过滤 |
| `persons` | `dms_entities` (person) | 部分完成（`v2_migrate`） | `company_id`（雇员关系）**完全丢失** |
| `documents` | ❌ 无对应 | **未迁移** | 原始 .docx 容器概念被抛弃 |
| `materials` | `dms_documents` + `dms_revisions` + `dms_files` | 部分完成（`v2_migrate`） | ocr_text、extracted_json、section 均丢失 |
| `pending_reviews` | ❌ 无对应 | **未迁移** | 整个人工审核队列无 DMS 等价物 |
| `material_versions` | `dms_revisions`（概念对应） | **未迁移** | 版本链、relation_type、replaced_at 全部丢失 |

---

## 迁移分阶段计划

### 阶段 0：准备与加固（当前基础工作）

**目标：** 在不改变任何业务逻辑的情况下，消除迁移中最危险的隐患。

**任务清单：**

- [ ] **0-1** 在 `v2_migrate.py` 的 `POST /materials` 迁移中，补充对 `material.section` 的处理——按 section 关键字映射到 DMS 文件夹（见下方字段映射细节），避免所有迁移文档 `folder_id=null`
- [ ] **0-2** 在 `v2_migrate.py` 的 `POST /materials` 中，将 `ocr_text`、`extracted_json`、`ocr_status` 写入 `DmsDocument.meta_json` 的 `_legacy_ocr` 键，防止 OCR 数据在迁移时丢失
- [ ] **0-3** 在 `v2_migrate.py` 的 `POST /persons` 中，补充将 `person.company_id` 写入 `Entity.attributes` JSON 的 `legacy_company_id` 键，为后续关系重建保留线索
- [ ] **0-4** 在 `v2_migrate.py` 中新增 `POST /material-versions` 端点，将 `material_versions` 迁移为 `dms_revisions`（见字段映射细节）
- [ ] **0-5** 在 `v2_migrate.py` 中新增迁移状态字段 `legacy_material_id` 到 `dms_documents.meta_json._legacy_id`，建立新旧 ID 的对应关系
- [ ] **0-6** 在 `dms_entities` 表中为 `credit_code` 新增独立列，方便精确匹配

```sql
ALTER TABLE dms_entities ADD COLUMN credit_code TEXT;
ALTER TABLE dms_entities ADD COLUMN company_id_legacy INTEGER;
CREATE INDEX idx_entities_credit_code ON dms_entities(credit_code);
```

- [ ] **0-7** 为现有迁移脚本添加幂等性保护：对 `file_hash IS NULL` 的 materials，改用 `(legacy_material_id in meta_json)` 做去重检查

**验收标准：**
- `GET /api/v2/admin/migrate/status` 返回的计数包含 material_versions
- 重复执行迁移不产生重复数据

**预估工作量：** 3～4 天

---

### 阶段 1：认证系统迁移（高优先级）

**目标：** 将 `users`/`sessions` 从旧模型独立出来，使 DMS v2 可以完全脱离 `database.py` 进行认证。

**任务清单：**

- [ ] **1-1** 在 `dms_models.py` 新增 `DmsUser` 和 `DmsSession` 模型

```python
class DmsUser(DmsBase):
    __tablename__ = "dms_users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, nullable=False, unique=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="editor")  # admin/editor/viewer
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    legacy_user_id = Column(Integer, nullable=True)  # 旧 users.id 对应关系

class DmsSession(DmsBase):
    __tablename__ = "dms_sessions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("dms_users.id"), nullable=False)
    token = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
```

- [ ] **1-2** 在 `v2_migrate.py` 新增 `POST /users` 端点，将 `users` → `dms_users`（含 `legacy_user_id` 对应）
- [ ] **1-3** 新建 `backend/routers/v2_auth.py`，实现 `/api/v2/auth/login`、`/logout`、`/check`，读取 `dms_users`/`dms_sessions`
- [ ] **1-4** 将 `v2_admin.py` 中的 `User` 引用替换为 `DmsUser`，切换到 DMS session
- [ ] **1-5** 前端 `services/auth.ts` 和 `App.tsx` 中的 `checkAuth`/`logout` 改为调用 `/api/v2/auth/*`（在旧路由下线前保持两者并存）
- [ ] **1-6** 双写过渡期（2周）：登录同时写入 `sessions`（旧）和 `dms_sessions`（新），验证无误后移除旧表写入

**验收标准：**
- 新旧登录接口均可正常验证 token
- `v2_admin.py` 的用户管理接口不再 import `database.py`

**预估工作量：** 3～5 天

---

### 阶段 2：人员-公司关系重建

**目标：** 恢复迁移中丢失的员工归属关系。

**任务清单：**

- [ ] **2-1** 在 `dms_models.py` 新增 `EntityRelation` 表，表达实体间关系（雇佣、归属等）

```sql
CREATE TABLE IF NOT EXISTS dms_entity_relations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id    INTEGER NOT NULL REFERENCES dms_entities(id),
    to_id      INTEGER NOT NULL REFERENCES dms_entities(id),
    relation   TEXT NOT NULL,   -- employed_by / subsidiary_of
    attributes TEXT,            -- JSON 附加信息
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(from_id, to_id, relation)
);
CREATE INDEX idx_entity_rel_from ON dms_entity_relations(from_id);
CREATE INDEX idx_entity_rel_to   ON dms_entity_relations(to_id);
```

- [ ] **2-2** 在 `v2_migrate.py` 新增 `POST /entity-relations` 端点：读取 `persons.company_id`，通过 `legacy_company_id` 反查 `dms_entities` 后插入 `dms_entity_relations`（relation="employed_by"）
- [ ] **2-3** 更新 `GET /api/v2/entities/{id}` 返回 `relations` 字段
- [ ] **2-4** 更新 MCP 工具 `get_person_complete` 和 `get_company_complete` 使用新关系表

**验收标准：**
- `GET /api/v2/entities/{person_id}` 返回包含所属公司的 `relations` 列表
- MCP `get_person_complete` 返回 `company` 字段不为空

**预估工作量：** 2～3 天

---

### 阶段 3：智能导入管线迁移（最大工作量）

**目标：** 将 `smart_import.py` 的 PendingReview 工作流迁移到 DMS v2，使 `SmartUploadPage` 和 `ReviewQueuePage` 完全脱离旧模型。

**背景：** 当前旧版 smart-import 和 DMS v2 upload 是两套并行的上传管线：
- 旧版：`POST /api/smart-import/single` → `PendingReview` 表 → 人工审核 → `Material`/`Document` 表
- 新版：`POST /api/v2/upload/` → `DmsDocument`(draft) → 人工审核 → active

两者功能高度重叠，需要将旧版的独特能力（PDF 旋转、页面选择、批量导入）合并入新版管线。

**任务清单：**

- [ ] **3-1** 在 `v2_upload.py` 补充 `POST /api/v2/upload/process/{doc_id}/rotate` 端点（复用 smart_import 中的 PyMuPDF 旋转逻辑）
- [ ] **3-2** 在 `v2_upload.py` 补充 `POST /api/v2/upload/batch` 端点，支持多文件批量上传（复用 `SmartImportPipeline.process_single_file` 中的循环逻辑）
- [ ] **3-3** 在 `v2_upload.py` 的 `GET /api/v2/upload/process/{doc_id}/page/{page_num}/thumb` 端点中增加旋转参数支持
- [ ] **3-4** 前端 `pages/SmartUploadPage.tsx` 改为调用 `api-v2.ts` 的上传管线接口
- [ ] **3-5** 前端 `pages/ReviewQueuePage.tsx` 改为调用 `api-v2.ts` 的 `getUploadQueue`、`approveUpload`、`rejectUpload`
- [ ] **3-6** 前端 `components/PdfPageSelector.tsx` 改用 v2 缩略图接口
- [ ] **3-7** 将 `PendingReview` 表中 status=pending 的历史记录迁移到 DMS draft 文档（仅迁移文件存在的记录）
- [ ] **3-8** 下线 `routers/smart_import.py` 和 `smart_import.py`（需等 3-4、3-5、3-6 完成并验证后）

**验收标准：**
- `SmartUploadPage` 和 `ReviewQueuePage` 不再 import `api.ts` 中的任何 smart-import 函数
- 单文件上传、PDF 页面选择、人工审核批准/拒绝全流程在 v2 管线测试通过

**预估工作量：** 7～10 天

---

### 阶段 4：Material/Company/Person 前端切换

**目标：** 将剩余前端页面从旧版 `/api/materials`、`/api/companies`、`/api/persons` 切换到 v2 等价接口。

**前端改动清单：**

| 文件 | 当前依赖 | 目标接口 |
|---|---|---|
| `pages/CompaniesPage.tsx` | `listCompanies()` → `/api/companies` | `listEntities({type:'org'})` → `/api/v2/entities` |
| `pages/PersonsPage.tsx` | `listPersons()` → `/api/persons` | `listEntities({type:'person'})` → `/api/v2/entities` |
| `pages/HomePage.tsx` | `/api/companies`, `/api/persons`, `/api/companies/{id}/materials` | `/api/v2/entities`, `/api/v2/documents?entity_id=X` |
| `pages/BrowsePage.tsx` | `useMaterials` hook，`/api/materials`, `/api/companies` | `/api/v2/documents`, `/api/v2/entities` |
| `hooks/useMaterials.ts` | `searchMaterials`, `updateMaterial`, `deleteMaterial` | `/api/v2/documents` 等价接口 |
| `components/CompanyDetailModal.tsx` | `getCompanyMaterials`, `triggerOCR` | `/api/v2/documents?entity_id=X`, `/api/v2/documents/actions/reprocess` |
| `components/PersonDetailModal.tsx` | `getPersonMaterials`, `updatePerson` | `/api/v2/documents?entity_id=X`, `PATCH /api/v2/entities/{id}` |
| `components/MaterialPicker.tsx` | `searchMaterials` → `/api/materials` | `searchDocuments` → `/api/v2/search` |
| `pages/UploadPage.tsx` | `uploadDocument`, `uploadSingleImage` | 已有 `UploadPageV2.tsx`，直接替换页面引用即可 |

**任务清单：**

- [ ] **4-1** 在 `api-v2.ts` 补充 `getEntityDocuments(entityId)` 函数，封装 `GET /api/v2/documents?entity_id=X`
- [ ] **4-2** 重写 `CompaniesPage` 和 `PersonsPage`，使用 `listEntities`
- [ ] **4-3** 重写 `CompanyDetailModal` 和 `PersonDetailModal`，使用 v2 接口
- [ ] **4-4** 重写 `useMaterials.ts` hook，改用 v2 document 接口，或直接内联到各消费页面
- [ ] **4-5** 在 `App.tsx` 中将 `UploadPage` 路由替换为 `UploadPageV2`
- [ ] **4-6** 删除 `pages/UploadPage.tsx`（旧版已被 v2 supersede）
- [ ] **4-7** 确认 `pages/BrowsePage.tsx` 是否有 v2 等价页面；若无则重写

**验收标准：**
- `api.ts` 中仅剩 auth 相关函数被前端调用（smart-import 和 material/company/person 均已迁走）

**预估工作量：** 5～7 天

---

### 阶段 5：旧路由下线

**目标：** 安全移除所有旧版路由和模型，彻底清理技术债。

**前提条件（全部满足后方可执行）：**
- 阶段 1～4 全部验收
- 线上运行至少 2 周无前端报错
- MCP 工具已切换到 v2 实体接口

**任务清单：**

- [ ] **5-1** 从 `main.py` 移除以下路由注册：
  - `routers.materials`
  - `routers.companies`
  - `routers.persons`
  - `routers.documents`
  - `routers.smart_import`
  - `routers.auth`（替换为 `routers.v2_auth`）
- [ ] **5-2** 删除以下文件：
  - `backend/routers/materials.py`
  - `backend/routers/companies.py`
  - `backend/routers/persons.py`
  - `backend/routers/documents.py`
  - `backend/routers/smart_import.py`
  - `backend/routers/auth.py`（替换为 v2_auth.py）
  - `backend/smart_import.py`
  - `backend/auto_processor.py`
- [ ] **5-3** 评估 `backend/database.py` 是否可缩减为仅含 `User`/`Session` 的最小版本（等阶段 1 完成后可整个删除）
- [ ] **5-4** 清理 `backend/main.py` 中对 `init_db()` 的调用（迁移完成后旧库只读）
- [ ] **5-5** 用 SQLite 工具确认旧表无新写入后，执行最终备份并归档旧库文件

**验收标准：**
- `main.py` 中无任何旧路由 import
- `database.py` 中无任何模型被 v2 路由引用
- 所有 v2 路由 500 错误率为 0

**预估工作量：** 2 天

---

## 数据映射细节（字段级）

### `materials.section` → `DmsDocument.folder_id`

`section` 是自由文本字符串（如"营业执照"、"资质证书"）。建议在 `v2_migrate.py` 中按如下映射解析：

```python
SECTION_TO_FOLDER_PATH = {
    "营业执照": "/公司资质/营业执照",
    "资质证书": "/公司资质/资质证书",
    "iso": "/公司资质/ISO认证",
    "iso认证": "/公司资质/ISO认证",
    "身份证": "/人员资质/身份证件",
    "学历": "/人员资质/学历证书",
    "合同": "/业绩材料/合同",
    "发票": "/业绩材料/发票",
    # 无匹配时 folder_id=null
}
```

### `material_versions` → `dms_revisions`

| 旧字段 | 新字段 | 处理方式 |
|---|---|---|
| `material_id` | `dms_revisions.document_id` | 通过 `meta_json._legacy_id` 反查 |
| `version_number` | `dms_revisions.version_number` | 直接映射 |
| `is_current` | `dms_revisions.is_current` | 直接映射 |
| `note` | `dms_revisions.change_note` | 直接映射 |
| `relation_type` | `dms_revisions.change_note` 附加 | 前缀写入，如 `"[renewal] 证书续期"` |
| `replaced_at` | `dms_revisions.created_at` | 用 replaced_at 覆盖默认值 |
| `replaced_reason` | `dms_revisions.change_note` 附加 | 与 relation_type 拼接 |
| `previous_material_id` | ❌ 无等价列 | 写入 `meta_json._legacy_prev_id` 保留线索 |
| `created_by` | `dms_revisions.created_by` | 直接映射（legacy user id，阶段 1 后可关联） |

### `materials.ocr_text` 保存策略

```python
# 在 v2_migrate.py 迁移 material 时补充以下逻辑
meta = {}
if material.ocr_text:
    meta["_legacy_ocr"] = {
        "text": material.ocr_text,
        "status": material.ocr_status,
        "error": material.ocr_error,
        "processed_at": material.ocr_processed_at.isoformat() if material.ocr_processed_at else None,
        "extracted_json": material.extracted_json,
    }
meta["_legacy_id"] = material.id
dms_doc.meta_json = json.dumps(meta)
```

---

## 需要新增的关键 SQL

```sql
-- 阶段 0：dms_entities 扩展
ALTER TABLE dms_entities ADD COLUMN credit_code TEXT;
ALTER TABLE dms_entities ADD COLUMN company_id_legacy INTEGER;
CREATE INDEX IF NOT EXISTS idx_entities_credit_code ON dms_entities(credit_code);

-- 阶段 2：实体关系表
CREATE TABLE IF NOT EXISTS dms_entity_relations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id     INTEGER NOT NULL REFERENCES dms_entities(id) ON DELETE CASCADE,
    to_id       INTEGER NOT NULL REFERENCES dms_entities(id) ON DELETE CASCADE,
    relation    TEXT NOT NULL,
    attributes  TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(from_id, to_id, relation)
);
CREATE INDEX IF NOT EXISTS idx_entity_rel_from ON dms_entity_relations(from_id);
CREATE INDEX IF NOT EXISTS idx_entity_rel_to   ON dms_entity_relations(to_id);

-- 阶段 1：认证迁移表（在 dms_models.py 中通过 ORM 创建，这里仅作参考）
CREATE TABLE IF NOT EXISTS dms_users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    role            TEXT DEFAULT 'editor',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login      TIMESTAMP,
    legacy_user_id  INTEGER
);
CREATE TABLE IF NOT EXISTS dms_sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES dms_users(id),
    token       TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at  TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dms_sessions_token ON dms_sessions(token);
```

---

## 风险与应对措施

| 风险 | 严重度 | 应对措施 |
|---|---|---|
| **人员-公司关系迁移时丢失**（`persons.company_id` 未写入 DMS）| 高 | 阶段 0-3 先将 `legacy_company_id` 写入 `entity.attributes`，阶段 2 建关系表后回填 |
| **旧 ID 失效导致外部集成崩溃**（MCP 工具接受旧整数 ID）| 高 | `meta_json._legacy_id` 建立双向映射；MCP 工具同时支持旧 ID 查找新实体 |
| **认证系统完全在旧模型，移除旧库导致无法登录** | 严重 | 阶段 1 必须最先完成，且需双写过渡期，不可跳过 |
| **材料迁移的 DocumentEntity 静默丢弃** | 高 | 阶段 0-3 修复后，在迁移日志中改为显式记录所有丢弃的关联；补充 `POST /retry-entity-links` 端点 |
| **OCR 数据迁移丢失** | 中 | 阶段 0-2 将 ocr_text 写入 `meta_json._legacy_ocr`；后续可按需触发 reprocess |
| **`file_hash IS NULL` 的 materials 重复迁移** | 中 | 阶段 0-7 改用 `_legacy_id` 做幂等键 |
| **SQLite WAL 模式下两套 session 并发写入** | 低 | 两套 ORM 已使用独立 `engine`，WAL 允许并发读；写入分属不同表，无锁竞争 |

---

## 建议废弃时间线

```
Week 1-2   阶段 0：补丁加固（migration 脚本修复）
Week 3-4   阶段 1：认证迁移（DmsUser/DmsSession + v2_auth 路由）
Week 5     阶段 2：实体关系重建
Week 6-8   阶段 3：智能导入管线迁移（工作量最大）
Week 9-10  阶段 4：前端 Material/Company/Person 页面切换
Week 11    验证期：线上双跑，监控错误日志
Week 12    阶段 5：旧路由下线，清理代码
```

**总计约 12 周（3 个月）全职工作，可视团队规模并行部分阶段。**

---

## 执行注意事项

1. **每个阶段开始前先备份 SQLite 文件**，使用 `backup.sh` 脚本
2. **阶段 1（认证）是硬性前置**，其他阶段可并行，但认证必须最先稳定
3. **旧路由下线（阶段 5）前保留至少 2 周双跑期**，通过 access log 确认旧端点流量归零
4. **MCP 工具的 `get_company_complete`、`get_person_complete` 在阶段 2 后需同步更新**，否则外部 AI 客户端查询结果将为空
5. **无自动化测试**：每个阶段完成后需手动走通 黄金路径（上传→OCR→审核→搜索→到期预警→聊天代理）
