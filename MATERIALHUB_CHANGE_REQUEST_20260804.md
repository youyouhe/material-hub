# MaterialHub 修改需求（SmartBid 侧提出）

日期：2026-08-04（v2：追加需求 3 mock 模式开关契约）
提出方：SmartBid 平台
对接方：MaterialHub 团队
影响接口：`POST /api/v2/mock/generate-on-demand`、`GET /api/v2/search`、`GET /api/v2/entities/`、`GET /api/v2/documents`

---

## 背景

SmartBid 投标 agent 通过 `generate-on-demand` 按需生成 mock 材料（营业执照、资质证书、业绩合同等），生成后需要在后续会话中按**投标主体（实体）**检索复用这些材料。当前实现导致"材料明明在库里，按实体却查不到"，agent 误判库中无材料，向最终用户重复收集信息。

---

## 问题 1（高优先级·功能缺陷）：mock 生成不建立实体↔文档关联，按实体检索返回 0

### 现象

`generate-on-demand` 生成的文档只把主体名称写入文档 `metadata.entity_names`，**没有建立实体（entity）与文档（document）的关联**。后果：

- `GET /api/v2/search?entity_id={id}` → 0 条（agent 按主体取材料的主路径）
- `GET /api/v2/entities/` 列表中该实体的 `document_count` → 0
- 但 `GET /api/v2/documents/?mock_reason=generated_for_requirement` → 能查到全部生成文档

### 证据（生产环境 material.senseflow.club，2026-08-04 实测）

实体 `武汉智汇医教科技有限公司`（id=517）：

```bash
# 按实体检索 → 0 条
GET /api/v2/search?entity_id=517&limit=30
→ {"results": []}

# 实体列表 → document_count = 0
GET /api/v2/entities/?limit=50
→ {"id": 517, "entity_type": "org", "name": "武汉智汇医教科技有限公司", "document_count": 0}

# 但 mock 文档实际存在 → 16 条
GET /api/v2/documents/?mock_reason=generated_for_requirement&status=active&limit=100
→ 16 条（营业执照×1 / 审计报告×3 / 合同×2 / 发票×2 / 资质证书×4 / 身份证×2 / 技术文档×2），
  每条的 metadata.entity_names 均含 "武汉智汇医教科技有限公司"
```

### 影响

agent 的 `material_hub_entity_documents(entityName)` 工具（内部即 `search?entity_id=`）对该公司返回"材料 0 份"，与真实库存（16 份）矛盾，导致投标流水线 S4 阶段向用户重复收集本可复用的材料。

### 修改要求

1. `generate-on-demand` 生成文档时，按 `entityName` 解析/创建实体后，**同步建立实体↔文档关联**（与人工上传文档相同的关联路径），使以下两处立即可见：
   - `GET /api/v2/search?entity_id={id}` 返回生成的文档
   - `GET /api/v2/entities/` 的 `document_count` 计数正确
2. **存量数据修复（backfill）**：对现有 `mock_reason=generated_for_requirement` 的 16 份文档，按 `metadata.entity_names` 补建关联。

### 验收标准

```bash
GET /api/v2/search?entity_id=517 → 返回 ≥16 条
GET /api/v2/entities/?q=武汉智汇医教 → document_count ≥ 16
```

---

## 问题 2（中优先级·数据质量）：人员被注册为 org 实体

### 现象

mock 生成涉及人员材料（身份证）时，人员被创建为 `entity_type=org`（公司）而非 `person`：

```bash
GET /api/v2/entities/?limit=50
→ {"id": 549, "entity_type": "org", "name": "张静"}      # 法定代表人，应为 person
→ {"id": 550, "entity_type": "org", "name": "李静怡"}    # 授权代表，应为 person
```

### 影响

- 实体类型语义被污染：按 `entityType=org` 列举候选投标主体时混入人名
- 人员类材料（身份证/职称/社保）后续按 person 检索将查不到

### 修改要求

