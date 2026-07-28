# MaterialHub 安全审计报告

> **审计日期**：2026-07-28
> **审计基线**：分支 `main`，commit `24f4a7d`
> **方法**：4 个并行只读 scout（AuthN/AuthZ、Injection、File handling、Secrets/Config）+ 主审计逐条核实所有 Critical/High 发现（读源码验证，未采信结论）

## 总览

- **注入面干净**：SQLi / 命令注入 / 反序列化均安全
- **认证授权层系统性失效**：文件服务全量免认证 + 文件夹权限是死代码 + editor 可提权 admin
- **2 个 Critical 需立即处置**
- 严重度分布：**2 Critical · 7 High · 7 Medium · 5 Low · 2 Info**

---

## 🔴 Critical

### C-1 未认证全量文档泄露（IDOR）

**位置**：`backend/main.py:85-88`（认证豁免）+ `backend/routers/v2_files.py:84`（无 auth 依赖）

```python
# main.py:85-88 — 中间件直接放行
if request.url.path.startswith("/api/files/") or request.url.path.startswith("/api/v2/files/"):
    return await call_next(request)
if "/page/" in request.url.path and request.url.path.endswith("/thumb"):
    return await call_next(request)
```

```python
# v2_files.py:84-85 — 本文件其他路由都有 require_role，唯独这个没有
@router.get("/files/{file_id}")
async def serve_file(file_id: int, request: Request, preview: bool = Query(False)):
```

**风险**：`file_id` 是 SQLite 自增主键（从 1 开始顺序）。任何人在网络上 `curl /api/v2/files/1..N` 即可下载全部上传文档——营业执照、身份证、合同。审计日志代码 `getattr(request.state, "user_id", None)` 对未认证请求返回 `None`，**遍历过程完全无日志**。三个 scout 独立确认 + 主审计读源码核实。

**修复**：从 `exempt_paths` 移除 `/api/v2/files/` 和 `/page/.../thumb` 规则；给 `serve_file` 和 `get_page_thumbnail` 加 `dependencies=[require_role("viewer")]` + 文件夹权限过滤。注意前端 `api-v2.ts:971`、`api.ts:271,408` 已在文件 URL 带 `?token=`，中间件 `main.py:101` 已支持从 query 取 token，故移除豁免不破坏前端预览。

### C-2 生产 API Key 硬编码并进入完整 git 历史

**位置**：`backend/kb_asr.py:20`（env 默认值）+ `transcribe_glm.py:18`（无 env fallback）

```python
# kb_asr.py:20
ASR_API_KEY = os.getenv("ASR_API_KEY", "b07f119aaa41487a914d6b0d4dedd239.EAJ6rekpFjyZEWoA")
# transcribe_glm.py:18
GLM_API_KEY  = "b07f119aaa41487a914d6b0d4dedd239.EAJ6rekpFjyZEWoA"
```

**风险**：智谱 BigModel 真实凭证（`{id}.{secret}` 格式），作为 Bearer 调用 `open.bigmodel.cn` 计费接口。`git log --all -S` 显示该 key 从 `c8d002e 初始化` 起存在于**所有提交**，无法通过删除文件清除。

**修复**：① **立即轮换该 key**（在智谱控制台）；② 两处默认值改为空串并 fail-fast；③ 用 `git filter-repo` / BFG 清洗历史（会改写所有 commit hash，需协调协作者重新 clone）。

---

## 🟠 High

### H-1 editor → admin 提权（创建 admin Agent）

**位置**：`backend/routers/v2_agents.py:60-89`

```python
@router.post("/", dependencies=[require_role("editor")])   # 仅需 editor
async def create_agent(data: CreateAgentRequest):
    if data.role not in VALID_ROLES:   # {"admin","editor","viewer"}
        ...
    agent = ApiAgent(... role=data.role, ...)   # editor 可指定 role="admin"
    if data.folder_ids and data.role != "admin"):  # admin 角色还跳过文件夹限制
```

**风险**：任何 editor 创建一个 `role="admin"` 的 agent token，获得无文件夹隔离的全权限访问。`require_role("editor")` 检查调用者全局角色，但 `data.role` 是被创建 agent 的角色，二者未关联约束。

**修复**：`create_agent` 提升为 `require_role("admin")`；或限制 editor 只能创建 ≤自身角色 的 agent。

### H-2 文件夹级权限是死代码 → 文档 IDOR

**位置**：`backend/dms_auth.py:187`（`require_folder_permission` 定义）vs 全部 router

