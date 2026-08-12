# MaterialHub Mock 生成能力扩展需求

提出时间：2026-08-02
提出方：SmartBid 团队
背景：`mock/generate-on-demand` 接口已验收通过（见 `MATERIALHUB_MOCK_ON_DEMAND_VERIFICATION_ROUND1~12.md`），SmartBid 侧已完成 skill 集成（`material_hub_mock_generate` 工具 + 五级检索零命中兜底路径）并部署上线。本文档基于**真实一键投标场景**的实战日志，提炼出当前 mock 生成服务暴露的具体能力缺口。

## 结论

之前的验收聚焦"同一实体多份材料间字段一致性"（公司名/法人/地址），已确认通过。但这次真实场景暴露的是**另一个维度的问题**：同一 `doc_type_code` 在不同调用间**内容固化/不随请求参数变化**，导致同一类型的材料无法按需生成出不同的具体内容——这让 mock 生成在需要"多个同类但不同"材料的场景下（如多个人员的身份证、多份不同业绩合同）基本不可用。

## 具体问题（均来自同一次真实标书编写过程的连续调用）

### 1. `id-card`（身份证）：内容完全固化，不随 `entityName` 变化

**现象**：无论 `entityName` 传入哪个人名，`doc_type_code=id-card` 的生成结果**姓名固定返回"高洋"**。

**实际影响**：本次标书需要法定代表人（营业执照生成的"刘涛"）和授权代表（另一人）各自的身份证材料。连续两次调用 `id-card`，`entityName` 不同，返回的都是同一个人"高洋"——**与营业执照法人姓名完全对不上**，也无法区分法人和授权代表两张不同的身份证。

**期望行为**：`id-card` 应该像 `authorization`（授权书）已经验收通过的行为一样——`name` 字段应该跟随 `entityName` 或该实体已有的关联人员信息生成，至少要能生成"两个不同的人"对应两次不同调用，而不是永远返回同一个固定人名。

### 2. `audit-report`（审计报告）：doc_type 目录里存在，但生成接口不支持

**现象**：调用 `material_hub_doc_types` 能看到 `审计报告`（分类 company）在目录里，但调用 `mock/generate-on-demand` 时传 `doc_type_code=audit-report` 直接报错"不支持该类型"（详见更早的第一轮测试：`{"detail":"Unknown doc_type_code: audit-report. Valid: acceptance-report, authorization, bid-document, business-license, company-profile, contract, education-cert, honor-award, id-card, invoice, iso-cert, product-brochure, professional-cert, qualification-cert, technical-doc"}`——16 个目录项里其实没有 audit-report，与 `doc_types` 接口返回的列表不一致）。

**期望行为**：`doc_types` 列出的类型和 `mock/generate-on-demand` 实际支持的类型应该一致。审计报告是招标里常见的资质证明材料（本次评分里对应 5 分），建议补充支持；如果短期内无法支持，至少让 `doc_types` 接口标注哪些类型"仅用于分类展示、暂不支持生成"，避免调用方以为能生成而浪费一次失败请求。

### 3. `contract`（合同）：内容随机，无法按业务领域定向生成

**现象**：调用 `doc_type_code=contract` 生成的合同，`project_name` 是完全随机的项目类型（本次返回的是"工业互联网系统开发项目"运维合同），而招标要求的业绩材料必须是"教学管理系统"同类项目的销售合同。

**实际影响**：业绩证明这类材料对"项目类型是否同类"有实质性评分要求（本次评分规则：教学管理系统销售业绩，6分），生成内容与实际需求领域不匹配的合同**完全无法使用**，只能放弃 mock、保留占位符。

**期望行为**：`requirement_context.requirement_text`（招标原文，如"教学管理系统销售合同"）应该被读取并用于影响生成内容的 `project_name`/`project_description` 等字段，而不是仅作为记录存档、不参与实际内容生成。这是当前"实体一致性"（复用公司名/法人）之外的另一层需求——"内容与招标要求的领域相关性"。

### 4. `qualification-cert`（资质证书）：同一类型码固定返回同一种证书，无法区分具体证书名称

**现象**：连续多次调用 `doc_type_code=qualification-cert`，无论 `requirementText` 分别写"纳税信用A级证书""CQC节能认证""CEC环境标志认证""发明专利""标准制定证明"，返回的 `cert_name` **始终是同一个"高新技术企业证书"**（或类似的固定种子内容）。

**实际影响**：招标评分里这 5 类证书是分别计分的独立评分项（各 1 分），但 mock 服务把它们当作同一份材料反复返回，实际上只能满足其中一项，其余 4 项无法通过 mock 满足，只能保留占位符。

**期望行为**：与问题 3 类似——`requirementText` 中的证书名称信息应该被用于生成对应的 `cert_name`/`issuing_authority`/`scope` 等字段，让同一个 `doc_type_code` 下不同的具体要求能生成出不同的证书内容，而不是每次都是同一份种子样例。

## 关于 `doc_type_code` 覆盖范围（附带发现，非本次重点）

本次招标涉及的以下材料，在现有 16 个 `doc_type_code` 目录里完全没有对应类型（不是"生成失败"，是压根没有这个分类）：

- 投标保证金凭证
- 银行进账凭证（业绩合同的资金证明）
- 完税凭证（纳税总额证明）
- 社保缴纳证明（授权代表任职证明）

这些材料目前只能保留占位符，无法通过 mock 满足。是否要扩展 `doc_type_code` 目录覆盖这些类型，还是维持现状由用户自行补充，请 Hub 团队评估决定——这类材料本身"防伪造"敏感度也更高（涉及资金流水），mock 生成的必要性和风险要一并权衡。

## 建议的优先级

1. **问题 1（id-card 姓名固化）**：影响面最直接——几乎每次投标都需要法人+授权代表两个人的身份证，当前完全无法区分，建议优先修复。
2. **问题 4（qualification-cert 内容固化）**：影响面广——涉及多个独立评分项，逐条对应不同证书类型，建议优先修复。
3. **问题 3（contract 内容随机）**：影响业绩类评分项，修复收益高但涉及"如何从 requirementText 提取业务领域"这类更复杂的生成逻辑，可能需要更多设计讨论。
4. **问题 2（audit-report 目录不一致）**：先解决目录一致性问题（哪怕先标注"不支持"），比支持生成本身更紧急、成本更低。

以上问题均来自 2026-08-02 一次真实的完整"一键投标"流程实测，非人为构造的边界测试，反映的是当前 mock 生成能力在真实标书编写场景下的实际瓶颈。
