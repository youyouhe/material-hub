# MaterialHub Mock 生成改用 LLM 生成内容 — 修改建议

提出时间：2026-08-02
提出方：SmartBid 团队
背景：`GAPS.md`/`GAPS_ROUND2.md` 两轮反馈的问题（CQC 证书类型误判、授权书 scope 不跟随业务领域、发票金额内部矛盾、同一响应内三个不同公司名）历经多轮修复仍反复出现或复发。我们判断这不是个别 bug，而是当前生成方式的**结构性上限**——建议改变生成方式本身，而非继续逐个字段打补丁。

## 1. 问题根因判断

现有 `POST /api/v2/mock/generate`（及 `generate-on-demand`）看起来是"按 `doc_type_code` 从模板/种子池里抽取字段拼装"的机制。这类实现有两个天生短板，且都在我们的复测中反复验证到：

1. **不理解语义，只能匹配关键词或直接固化**：`qualification-cert` 传"CQC节能产品认证证书"，返回的是"国家高新技术企业"——不是没做关键词匹配，就是匹配表没覆盖到这个证书名。每加一种证书名就要加一条规则，扩展性天然差。
2. **字段之间各自独立生成，缺乏统一一致性校验**：同一次响应里 `entityName` 参数、`mock_data.company_name`、`image_url` 文件名前缀出现三个不同公司名（"独立核实测试公司"/"启明科技有限公司"/"星辰科技有限公司"）——说明这几个字段是分别取值、拼在一起返回的，没有一个环节校验过它们该是同一个东西。发票金额内部矛盾（含税总额 ≠ 明细项之和）也是同一类问题。

我们看到 Hub 已经在 `/api/v2/settings/` 里配置了 LLM provider（用于 OCR/Embedding 等能力），说明 Hub 本身具备接入 LLM 的基础设施，建议把这一能力用到 mock 内容生成上。

## 2. 建议方案：内容生成环节改为 LLM 驱动，其余环节不变

**明确不变的部分**（这些已验收通过、且这几轮复测没有回归，不建议动）：
- 接口契约（`generate-on-demand` 的请求/响应结构、`mock`/`mock_reason`/`requires_user_replacement` 字段）
- 图片生成、水印、文件存储、`revision` 替换后自动清除 mock 标记的生命周期机制
- 幂等键 `(entity_name, doc_type_code, requirement_text)`
- 实体基础属性复用机制（同一 entity 的信用代码/法人/地址已经能正确复用，这部分工作正常）

**建议改变的部分**：生成 `mock_data` 里具体字段值（`cert_name`、`scope`、`project_name`、发票明细等"内容"字段）这一步，从"查表/随机池"改为一次 LLM 调用。

### 2.1 调用时机与输入

在收到 `generate-on-demand` 请求、确认好该 entity 已有的基础属性（复用逻辑不变）之后，构造一次 LLM 调用，输入：

```json
{
  "doc_type_code": "qualification-cert",
  "entity_known_attributes": {
    "company_name": "星辰科技有限公司",
    "legal_person": "刘涛",
    "credit_code": "91XXXXXXXXXXXXXXX",
    "address": "..."
  },
  "requirement_text": "投标人须提供CQC节能产品认证证书",
  "tender_project": "教学管理系统项目 2026-JQ55-W1013"
}
```

`entity_known_attributes` 是这次的关键——把该实体已经存在的真实字段作为**约束**喂给 LLM，而不是让 LLM 或模板另起一套。这样"公司名/法人/地址是否一致"直接由 LLM 在同一次生成里保证，天然消除"三个不同公司名"这类问题（不需要事后再做一致性校验，因为源头就只有一份权威输入）。

### 2.2 输出：每个 doc_type 一个结构化 schema，让 LLM 做语义匹配和内部一致性计算

按 doc_type_code 定义输出字段的 JSON schema（复用现有 `mock_data` 里已有的字段结构，不需要新设计一套），要求 LLM：
- 对 `qualification-cert`：从 `requirement_text` 里识别出具体证书名称（如"CQC节能产品认证"），生成对应的 `cert_name`/`issuing_authority`/`scope`，而不是从固定池子里选。
- 对 `authorization`：`scope` 字段必须体现 `tender_project`/`requirement_text` 里的业务领域（如"教学管理系统"），不是随机项目名。
- 对 `invoice`：要求 LLM 在同一次输出里给出金额明细和汇总，并显式校验"明细之和 = 汇总"（可以在 prompt 里直接要求"先算明细，再算合计，禁止两者矛盾"，LLM 做算术一致性远比模板拼接可靠）。
- 对 `contract`：延续已经验证有效的"`project_name` 跟随 `requirement_text` 业务领域"这个行为，只是把实现换成 LLM（内容质量应该更稳，覆盖面也更广，不需要再逐个业务领域加规则）。