1. `generate-on-demand` 按材料类型决定实体类型：人员类材料（身份证、职称证书、社保证明等 `doc_type` 归属人的）→ 创建/关联 `entity_type=person` 实体；公司类材料 → `entity_type=org`。
2. **存量修复**：将 id=549（张静）、id=550（李静怡）的 `entity_type` 改为 `person`（或删除后按正确类型重建关联）。

---

## 需求 3（高优先级·契约设计）：mock 模式开关的对外契约

### 背景

MaterialHub 按部署场景可关闭 mock 能力。真实资料环境下必须**杜绝真实材料与 mock 材料混合**——否则最终标书中出现无法识别真假的内容，构成废标/虚假应标风险。因此 mock 开关不能只停留在 hub 内部配置，必须形成对调用方的正式契约。单一机制不够：

- **只在生成时报错**：调用方的流程设计依赖模式（mock 关闭时根本不该向最终用户提供"全部 mock"选项），到生成时才发现为时已晚
- **只提供能力查询**：模式可能在长流水线执行中途被切换，缓存的能力值过期，需要执行层最终防线
- **两层都有但读侧不隔离**：测试期生成的存量 mock 文档在真实环境仍会被检索出来当真材料——混合风险主要来自"读"

故采用三层设计：

### 3.1 能力广播（规划层）

```
GET /api/v2/capabilities
→ 200 { "version": "2.x", "mock": { "enabled": false, "mode": "disabled" } }
```

- 无敏感信息、廉价调用；调用方在流程启动预检时获取并缓存于本次运行
- 建议所有 API 响应附带 `X-MaterialHub-Mock-Mode: enabled|disabled` 响应头，使模式中途切换可被感知（防御纵深）

### 3.2 写侧硬错误（执行层，最终防线）

mock 关闭时：

```
POST /api/v2/mock/generate-on-demand
→ 403 { "error": { "code": "MOCK_DISABLED", "message": "当前环境已禁用 mock 材料生成", "mock_enabled": false } }
```

- 必须是**机器可读的 `code`**，禁止用 500/404 或纯文案表达
- 调用方语义：terminal——不重试、不伪造成功，缺失材料落入"未替换清单"并在交付摘要中分级上报

### 3.3 读侧隔离（数据卫生层）

- mock 关闭时，**所有检索/列表接口默认不返回 mock 文档**；仅 `?include_mock=true` 显式请求时返回（管理/审计用途）
- 所有文档响应携带一等字段 `is_mock: bool` 与 `mock_status: pending_replacement | replaced | null`（当前调用方靠解析标题后缀"（MOCK-待替换）"识别，脆弱，标题变更即失效）
- mock 开启时检索行为不变，但上述字段照常携带

### 3.4 调用方（SmartBid）行为矩阵（供理解契约语义）

| 模式 | 材料命中 | 材料缺失 |
|---|---|---|
| `enabled` | 正常使用；mock 材料标注"待替换" | 按用户授权（mock_grant）按需生成 |
| `disabled` | 正常使用 | 信息收集阶段不提供 mock 选项；缺失列入"未替换清单"并向用户收集，交付状态为 SUCCESS_WITH_BLOCKERS |
| capabilities 查询失败 | 保守按 `disabled` 处理 | 同 `disabled` |

### 验收标准

mock 关闭后：
1. `GET /api/v2/capabilities` 返回 `mock.enabled=false`
2. `POST /api/v2/mock/generate-on-demand` 返回 403 且 `error.code == "MOCK_DISABLED"`
3. `GET /api/v2/search` / `/api/v2/documents` 默认结果不含 `is_mock=true` 文档；`?include_mock=true` 可查到且每条带 `is_mock`/`mock_status` 字段
4. mock 重新开启后：以上全部恢复当前行为

---

## 附：调用方已做防御（供参考，不影响上述要求的必要性）

SmartBid 侧已在 skill 流程中要求 agent 同时查询待替换清单（`mock_reason` 过滤路径）作为交叉数据源，缓解关联缺失的影响；用户 mock 授权已落盘（`mock_grant`）避免重复询问。但实体关联与模式契约才是正路，请按上述要求修复。

## 联系人

- SmartBid 侧：（待填）
- 问题反馈渠道：（待填）
