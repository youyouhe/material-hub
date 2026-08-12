# MaterialHub 按需 Mock 生成 — 复测反馈（第四轮）

测试时间：2026-08-01（紧接 commit `e4993a5` 部署后）
测试方：SmartBid 团队
依据：Hub 团队反馈根因是"entity extraction 不为 company_name 创建 org entity，改为绕过 entity、直接按 company_name LIKE 匹配 extracted_data"，并称"授权书 authorizer_legal_person 现在能复用营业执照 legal_person"

## 结论

**法人姓名映射（`legal_person` 系列别名）已确认修复**，稳定生效。但复测覆盖到更多字段/模板后，发现两个新问题：**地址映射（`address → party_a_address/party_b_address`）在合同模板上仍未生效**；以及**法人姓名映射生效后带出的新问题**——身份证上"姓名复用法人姓名，但性别未联动校验"，出现"郭斌（女）"这种一眼可疑的组合。

## 逐项复测

### ✅ 法人姓名映射 — 已确认修复，稳定

对照基准：营业执照（`document_id=38`）`legal_person: "郭斌"`。

| 场景 | doc_type | 字段 | 结果 | 命中 |
|---|---|---|---|---|
| 授权书 ×4 次 | authorization | authorizer_legal_person | 郭斌（4次全部一致） | ✅ |
| 招标文件 | bid-document | contact_person | 郭斌 | ✅ |
| 身份证 ×3 次 | id-card | name | 郭斌（3次全部一致） | ✅ |

法人姓名这一路径的映射（覆盖 `authorizer_legal_person`/`contact_person`/`name` 三个别名）稳定生效，不再是随机值。此前第三轮反馈的问题在此层面已解决。

### ✅ 地址映射 — 在身份证模板上生效，但在合同模板上未生效（不一致）

对照基准：营业执照 `address: "陕西省深圳市天河区天河路54号"`。

| 场景 | doc_type | 字段 | 结果 | 命中 |
|---|---|---|---|---|
| 身份证 ×2 次 | id-card | address | 陕西省深圳市天河区天河路54号（2次全部一致） | ✅ |
| 合同 ×3 次 | contract | party_b_address | 广东省北京市浦东新区南京路184号 / 上海市深圳市洪山区天河路175号 / 浙江省北京市南山区天河路126号（每次不同） | ❌ |

同一个 `address` 别名映射，`id-card.address` 生效了，但 `contract.party_a_address`/`party_b_address`（Hub 团队第三轮回复里明确列出的两个别名字段）完全没生效——3 次调用 3 个不同随机地址，无一次复用营业执照地址。

**怀疑方向**：是否 `party_a_address`/`party_b_address` 这两个字段名的映射规则本身没有实际接入代码（可能列在设计文档/别名表里，但实现时漏掉了这两个），而 `id-card.address` 走的是另一条已生效的路径（比如直接同名字段 `address` 的通用匹配）？建议 Hub 团队针对 `contract` 模板单独排查。

**附带小问题（非本次映射范围，但影响真实感）**：合同模板生成的随机地址存在"省市重叠"的逻辑错误，如"广东省北京市浦东新区南京路184号""浙江省北京市南山区天河路126号"——省份与城市不匹配，一眼能看出是拼接生成。这是地址随机生成逻辑本身的问题，与本次一致性映射无关，但既然发现了一并反馈，供 Hub 团队评估是否值得顺手修一下（影响 mock 材料的"看起来像真的"程度）。

### ⚠️ 新发现：法人姓名映射生效后，衍生出"姓名-性别不一致"问题

身份证模板（`id-card`）复用了法人姓名"郭斌"，但 `gender` 字段仍是独立随机生成，3 次测试全部返回 `"gender": "女"`（与"郭斌"这个姓名在常见性别认知上冲突，虽非绝对——但结合业务场景，法定代表人身份证上姓名和性别本该是同一个人的两个属性，理论上应该在生成时联动，而不是"姓名从别处复用，性别照常随机"）。

**风险说明**：这类"字段各自独立随机、缺乏同一份材料内部的属性联动"的问题，比之前"公司名不一致"更隐蔽——因为姓名本身是对的（复用了正确的法人），materials 看起来"大部分对"，容易被忽略，但一旦被认真核对（比如对照工商登记信息里法人的性别），反而比明显的公司名错配更难被察觉后信任度反而更低。

**建议**：这类需要"同一自然人多个属性联动"的字段（姓名+性别、姓名+身份证号中的性别码位等），建议作为独立的一类问题在 Hub 内部登记跟进，不需要现在马上处理，但建议纳入排查范围，避免后续再次以"字段级"补丁的方式逐个发现。

## 本轮测试产生的新数据（供清理）

| document_id | doc_type | entity_name | 用途 |
|---|---|---|---|
| 50-53 | authorization | 测试验证科技有限公司 | 法人映射复测（4次） |
| 54, 55, 及若干未记录id | contract | 测试验证科技有限公司 | 地址映射复测（约5次） |
| （未记录id） | qualification-cert / bid-document / technical-doc / invoice / acceptance-report / id-card ×3 / education-cert / professional-cert | 测试验证科技有限公司 | 查找 credit_code 字段 + 身份证映射复测 |

均为测试数据，非真实项目材料。

## 下一步

1. 请 Hub 团队排查 `contract` 模板的 `party_a_address`/`party_b_address` 映射为何未生效（对照 `id-card.address` 已生效的实现，确认两者是否走了不同代码路径）。
2. 信用代码（`credit_code`）映射本轮仍未找到对应字段的模板出现该 key（测试了 qualification-cert/bid-document/technical-doc/invoice/acceptance-report/id-card/education-cert/professional-cert，均无 `credit_code` 字段），麻烦 Hub 团队直接告知哪个 `doc_type_code` 会返回此字段，以便针对性复测。
3. 姓名-性别联动问题记录在案，不阻塞本轮核心映射的验收结论，但建议后续处理。

在地址映射（至少覆盖到合同这类高频模板）修复前，SmartBid 侧继续暂缓正式接入；法人姓名映射本身已可用于我们侧的进一步集成设计讨论。
