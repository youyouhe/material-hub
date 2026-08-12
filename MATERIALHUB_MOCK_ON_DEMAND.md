# MaterialHub 按需 Mock 材料生成 — 需求设计

状态：草案，待 Hub 团队评审
提出方：SmartBid 团队
关联现状：MaterialHub 当前配置为 mock 数据（出于用户隐私考虑，暂不接入真实资质库），库中现有 35 份种子样例文档，与具体招标项目无关联。

## 1. 背景与问题

SmartBid 的投标 skill（`bid-material-search`）在编写标书时，需要从 MaterialHub 检索营业执照、资质证书、业绩合同等材料，填充响应文件中的扫描件占位符。

现状痛点：招标文件要求的资质五花八门（如"ISO27001信息安全管理体系认证""纳税信用A级证书""同类项目销售业绩合同"），MaterialHub 库中的 35 份种子样例是提前随机生成的，与任何具体招标项目无关。当 skill 检索确认某类材料**零命中**时，当前唯一选择是把占位符留空，等用户手工补充——这会中断"一键投标"全流程自动化的价值。

**目标**：允许 skill 在确认零命中后，主动请求 Hub 按招标要求"现造"一份贴合的 mock 材料，让标书编写不中断；同时这份材料必须被**显著标记为待替换**，防止用户误把假证书当真提交。

## 2. 安全前提（不可退让）

1. 按需生成的材料必须与"真实材料"在数据层面**可区分、可筛选**——不能与已有种子样例混为一谈。
2. 用户上传真实材料替换后，标记必须**自动清除**，不依赖人工操作或下游轮询。
3. 最终交付物中，"仍待替换的 mock 材料清单"必须在 SmartBid 侧被**强制置顶展示**，不能被"投标文件已生成"之类的完成态提示盖过。

## 3. Hub 端需要新增的接口

### 3.1 按需生成 mock 材料

```
POST /api/v2/documents/mock-generate
```

请求体：
```json
{
  "doc_type_code": "iso-cert",
  "entity_name": "星辰科技有限公司",
  "requirement_context": {
    "tender_project": "教学管理系统项目 2026-JQ55-W1013",
    "requirement_text": "投标人须具备ISO27001信息安全管理体系认证",
    "constraints": {
      "cert_name": "ISO/IEC 27001",
      "valid_after": "2026-08-01"
    }
  },
  "folder_path": "/公司资质/资质证书/"
}
```

- `doc_type_code`：复用现有 `/api/v2/doc-types/` 目录里的 code（如 `iso-cert`/`business-license`）。若招标要求的资质类型不在现有 16 种目录里，需要 Hub 侧先支持新增 doc_type，或本接口允许传自由文本类型描述作为兜底。
- `requirement_context`：原样存储、原样回填，供后续追溯"这份材料是因为哪条招标要求生成的"。`constraints` 字段格式待第 6 节讨论。

响应体（在现有 `/api/v2/documents/{id}` 结构基础上）：
```json
{
  "id": 42,
  "title": "星辰科技有限公司 - ISO27001认证（MOCK-待替换）",
  "metadata": {
    "mock": true,
    "mock_reason": "generated_for_requirement",
    "requirement_context": { "...": "原样回填" },
    "extracted_data": { "...": "结构化字段，供 skill 立即取用" }
  },
  "requires_user_replacement": true
}
```

**关键区分**：现有 35 份种子样例是 `mock: true` 但无 `mock_reason`（系统自带通用示例）；本接口生成的材料额外带 `mock_reason: "generated_for_requirement"`（因真实资料缺失、专为糊住某条招标要求生成）。两者都是假数据，但下游处理策略不同——后者必须被追踪至替换为止，前者不需要。

**实体一致性**：同一 `entity_name` 多次调用生成接口时，公司基础字段（信用代码/法人/地址等）必须与该实体已有材料保持一致，不能同一公司在不同证书上法人对不上。建议 Hub 生成前查询该 entity 是否已有基础属性（`attributes`），有则复用，无则新生成一套并沉淀，供后续同实体调用复用。

### 3.2 待替换清单查询

```
GET /api/v2/documents?mock_reason=generated_for_requirement&status=active
```

或在现有 `/api/v2/search` 上新增 `mock_reason` 过滤参数。用于 SmartBid 在标书组装收尾阶段拉取"本次投标涉及哪些临时补造的材料"，生成待办清单。

