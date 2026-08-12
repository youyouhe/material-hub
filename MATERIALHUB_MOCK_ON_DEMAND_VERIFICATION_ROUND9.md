# MaterialHub — 生产环境紧急问题反馈（第九轮，非本次白名单验证结果）

测试时间：2026-08-01
测试方：SmartBid 团队
背景：Hub 团队反馈 revisions POST 401 根因怀疑是"异步中间件调同步 SQLite session 时序问题"，计划把 revisions POST 加入 agent token 白名单临时测通，并提到"host 停在 c0d3767，debug commit 没同步过来"。

## 结论：这次发现的问题比 revisions 白名单更紧急——生产域名 `https://material.senseflow.club` 下 `/api/v2/*` 全部返回 404，服务对外实质不可用

在复测白名单是否生效之前，例行确认基线时发现：**不止 `revisions` 端点，`/api/v2/` 下所有此前验证通过的端点（包括 `entities/`、`doc-types/`、`documents/{id}`、`mock/generate-on-demand`、`folders/tree`）在公网域名下全部返回 404**。这个问题的影响范围和优先级都高于本轮要验证的白名单/401 问题，建议先处理这个。

## 关键证据：应用层正常，代理层路由丢失

| 访问路径 | 从公网域名访问 | 从 VPS 本机 `127.0.0.1:8101` 直连 |
|---|---|---|
| `/health` | 200 | 200 |
| `/api/v2/documents/1` | **404** | **200** |
| `/api/v2/entities/` | **404** | **200** |
| `/api/v2/search` | **404** | **200** |
| `/api/v2/folders/tree` | **404** | **200** |
| `/api/v2/mock/generate-on-demand`（POST） | **404** | 未测（应用层已确认健康，此路径此前在公网多轮验证通过） |
| `/docs` | 200，但返回前端 SPA 的 index.html（不是 FastAPI 文档页） | 404 |

**结论**：VPS 上 `127.0.0.1:8101` 的后端应用本身完全健康，所有 `/api/v2/*` 路径都能正确响应。问题出在对外域名 `material.senseflow.club` 前面的反向代理/CDN 层——它似乎把 `/api/v2/*` 当作"未匹配路由"处理，而不是转发给后端 8101 端口；同时 `/docs` 等路径被代理的 SPA fallback 规则接住返回了前端页面而非真正到达后端。这与"revisions 端点 401 认证判定"是完全不同层面的问题，且影响范围是全部 API，不只是 revisions。

## 怀疑与"host 停在 c0d3767"的关联

Hub 团队提到"host 停在 c0d3767，debug commit 没同步过来"——如果这次的"停留"或"回退"操作连带影响了反向代理的路由配置文件（比如 Caddy/Nginx 的 `/api/v2` 转发规则跟着某次部署脚本一起被回退/重置），有可能是本次发现的根因。建议按此方向优先排查代理层配置，而不是继续在应用代码里找 revisions 认证问题——目前应用代码可能完全没问题，只是外部请求根本没到达它。

## 对本轮验证任务的影响

由于 `/api/v2/*` 公网不可达，本轮"revisions POST 加白名单"的验证无法进行——白名单加不加，外部请求现在都到不了后端。建议 Hub 团队：

1. 优先修复代理层路由问题，恢复 `/api/v2/*` 对外可达。
2. 修复后我们会先做一次全量基线回归（用此前几轮验证过的一批端点，如 `mock/generate-on-demand`、`entities/`、`doc-types/`），确认没有引入新的broken，再继续本轮 revisions 白名单验证。

## 备注

这次没有等到白名单生效就先撞上了这个更基础的问题，所以尚未能提供"revisions 白名单是否解决了 401"的直接结论——望理解，这不是我们绕过了 Hub 的验证请求，是环境目前对外不可达，无法执行任何进一步测试。
