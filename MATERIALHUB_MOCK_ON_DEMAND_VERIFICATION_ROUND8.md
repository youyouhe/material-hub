# MaterialHub 按需 Mock 生成 — Revision 替换验证反馈（第八轮）

测试时间：2026-08-01
测试方：SmartBid 团队
背景：Hub 团队提供 `POST /api/v2/documents/{doc_id}/revisions/` 接口及验证步骤，用于测试"替换真实材料后 mock 标记自动清除"。

## 结论：验证被阻断——`POST .../revisions/` 返回 401，但同一 token 在 GET 上正常

按提供的步骤执行，`POST` 创建 revision 这一步本身就无法通过认证，尚未能测到"mock 标记是否清除"这一层。

## 复现详情

### Step 1（提供的验证步骤）：401

```bash
curl -X POST https://material.senseflow.club/api/v2/documents/38/revisions/ \
  -H "Authorization: Bearer mh-agent-059cce07a89150a2a2a7e0b73e2045f1e847a4ea726740f0" \
  -H "Content-Type: application/json" \
  -d '{"change_note": "替换为真实材料"}'
```
返回：
```json
{"detail":"Not authenticated"}
```
HTTP 401。

### 排查过程

1. **排除重定向丢 header 的可能**：不带尾部斜杠的 `POST .../revisions`（无斜杠）会先收到 307，`Location` 指向 `http://`（明文，非 https）——如果客户端跟随这个重定向，从 https 降级到 http 时通常会按安全策略丢弃 Authorization header，导致后续请求变成匿名请求。但即便直接用带斜杠的完整 https 路径发起请求（不经过任何重定向），依然是 401，说明这不是重定向降级导致的假象，是这个端点本身的认证判定问题。

   **附带反馈**：这个 307 跳转目标是 `http://`而非 `https://`，本身是一个独立的小问题，建议 Hub 团队顺手检查一下反向代理/框架配置，避免其他严格遵循"协议降级时丢弃敏感 header"策略的 HTTP 客户端（不止 curl，很多语言的标准库 HTTP 客户端都有此行为）在不知情的情况下认证失败。

2. **排除 token 本身失效**：同一个 Bearer token，在同一个资源路径上换成 `GET` 方法，认证通过、返回 200，且能正确取到该文档的 revision 历史：
   ```bash
   GET /api/v2/documents/38/revisions/
   → 200，正常返回 revisions 数组
   ```
   `GET /api/v2/documents/38`（文档详情）等其他既有接口，同一 token 也一直正常。

**结论**：Bearer token 本身有效，问题精确定位在 `POST /api/v2/documents/{id}/revisions/` 这一个端点的认证判定上——推测该写操作端点的认证中间件配置与其他端点（包括同路径的 GET、以及此前测试通过的 `mock/generate-on-demand`）不一致，可能被绑定成要求"用户 session 认证"而非我们一直使用的"agent Bearer token 认证"。

## 下一步

麻烦 Hub 团队排查 `POST /api/v2/documents/{id}/revisions/` 端点的认证配置，确认它是否应该接受与其他 API 端点相同的 Bearer token 认证方式。确认修复后，我们会按提供的验证步骤继续执行 Step 2（检查 `metadata.mock`/`mock_reason` 是否清除、标题中的 `（MOCK-待替换）` 是否移除）。

在此项验证通过之前，"替换后自动清除 mock 标记"仍是唯一未完成验收的需求项，其余各项（生成、幂等、过滤查询、实体一致性）均已在第一至第七轮验收通过。