### 3.3 替换后自动清除标记

用户在 Hub 上传真实材料替换某份 mock 文档（走现有版本/revision 替换流程）后，Hub 应**自动**清空该文档的 `metadata.mock`、`mock_reason`、`requires_user_replacement`。SmartBid 侧不做轮询确认，依赖 3.2 的清单查询天然排除已替换项。

**待确认**：现有 revision 替换逻辑是否已具备这个清理行为？如果没有，需要作为本需求的一部分补上。

### 3.4 幂等约束

同一 `(entity_name, doc_type_code, tender_project)` 组合重复调用生成接口时，应返回已存在的那份而非重新生成，避免 skill 侧重试/多次调用导致库内堆积重复假材料。建议生成前做查重，或接口设计为 upsert 语义（有则更新 `requirement_context`，无则新建）。

## 4. SmartBid / Skill 端配套改动（供 Hub 团队了解调用方行为，非本次需要 Hub 实现）

1. 新增写类工具 `material_hub_mock_generate`，与现有只读检索工具分开注册（因涉及副作用）。
2. SKILL.md 层面约束：**必须先完整走完现有五级检索（实体聚合→下钻→关键词→语义/多跳→图谱探索）确认零命中，才允许调用生成接口**——延续现有"阴性结果规则"纪律。
3. 新增 `mock_materials_registry.json`（与现有 `placeholders.json` 并列），记录本次投标流程中所有调用过生成接口的材料及对应招标要求原文。
4. `bid-assembly` 质检阶段：若该 registry 非空，最终交付说明中以最高优先级列出"待替换材料清单"（材料类型、对应招标要求、Hub 文档链接），不得被其他完成态提示掩盖。
5. `bid-manager` S11 扫描件替换阶段的兜底规则从"零命中→留空占位符"改为"零命中→尝试生成→成功则替换并标记待替换，失败才留空"。

## 5. 典型调用时序

```
skill 检索营业执照/ISO认证/业绩合同...
  → 五级检索全部零命中
  → POST /api/v2/documents/mock-generate（带招标要求原文）
  → Hub 返回新文档（含结构化字段 + requires_user_replacement=true）
  → skill 用返回的图片/字段完成占位符替换，登记 mock_materials_registry.json
...
标书生成完毕
  → bid-assembly 拉取 GET .../documents?mock_reason=generated_for_requirement
  → 在交付说明置顶"以下 N 份材料为临时生成，提交前必须替换为真实材料"清单
...
用户在 Hub 上传真实材料替换
  → Hub 自动清除该文档的 mock 标记
```

## 6. 待与 Hub 团队确认的开放问题

1. **生成内容的真实度**：按需生成的证书图片本身要不要做到"看起来像真实扫描件"，还是只需结构化字段能撑住下游流程、图片用统一的"MOCK 待替换"水印占位图即可？SmartBid 侧倾向后者——更简单，且能进一步降低被误用于真实提交的风险。
2. **`constraints` 字段格式**：做成强类型 schema（每种 doc_type 固定字段集），还是保持自由 key/value？招标要求五花八门，自由格式更灵活，但会弱化下游统计能力（如"本次投标因缺哪些资质而生成了材料"）。
3. **生成配额/限流**：是否需要对单个 entity/单次投标流程的生成次数设上限，防止调用方逻辑异常时无限重复生成造成库内垃圾数据堆积？
4. **doc_type 覆盖不足时的兜底**：招标要求的资质类型不在现有 16 种 doc_type 目录里时，是走"新增 doc_type"的正式流程，还是允许生成接口接受自由文本类型作为临时兜底？

## 7. 现有数据现状（供参考）

MaterialHub 当前 doc_type 目录（`/api/v2/doc-types/`）：

| 分类 | 类型 |
|------|------|
| bid | 投标文件 |
| company | 营业执照、资质证书、ISO认证、荣誉奖项、授权文件、产品资料、公司简介、审计报告 |
| personnel | 学历证书、职称证书、身份证 |
| project | 合同、验收报告、发票、技术文档 |

现有 Entity 表（`/api/v2/entities/`）目前只是从提取字段派生出的零散 `topic` 节点（如"10000万元"），不是真正的公司/人员结构化档案——本需求的"实体一致性"要求，客观上也会推动 Hub 建立更完整的实体档案能力。
