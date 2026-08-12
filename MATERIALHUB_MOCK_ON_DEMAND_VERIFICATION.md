# MaterialHub 按需 Mock 生成 — 验收测试反馈

测试时间：2026-08-01
测试方：SmartBid 团队
被测环境：`https://material.senseflow.club`（部署 commit `8369395`）
依据文档：`MATERIALHUB_MOCK_ON_DEMAND.md`

## 结论

4 项需求中 3 项验证通过，**1 项（实体一致性）实测失败**，另发现 1 处接口细节与文档不符、1 项因测试条件限制未能验证。建议修复实体一致性问题后再接入 SmartBid 生产流程——这是本次需求最核心的安全约束，一旦失效，标书里会出现"营业执照公司名 A、认证证书公司名 B"这类一眼假的矛盾，比"占位符留空"风险更高。

## 逐项结果

### ✅ 1. 按需生成接口 — 可用，但路径与文档不符

请求：
```
POST /api/v2/mock/generate-on-demand
{
  "doc_type_code": "iso-cert",
  "entity_name": "星辰科技有限公司",
  "requirement_context": {
    "tender_project": "测试项目 TEST-001",
    "requirement_text": "投标人须具备ISO27001信息安全管理体系认证",
    "constraints": {"cert_name": "ISO/IEC 27001"}
  },
  "folder_path": "/公司资质/资质证书/"
}
```

返回 200，含 `document_id`、`requires_user_replacement: true`、`mock_data`。功能可用。

**路径确认**：实际路径是 `/api/v2/mock/generate-on-demand`，与原需求文档草案里写的 `/api/v2/documents/mock-generate` 不同——以 Hub 团队实现的路径为准，SmartBid 侧会按此对接。

**耗时提示**：首次调用耗时约 1.6s，接入方需注意超时设置（我们最初用 8s 超时测出了假的连接失败，实际是慢响应不是接口不可用）。

### ⚠️ 2. `folder_path` 参数似乎被忽略

请求中传了 `folder_path: "/公司资质/资质证书/"`，但生成文档实际落在了 `folder_id: 7`（"ISO认证"文件夹，路径 `/公司资质/iso认证/`），并非请求中指定的"资质证书"文件夹。

看起来系统是按 `doc_type_code` 自动路由到对应文件夹，忽略了显式传入的 `folder_path`。

**需要确认**：这是否是设计意图（每个 doc_type 有固定归属文件夹，不允许调用方指定）？如果是，建议接口层面直接不接受这个参数（或接受但在返回体里明确告知"已按 doc_type 自动归类，folder_path 被忽略”），避免调用方以为传了就会生效。

### ✅ 3. `mock_reason` 过滤查询 — 可用，但有一个重定向细节

请求：
```
GET /api/v2/documents?mock_reason=generated_for_requirement&status=active
```

不带尾部斜杠的 `/api/v2/documents` 返回 **307 重定向**到 `/api/v2/documents/`（带斜杠）。带斜杠或让 HTTP 客户端自动跟随重定向后，查询结果正确，只返回了本次生成的那份文档，字段完整（`metadata.mock_reason`、`requirement_context` 原样回填）。

**建议**：文档里注明规范路径带尾部斜杠，避免接入方因未跟随重定向（很多严格模式的 HTTP 客户端默认不跟随跨方法重定向）而误判为查询失败。

### ⚠️ 4. 替换后自动清除 mock 标记 — 未验证

受限于测试条件（需要走真实文件上传 + revision 替换流程，我们这轮只做了只读+生成类接口的验证），本次未能验证"用户上传真实材料后 `metadata.mock`/`mock_reason`/`requires_user_replacement` 是否被自动清除"。

**待办**：请 Hub 团队提供一个可复现的验证路径（如具体的 revision 创建接口 + 调用示例），我们补测一次再确认此项。

### ❌ 5. 实体一致性 — 验证失败（核心问题）

**这是本次测试发现的主要问题。**

测试步骤：
1. 库中已有 `entity_name: "星辰科技有限公司"` 的营业执照（document id=1），`extracted_data` 里法人为"林晓峰"。
2. 调用生成接口，显式传入 `entity_name: "星辰科技有限公司"`，请求生成 ISO 认证证书。
3. 返回的证书 `extracted_data.company_name` 字段却是 **"华信信息技术有限公司"**——与请求的 `entity_name` 完全不同、也和库内已有该公司的营业执照对不上。

返回原文（关键字段）：
```json
{
  "entity_name（请求参数）": "星辰科技有限公司",
  "mock_data.company_name（返回结果）": "华信信息技术有限公司"
}
```

**为什么这是关键问题**：需求文档第 3.1 节明确要求"同一 `entity_name` 多次生成材料时，公司基础字段必须与该实体已有材料保持一致"，这是防止标书出现自相矛盾材料的核心机制。当前实现看起来完全没有读取/复用已有实体属性，而是每次生成随机公司名——这比"不生成、留空占位符"更危险：用户如果没有逐字核对每份证书上的公司名，很可能把写着"华信信息技术有限公司"的 ISO 证书和写着"星辰科技有限公司"的营业执照一起提交。

**幂等性附带观察**：同一参数二次调用返回了同一个 `document_id`（幂等本身有效），但第一次生成时的公司名错误会被"缓存"复用，不会随后续调用自我纠正——所以幂等设计目前是把错误结果也一起固化下来了。

**建议排查方向**：生成逻辑在写入 `mock_data.company_name` 前，是否有查询该 `entity_name` 在库中已有属性（如营业执照的 `extracted_data.company_name`）并复用的步骤？从结果看，这一步可能完全没有执行，或者查询逻辑本身有 bug（比如没有正确匹配到已存在的实体）。

## 下一步

在实体一致性问题修复并复测通过之前，SmartBid 侧暂缓将此接口接入 `bid-material-search` skill 的正式调用链——先接入意味着一旦上线就可能直接影响标书内容准确性，建议先修好再对接。

麻烦确认：
1. 实体一致性 bug 的修复计划/时间
2. `folder_path` 参数的预期行为（忽略 vs 生效）
3. revision 替换清除标记的验证方式，方便我们补测第 4 项