### 2.3 图片渲染环节不变

LLM 只负责产出结构化字段值（`mock_data`），图片仍然用现有的模板渲染 + 水印机制，把 LLM 生成的字段值填进现有的图片模板里即可，不需要 LLM 生成图片内容本身。这样风险面小、改动集中在"内容"这一层。

## 3. 这个方案如何解决已反馈的具体问题

| GAPS 反馈的问题 | LLM 方案下预期结果 |
|---|---|
| CQC 节能认证证书类型误判为"国家高新技术企业" | LLM 直接从 `requirement_text` 提取"CQC节能产品认证"这个证书名生成，不依赖关键词表 |
| 授权书 scope 不跟随业务领域 | 与 `contract.project_name` 用同一套机制（LLM 读 `requirement_text`），不需要逐字段单独适配 |
| 发票金额内部矛盾 | 要求 LLM 在同一次输出中自行校验"明细之和=汇总"，比字段独立生成再拼接更可靠 |
| 同一响应内三个不同公司名 | `entity_known_attributes` 作为唯一权威输入源，一次生成里所有字段共享同一份实体信息，结构上不会再出现分叉 |
| 服务端出现与本项目无关的其他实体种子样例污染查询结果 | 这个问题独立于生成方式（属于查询/过滤逻辑），不在本提案范围内，建议继续按原 issue 跟踪 |

## 4. 我们理解的成本/权衡，供 Hub 团队评估

1. **延迟**：LLM 调用比查表慢，`generate-on-demand` 响应时间会从毫秒级变成秒级。SmartBid 侧这个调用本来就是 agent 会话中的一次工具调用，多等几秒可接受，不是问题。
2. **成本**：每次生成消耗一次 LLM token，量级远小于 SmartBid 自己的标书生成流程，预计影响很小。
3. **稳定性兜底**：建议 LLM 调用失败（超时/解析失败）时，回退到现有的模板/随机池生成，保证接口不因为 LLM 不可用而整体不可用——这是唯一需要保留旧生成逻辑的原因。
4. **不需要一次性覆盖所有 16 个 doc_type**：可以先在这次反复出问题的几个类型上落地（`qualification-cert`/`authorization`/`invoice`/`contract`），验证效果后再推广到其余类型，风险和工作量都可控。

## 5. 我们不建议的替代方案

我们也考虑过让 SmartBid 侧（拿到 Hub 返回的基础字段后）用自己的 LLM 二次加工/校验内容，但放弃了这个思路——因为 Hub 才掌握"这个 entity 已有哪些真实字段"这个权威信息源，SmartBid 侧二次加工等于要先把 Hub 的实体数据全量同步过来做校验，属于反向重复建设。内容生成放在 Hub 端（数据和生成逻辑在同一处），SmartBid 侧继续只做"检索→调用生成接口→登记待替换清单"，分工更清晰。

## 6. 待 Hub 团队确认的问题

1. 这个改动是否可以复用 `/api/v2/settings/` 里已配置的 LLM provider，还是需要单独配置一个用于 mock 生成的模型（考虑到成本，可能希望用比 OCR/Embedding 更便宜的模型）？
2. `entity_known_attributes` 目前哪些字段可以直接从现有 entity 属性表读到？是否所有 doc_type 都需要，还是按类型选取子集喂给 LLM（如 `id-card` 只需要姓名，不需要公司地址）？
3. 是否需要我们（SmartBid）在下一轮真实"一键投标"里针对这 4 类 doc_type 做一次专项复测，作为验收依据？

以上建议基于三轮真实场景复测中反复出现的具体证据（详见 `MATERIALHUB_MOCK_GENERATION_GAPS.md`/`_ROUND2.md`），核心判断是：这类"语义匹配+内部字段一致性"的要求，天然更适合用 LLM 解决，而不是持续扩充关键词匹配表和随机池。
