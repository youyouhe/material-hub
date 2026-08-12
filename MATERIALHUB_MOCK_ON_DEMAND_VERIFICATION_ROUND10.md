# MaterialHub 按需 Mock 生成 — Revision 替换验证反馈（第十轮）

测试时间：2026-08-01
测试方：SmartBid 团队
背景：Hub 团队反馈 Caddy 反向代理配置已修复（`handle_path` 误剥离 `/api` 前缀，改为 `handle`），请 SmartBid 复测 `/api/v2/*` 基线 + revisions 401 问题。

## 结论：代理修复已确认生效；revisions 401 依然稳定复现，且非偶发性

## 1. ✅ 代理层修复确认

基线回归全部恢复 200：

| 路径 | 结果 |
|---|---|
| `/api/v2/documents/1` | 200 |
| `/api/v2/entities/` | 200 |
| `/api/v2/doc-types/` | 200 |
| `/api/v2/folders/tree` | 200 |

上一轮反馈的"公网 `/api/v2/*` 全部 404"问题已解决，感谢排查。

## 2. `mock/generate-on-demand` 端点确认正常

用新实体"验证九号科技有限公司"生成营业执照，返回 200，`document_id=76`，`requires_user_replacement: true`，字段完整——此前几轮验收过的核心功能未受代理问题影响。

## 3. ❌ `POST /api/v2/documents/{id}/revisions/` 仍返回 401，稳定复现（非偶发）

对新生成的文档 76 执行验证步骤：

```bash
curl -X POST https://material.senseflow.club/api/v2/documents/76/revisions/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"change_note": "替换为真实材料"}'
```
返回：
```json
{"detail":"Not authenticated"}
```
HTTP 401。

**关键测试——连续 5 次重试，排除"异步中间件调同步 SQLite session 时序问题"这一假设**：

| 尝试 | 结果 |
|---|---|
| 1 | 401 |
| 2 | 401 |
| 3 | 401 |
| 4 | 401 |
| 5 | 401 |

5 次连续调用（间隔 1 秒），**100% 复现 401，没有一次成功**。如果根因确实是"偶发的异步/同步时序竞态"，理论上应该有一定概率通过；但目前观察到的是确定性失败，每次都不过。这提示两种可能：
1. Hub 团队计划的"revisions POST 加入 agent token 白名单"这个改动**尚未实际部署到 `material.senseflow.club` 这个环境**（比如改了代码但还没同步/重启，类似上次"host 停在 c0d3767"的情况）；
2. 或者白名单改动已部署，但没有覆盖到实际被触发的代码路径（比如中间件匹配规则写的路径和真实路由不完全一致）。

**对照**：同一 token，在 `mock/generate-on-demand`（另一个写操作端点）上认证始终正常（本轮和此前所有轮次均如此）——如果 revisions 端点的 401 真是"通用的异步/同步时序竞态"，理论上应该在其他写端点上也偶发出现，但从未观察到 `mock/generate-on-demand` 失败过。这进一步支持"revisions 端点有自己独立的认证配置路径，与其他端点不同"这个此前几轮就提出的怀疑，而不是一个全局性的、偶发的中间件时序问题。

## 建议

在花时间深挖"异步中间件时序竞态"这个假设之前，建议先确认：**白名单改动是否已经真正部署并生效在 `material.senseflow.club` 上**？可以用一个最简单的判断——如果确实是概率性的时序问题，理论上多次重试至少应该有一次成功；但我们这边 5 次全部失败，更像是"改动没生效"而不是"改动生效了但有时序问题"。

如果确认已部署，那么下一步建议直接对比 revisions 端点和 mock/generate-on-demand 端点在中间件层的路由注册代码，看两者的认证装饰器/依赖注入方式是否有实质差异（比如一个用了 `Depends(get_current_agent)`、另一个用了别的依赖，或者路径匹配的正则/前缀不一致导致中间件白名单规则没匹配上这条路由）。

## 下一步

麻烦确认部署状态后再同步，我们会继续用文档 76 做验证（该文档目前仍是 `mock: true` 状态，未消耗，可复用）。
