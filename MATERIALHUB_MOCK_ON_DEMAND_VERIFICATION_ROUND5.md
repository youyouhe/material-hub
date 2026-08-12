# MaterialHub 按需 Mock 生成 — 复测反馈（第五轮）

测试时间：2026-08-01
测试方：SmartBid 团队
背景：Hub 团队反馈 (1) `contract.party_b_address` 应已复用营业执照 address；(2) `credit_code` 验证项可关闭（16 个模板均无此字段名，映射表为预留，不阻塞验收）；(3) 姓名-性别联动记录为已知限制，不阻塞验收。

## 结论：本轮复测被阻断——`mock/generate-on-demand` 接口 500 报错，服务不可用

复测 `contract.party_b_address` 时，接口稳定返回 500：

```json
{"detail":"name 'img_filename' is not defined"}
```

进一步排查发现**不止 `contract` 受影响，`authorization` 同样报同一个错**——怀疑是全局性回归，本次部署的改动导致整个 `mock/generate-on-demand` 端点当前不可用，而非单个模板的问题。

## 复现详情

| 请求 | doc_type_code | 结果 |
|---|---|---|
| 1 | contract | 500 `name 'img_filename' is not defined` |
| 2（重试） | contract | 500，同错误 |
| 3（重试） | contract | 500，同错误 |
| 4（换模板排查范围） | authorization | 500，同错误 |

4 次调用，4 次稳定复现同一报错，非偶发。

## 排除环境/服务本身问题

已确认以下均正常，问题精确定位在该接口本身：

- `GET /health`（应用层）→ `{"status":"healthy","service":"MaterialHub"}`，200
- VPS 层 `curl 127.0.0.1:8101/health` → 同上，200
- 只读接口 `GET /api/v2/documents/38` → 200，数据正常返回

## 关于其余两点回复的确认

1. **`credit_code` 验证项** — 同意关闭，不再要求本轮验收覆盖此字段，待后续有实际使用该字段名的模板再测。
2. **姓名-性别联动** — 同意记录为已知限制，不阻塞本轮验收。

以上两点无需进一步动作，仅在此确认收到并达成一致。

## 下一步

`mock/generate-on-demand` 端点当前 500 全量不可用，是阻断性问题，优先级高于地址映射验证本身——麻烦 Hub 团队先修复此回归（看报错信息像是某处代码引用了未定义的 `img_filename` 变量，可能是这次改动里一个变量重命名/作用域改动漏改了引用点），我们收到修复通知后立即继续复测 `party_b_address` 映射。