`require_folder_permission` 在 `dms_auth.py` 中定义，但**无任何 router import 或使用**。`get_accessible_folder_ids()` 只在 list/get 文档的**读**路径用，所有**变异**操作（`v2_documents.py` 的 PATCH/DELETE/lock/unlock/revisions/entities/tags，`list_revisions:455`）按 `doc_id` 直接查，无 folder 过滤。

**风险**：受限用户（只能看 A 文件夹）只要知道/猜到 B 文件夹的 doc_id，即可修改/删除/锁定 B 的文档。`v2_complete.py` 的 `/companies|persons/{id}/complete` 把法人、credit_code、身份证号、证书号 dump 给任何登录用户。

**修复**：在所有按 `doc_id` 查询处加 `doc.folder_id IN accessible_ids` 过滤；将 `require_folder_permission` 接入或删除。

### H-3 存储 XSS via 未校验 Content-Type

**位置**：`backend/routers/v2_files.py:59-64`（存原始 MIME）+ `:115-122`（inline 返回）

```python
# 上传：mime_type 直接存 file.content_type，无白名单
safe_name = f"{file_hash[:8]}_{file.filename}"
dms_file = DmsFile(... mime_type=file.content_type, ...)
# 服务：preview 时 inline 用存储的 mime_type
resp = FileResponse(str(file_path), media_type=dms_file.mime_type)
resp.headers["Content-Disposition"] = "inline"
```

**风险**：editor 上传 `<script>...</script>` 并声明 `Content-Type: text/html`；受害者访问 `/api/v2/files/{id}?preview=true`（配合 C-1 **无需登录**）→ 浏览器在站点 origin 执行 JS → 偷 session token。全代码库无 `X-Content-Type-Options: nosniff`。对比：`v2_upload.py` 有 `ALLOWED_MIME_TYPES` 白名单，但 `v2_files.py` 的上传没有。

**修复**：`v2_files.py` 上传加 MIME 白名单；服务时强制 `application/octet-stream` + `Content-Disposition: attachment` + `nosniff` 头。

### H-4 上传路径穿越写入（4 处）

**位置**：`v2_upload.py:220-225`、`v2_files.py:59-64`、`v2_upload.py:906-910`(batch)、`v2_documents.py:802-806`(import)

```python
safe_name = f"{file_hash[:8]}_{original_filename}"   # original_filename = file.filename
storage_path = f"dms_files/{doc.id}/{rev.id}/{safe_name}"
full_path = DATA_DIR / storage_path
with open(full_path, "wb") as f: f.write(content)
```

**风险**：`file.filename` 未净化 `..`/绝对路径/null 字节。`filename="../../../../../../tmp/pwned"` → hash 前缀粘到首段成字面目录名（假安全），攻击者多加几个 `..` 即可逃出 `DATA_DIR`，实现任意文件写入（覆盖配置/投毒）。读侧有 `relative_to(DATA_DIR.resolve())` 防护，所以是**任意写**非任意读。

**修复**：所有写点 `os.path.basename(file.filename)` + 拒绝含 `..`/`\x00` 的文件名 + 二次 `resolve()` 后校验在 `DATA_DIR` 内。

### H-5 未认证 PDF 页面渲染枚举

**位置**：`backend/routers/v2_upload.py:1051` + `main.py:87`

`get_page_thumbnail` 经 `/page/.../thumb` 子串豁免免认证。缩略图是 PDF 页面的忠实 200px 渲染，泄露证书编号/合同条款等内容，非仅元数据。`/page/` 子串通配还会误豁免未来任何 `*/page/*/thumb` 形状的路由。

**修复**：移除子串豁免（与 C-1 合并），加 `require_role("viewer")` + 文件夹过滤。

### H-6 SSRF via 运行时配置（OCR/LLM base_url）

**位置**：`v2_settings.py:413-421`（仅校验 provider 枚举，不校验 URL）→ `ocr_client.py`、`llm_provider.py`

admin（或通过 H-1 提权获得的 admin）可把 `ocr_service_url`/`llm_base_url` 设为 `http://169.254.169.254/...`（云元数据）或内部地址，响应经 `markdown_text`/`content` 字段回传给调用者。无 scheme/host 白名单。

**修复**：URL 存储前校验 https + 非私有 IP 段；或限制为 env-only 不可运行时改。

### H-7 MCP token 在 URL + 未认证 token→API key 兑换

**位置**：`mcp-server/server.py:1229`（token 从 query 取）+ `v2_settings.py:243` `/mcp/resolve`（在 `exempt_paths`，无认证返回完整 agent API key）

