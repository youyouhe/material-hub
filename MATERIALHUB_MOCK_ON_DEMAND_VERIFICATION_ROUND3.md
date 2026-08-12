# MaterialHub 按需 Mock 生成 — 复测反馈（第三轮）

测试时间：2026-08-01（紧接 commit `a3163fc` 部署后）
测试方：SmartBid 团队
依据：Hub 团队反馈"已部署跨模板字段名映射（legal_person → authorizer_legal_person/legal_representative/contact_person；unified_social_credit_code → credit_code；address → party_a_address/party_b_address），授权书 authorizer_legal_person 会自动从同一 entity 的营业执照 legal_person 复用"

## 结论

**复测未观察到映射生效**。三组映射（法人、信用代码、地址）逐一测试，均是每次调用返回新的随机值，未出现一次复用已有实体档案的情况。怀疑代码未生效部署，或部署的分支/配置与预期不一致，请 Hub 团队复核 `a3163fc` 是否已实际生效在 `https://material.senseflow.club` 这个环境上。

## 测试对照基准

实体"测试验证科技有限公司"的营业执照（`document_id=38`，第二轮测试中生成，未变更）：
```
legal_person: 郭斌
unified_social_credit_code: 912184358165235307
address: 陕西省深圳市天河区天河路54号
```

## 逐项复测

### 1. `legal_person → authorizer_legal_person` 映射 — 未生效

同一实体连续生成 4 次 `authorization`（授权文件）类型材料，`authorizer_legal_person` 结果：

| 调用次序 | document_id | authorizer_legal_person | 是否等于"郭斌" |
|---|---|---|---|
| 1 | 42 | 高超 | ❌ |
| 2 | 44 | 高洋 | ❌ |
| 3 | 45 | 徐秀兰 | ❌ |
| 4 | 46 | 李桂英 | ❌ |

4 次调用、4 个不同的随机姓名，无一次复用营业执照的"郭斌"。

### 2. `address → party_a_address / party_b_address` 映射 — 未生效

同一实体连续生成 3 次 `contract`（合同）类型材料，其中该实体作为乙方（`party_b`），`party_b_address` 结果：

| 调用次序 | document_id | party_b | party_b_address | 是否等于"陕西省深圳市天河区天河路54号" |
|---|---|---|---|---|
| 1 | 43 | 测试验证科技有限公司 | 上海市杭州市南山区长安街480号 | ❌ |
| 2 | (未记录id，见下方补测) | 测试验证科技有限公司 | 北京市重庆市雁塔区中关村大街492号 | ❌ |
| 3 | (未记录id，见下方补测) | 测试验证科技有限公司 | 江苏省重庆市雁塔区中山路86号 | ❌ |

3 次调用、3 个不同随机地址，无一次复用营业执照地址。另外注意到生成的地址本身格式有问题（如"北京市重庆市雁塔区中关村大街492号"——省市区拼接出现"北京市"+"重庆市"同时出现的逻辑错误，这是另一个独立的小问题，附带反馈）。

### 3. `unified_social_credit_code → credit_code` 映射 — 未测出目标字段

本轮测试用的 `contract`/`authorization` 模板返回字段中未出现 `credit_code` 字段本身（`mock_data` 里没有这个 key），无法直接验证该映射是否生效。可能需要 Hub 提供一个明确包含 `credit_code` 字段的 doc_type 示例（比如资质证书类模板是否有此字段），或告知哪个 `doc_type_code` 会返回 `credit_code`，以便我们针对性复测。

## 排查建议

1. 请确认 `https://material.senseflow.club` 当前运行的代码版本确实是 `a3163fc`（而不是部署流程本身的问题，比如缓存未刷新、灰度未切全量等）。
2. 请提供一次 Hub 团队自己复现"映射生效"的具体调用示例（请求体 + 返回体），我们对照复测，排除是我们请求参数用法不对导致映射逻辑没被触发的可能（例如是否需要额外传参才激活映射、`entity_name` 精确匹配要求等）。

## 本轮测试产生的新数据（供清理）

| document_id | doc_type | entity_name | 用途 |
|---|---|---|---|
| 42 | authorization | 测试验证科技有限公司 | 法人映射复测1 |
| 43 | contract | 测试验证科技有限公司 | 地址映射复测1 |
| 44 | authorization | 测试验证科技有限公司 | 法人映射复测2 |
| 45 | authorization | 测试验证科技有限公司 | 法人映射复测3 |
| 46 | authorization | 测试验证科技有限公司 | 法人映射复测4 |
| （另有2份未记录id的contract，地址映射复测2/3） | contract | 测试验证科技有限公司 | 地址映射复测 |

均为测试数据，非真实项目材料。

## 下一步

在收到 Hub 团队确认的复现示例、并排除环境/参数使用问题之前，SmartBid 侧继续暂缓接入正式调用链。