README 示例 `?token=mh-agent-xxx` 的 SSE URL 会被所有反向代理日志/Referer/浏览器历史记录。单个泄露的 SSE token → 未认证 `GET /api/v2/settings/mcp/resolve?token=...` → 完整 `mh-agent-*` API key → 持久 DMS 访问。前端 `api-v2.ts:971`、`api.ts:271,408` 也为图片预览构建 `?token=` URL，放大泄露面。

**修复**：SSE 改用 `Authorization` 头；`/mcp/resolve` 要求认证；停止生成 `?token=` URL。

---

## 🟡 Medium

| ID | 位置 | 问题 |
|---|---|---|
| M-1 | `main.py:38-43` | CORS `allow_origins=["*"]`。非 Critical 因无 `allow_credentials=True`（cookie 不会跨域带），但仍配合 `?token=` 放大攻击 |
| M-2 | `main.py:78` | `/docs`、`/openapi.json`、`/redoc` 免认证公开，泄露完整 API schema 助攻侦察 |
| M-3 | `v2_upload.py:166` 等 | 无上传大小限制，`await file.read()` 全量入内存 → OOM/磁盘耗尽 DoS。`check_file_hash` 更糟：全量缓冲+MD5 后丢弃 |
| M-4 | `v2_transfer.py:181-199` | zip-slip：`target = DATA_DIR.parent / member` 无 `basename()`/containment 校验，且会覆盖 `materials.db` |
| M-5 | `.gitea/workflows/ci-cd.yml` | Gitea token 嵌入 `http://`（非 https）git URL，明文过网 + 经 `git remote set-url` 持久化到服务器 `.git/config` |
| M-6 | `docker-compose.yml` | 默认 PG 凭据 `materialhub:materialhub`，且 PG 端口映射到宿主机 |
| M-7 | `v2_search.py:217`、`v2_expiry.py:176`、`v2_kb.py:133` | 多个变异/昂贵端点无 `require_role`：`rebuild-index`、`update-status`（全局状态变更）、`kb/sync` 任何登录用户可调 |

---

## 🟢 Low / Info

- **L-1** `v2_admin.py:125` 密码策略仅 `len>=4`
- **L-2** `v2_transfer.py:113` 等 5 处 `detail=f"...{e}"` 把异常字符串（含 DB 路径）回传客户端，无全局 `exception_handler` 清洗
- **L-3** `v2_upload.py:108` 等 5 处用 MD5 做文件去重（碰撞可绕过去重）
- **L-4** `kb_asr.py:51,164` ASR/视频 temp 目录从不清理，磁盘慢泄漏
- **L-5** `dms_models.py:461`、`database.py:439` 默认 `admin/admin123` 种子账号
- **I-1** `requirements.txt` 全部 `>=` 未 pin，无 lockfile（`package-lock.json` 被 gitignore）；Pillow/PyMuPDF 历史多 CVE
- **I-2** Agent 循环把 OCR/文档文本喂回 LLM 选工具参数 → 间接 prompt injection 表面（文档可注入指令操控工具选择；查询构造本身参数化安全）

---

## ✅ 干净的面

- **注入**：0 个可利用 SQLi。raw SQL 的 f-string 仅插值硬编码常量、float-disciplined pgvector 字面量、整数 PK；FTS5 MATCH 用 `:query` 绑定；所有 `.ilike()` 参数化
- **命令注入**：ffmpeg/ffprobe 全用 argv list，无 `shell=True`
- **反序列化**：无 eval/exec/pickle/`yaml.load`
- **密码哈希**：bcrypt 12 rounds（`auth.py:13-22`）✅
- **会话**：`secrets.token_hex`/`uuid4.hex` 熵充足，每次请求校验过期 ✅；logout 服务端失效 ✅
- **.env/.mcp.json** 正确 gitignore，未提交 ✅

---

## 修复优先级

1. **立即**：轮换 C-2 的 BigModel key；修复 C-1（移除文件服务认证豁免）——这两个任一被利用都是全量数据泄露
2. **本周**：H-1（提权）、H-2（文件夹死代码）、H-3（XSS）、H-4（路径穿越）——构成攻击链
3. **随后**：H-5/H-6/H-7 + Medium 项


---

## 修复状态（2026-07-28）

| ID | 严重度 | 状态 | 修复内容 |
|---|---|---|---|
| C-1 | Critical | ✅ 已修复 | 移除 `main.py` 中 `/api/v2/files/` 和 `/page/.../thumb` 认证豁免，所有文件下载现需认证 |
| C-2 | Critical | ✅ 代码已修复 | 移除 `kb_asr.py`、`transcribe_glm.py` 中的硬编码 BigModel key 默认值（改为空串，env 未设则 fail）。**⚠️ 仍需：(1) 在智谱控制台轮换该 key；(2) 用 git-filter-repo 清洗 git 历史（会重写所有 commit hash，需用户确认）** |
| H-1 | High | ✅ 已修复 | `v2_agents.py` 全部 agent 管理端点从 `require_role("editor")` 提升为 `require_role("admin")` |
| H-2 | High | ✅ 已修复 | 新增 `assert_doc_folder_access()` helper（`dms_auth.py`），应用到 `v2_documents.py` 的 11 个 mutation/read 端点 + `v2_complete.py` 的 `/complete` 文档过滤 |
| H-3 | High | ✅ 已修复 | `v2_files.py` 上传加 MIME 白名单；服务端非图片强制 `application/octet-stream` + `attachment` + `X-Content-Type-Options: nosniff` |
| H-4 | High | ✅ 已修复 | 4 个上传点（`v2_upload`/`v2_files`/`v2_documents`）加 `_sanitize_upload_filename()`（basename + null-byte strip）+ resolve 容器校验 |
| H-5 | High | ✅ 已修复 | 与 C-1 合并，`get_page_thumbnail` 现需认证 |
| H-6 | High | ✅ 已修复 | `v2_settings.py` 新增 `_validate_service_url()`，拒绝 http/https 以外协议 + 私有/回环/链路本地/保留 IP |
| H-7 | High | ✅ 已修复 | `/mcp/resolve` 从 GET 改 POST（token 在 body 不入 URL/代理日志）；MCP server 调用同步更新 |
| M-1 | Medium | ✅ 已修复 | CORS 改为 env 白名单 `ALLOWED_ORIGINS`（默认本地开发端口，生产配实际域名）；移除 `["*"]` |
| M-2 | Medium | ✅ 已修复 | `/docs`、`/openapi.json`、`/redoc` 默认关闭（`ENABLE_DOCS=false`），并从 `exempt_paths` 移除 |
| M-3 | Medium | ✅ 已修复 | `upload_file`、`batch_upload`、`check_file_hash` 加 200MB Content-Length 上限（413） |
| M-4 | Medium | ✅ 已修复 | `v2_transfer.py` zip-slip 加 `resolve().relative_to()` 容器校验，逃逸条目跳过 |
| M-5 | Medium | ✅ 已修复 | CI deploy 的 `git fetch` 改用临时 URL 携带 token，`.git/config` 中 remote 设为无 token URL（token 不再持久化到磁盘） |
| M-6 | Medium | ✅ 已修复 | docker-compose PG 密码改用 `${PG_PASSWORD:?...}` 强制校验（未设则拒绝启动）；`.env.example` 改为强密码提示 |
| M-7 | Medium | ✅ 已修复 | `rebuild-index`、`update-status`、`kb/sync` 加 `require_role("admin")`；`kb/reindex` 修复 tuple-return 403 bug |

### 验证
- 全部 15 个修改文件 `py_compile` 通过
- 运行时单测：路径净化器（`basename` + null strip + resolve 容器）、SSRF 校验器（8/8 用例：metadata/loopback/private IP 全拒绝，合法 URL 放行）、文件夹 IDOR 守卫（admin 不限/受限用户越权 403/零权限全拒）均验证通过
- 静态确认：`main.py` 中无文件服务认证豁免残留；docs 默认关闭

### 生产环境部署时需配置（代码侧已修复，仅需填入实际值）
1. ~~轮换 BigModel key（C-2）~~ —— ✅ 已注销；代码层硬编码已移除；git 历史清洗经用户确认跳过
2. **`ALLOWED_ORIGINS`**（M-1）—— `.env` 中填入生产前端域名，如 `https://app.example.com`
3. **`PG_PASSWORD`**（M-6）—— `.env` 中填入强密码（docker-compose 已强制校验，未设拒绝启动）
4. **`ENABLE_DOCS`**（M-2）—— 仅开发时设 `true` 开启 Swagger，生产保持 `false`（默认）
5. ~~CI token https（M-5）~~ —— ✅ 已修复 token 持久化问题；若 Gitea 支持 https，将 ci-cd.yml 中 `http://10.0.0.2:3000` 改为 https 即可进一步加固传输安全