"""
MaterialHub MCP Server

Wraps MaterialHub search & document APIs as MCP tools,
enabling LLMs to search, browse, and retrieve document information.
"""

import os
import json
import logging
from typing import Any

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load env from project root
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("materialhub-mcp")

# Configuration
API_BASE = os.getenv("MATERIALHUB_API_URL", "http://localhost:8201")
API_READ_TOKEN = os.getenv("MATERIALHUB_API_KEY", "")       # Read agent: broad folder access
API_IMPORT_TOKEN = os.getenv("MATERIALHUB_IMPORT_KEY", "")   # Import agent: restricted folders

# Last resolved agent info (used by tool calls for auth)
_last_agent: dict = {}

mcp = FastMCP(
    "MaterialHub",
    instructions="MaterialHub 材料管理系统 - 搜索和查询企业资质文档、证书、合同等材料",
)

# Allow LAN access (disable DNS rebinding protection for IP access)
# 兼容 mcp 1.16+:settings.transport_security 默认 None,不能直接设其属性,需整体赋值
from mcp.server.transport_security import TransportSecuritySettings
mcp.settings.transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)

# ============================================================
# Context Protection: truncation helpers
# ============================================================

MAX_RESULTS = 30  # hard cap on list results
MAX_OCR_CHARS = 300  # max OCR text per document in search results
MAX_EXTRACTED_FIELDS = 20  # max extracted_data fields in search results


def _safe_limit(limit: int) -> int:
    return min(max(1, limit), MAX_RESULTS)



def _headers(token: str = "") -> dict:
    """Build request headers. Agent-resolved key takes priority over env fallback."""
    t = _last_agent.get("api_key", "") or token
    if not t:
        raise RuntimeError("No authenticated SSE session — tool called without prior token resolution")
    return {"Content-Type": "application/json", "Authorization": f"Bearer {t}"}


async def _get(path: str, params: dict | None = None) -> Any:
    """Make GET request to MaterialHub API (uses read token)."""
    async with httpx.AsyncClient(base_url=API_BASE, timeout=30) as client:
        resp = await client.get(path, params=params, headers=_headers(API_READ_TOKEN))
        resp.raise_for_status()
        return resp.json()


async def _post_file(path: str, file_path: str, form_data: dict) -> Any:
    """Upload a file via multipart POST to MaterialHub API (uses import token)."""
    import mimetypes
    mime, _ = mimetypes.guess_type(file_path)
    if not mime:
        mime = "application/octet-stream"

    headers = {}
    token = API_IMPORT_TOKEN or API_READ_TOKEN
    if token:
        headers["Authorization"] = f"Bearer {token}"

    with open(file_path, "rb") as f:
        files = {"file": (os.path.basename(file_path), f, mime)}
        async with httpx.AsyncClient(base_url=API_BASE, timeout=120) as client:
            resp = await client.post(path, files=files, data=form_data, headers=headers)
            resp.raise_for_status()
            return resp.json()


# ============================================================
# Tool: search_documents
# ============================================================

@mcp.tool()
async def search_documents(
    query: str = "",
    doc_type: str = "",
    status: str = "",
    entity_name: str = "",
    folder_path: str = "",
    expiry_before: str = "",
    expiry_after: str = "",
    limit: int = 20,
    offset: int = 0,
) -> str:
    """搜索 MaterialHub 中的文档资料。支持分页。

    支持全文关键词搜索和多维度过滤，可用于查找营业执照、资质证书、合同、
    人员证件等各类企业材料。

    Args:
        query: 搜索关键词，支持中文全文检索（如"营业执照"、"ISO认证"、公司名等）
        doc_type: 文档类型过滤，如 business_license, qualification_cert, contract, id_card
        status: 状态过滤: active(生效), draft(草稿), expired(已过期), archived(已归档)
        entity_name: 按关联实体(公司/人员)名称搜索
        folder_path: 按文件夹路径过滤
        expiry_before: 到期日期早于(YYYY-MM-DD)，用于查找即将过期的文档
        expiry_after: 到期日期晚于(YYYY-MM-DD)
        limit: 返回结果数量上限，默认20，最大30
        offset: 分页偏移量，默认0。设为30获取第二页，60获取第三页
    """
    params: dict[str, Any] = {"limit": _safe_limit(limit), "offset": offset}

    if query:
        params["q"] = query
    if status:
        params["status"] = status
    if expiry_before:
        params["expiry_before"] = expiry_before
    if expiry_after:
        params["expiry_after"] = expiry_after

    # Resolve folder_path to folder ID
    if folder_path:
        try:
            tree_data = await _get("/api/v2/folders/tree")
            tree = tree_data.get("tree", []) if isinstance(tree_data, dict) else tree_data

            def _find_folder(nodes: list, target: str) -> int | None:
                for n in nodes:
                    if n["path"] == target or n["name"] == target:
                        return n["id"]
                    if n.get("children"):
                        found = _find_folder(n["children"], target)
                        if found:
                            return found
                return None

            fid = _find_folder(tree, folder_path)
            if fid:
                params["folder_id"] = fid
        except Exception:
            pass

    # Resolve doc_type name to ID
    if doc_type:
        try:
            dt_data = await _get("/api/v2/doc-types/")
            for cat_types in dt_data.get("doc_types", {}).values():
                for dt in cat_types:
                    if dt["code"] == doc_type or doc_type.lower() in dt["name"].lower():
                        params["doc_type_id"] = dt["id"]
                        break
        except Exception:
            pass

    # Resolve entity name to ID
    if entity_name:
        try:
            ent_data = await _get("/api/v2/entities/", {"q": entity_name, "limit": 1})
            entities = ent_data.get("results", [])
            if entities:
                params["entity_id"] = entities[0]["id"]
        except Exception:
            pass

    try:
        data = await _get("/api/v2/search", params)
    except httpx.HTTPStatusError as e:
        return f"搜索失败: {e.response.status_code} {e.response.text}"

    results = data.get("results", [])
    total = data.get("total", 0)

    # Smart fallback: if keyword search returned few results, also try folder-name matching
    if query and total < 3 and "folder_id" not in params:
        try:
            tree_data = await _get("/api/v2/folders/tree")
            tree = tree_data.get("tree", []) if isinstance(tree_data, dict) else tree_data

            def _find_matching_folders(nodes: list, keyword: str) -> list[int]:
                matched = []
                for n in nodes:
                    if keyword in n.get("name", "") or keyword in n.get("path", ""):
                        matched.append(n["id"])
                    if n.get("children"):
                        matched.extend(_find_matching_folders(n["children"], keyword))
                return matched

            folder_ids = _find_matching_folders(tree, query)
            if folder_ids:
                existing_ids = {r["id"] for r in results}
                for fid in folder_ids:
                    try:
                        folder_data = await _get("/api/v2/search", {
                            "folder_id": fid, "limit": _safe_limit(50),
                            **({"status": status} if status else {}),
                        })
                        for r in folder_data.get("results", []):
                            if r["id"] not in existing_ids:
                                results.append(r)
                                existing_ids.add(r["id"])
                    except Exception:
                        pass
                total = len(results)
        except Exception:
            pass

    if not results:
        return f"未找到匹配的文档 (关键词: {query or '无'}, 过滤条件: doc_type={doc_type}, status={status})"

    has_more = (offset + len(results)) < total
    page_info = f"第{offset//_safe_limit(limit)+1}页"
    if has_more:
        page_info += f"，还有{total - offset - len(results)}条，用offset={offset + len(results)}获取下一页"

    lines = [f"找到 {total} 条结果，显示 {offset+1}-{offset+len(results)} ({page_info}):\n"]
    for r in results:
        dt_name = r["doc_type"]["name"] if r["doc_type"] else "未分类"
        folder_name = r["folder"]["name"] if r["folder"] else "未归档"
        entities = ", ".join(r.get("entity_names", [])[:5]) or "无"
        expiry = r.get("expiry_date") or "无"
        snippet = (r.get("snippet") or "")[:MAX_OCR_CHARS]

        lines.append(f"- [{r['id']}] {r['title']}")
        lines.append(f"  类型: {dt_name} | 文件夹: {folder_name} | 状态: {r['status']}")
        lines.append(f"  关联实体: {entities} | 到期日: {expiry}")
        if snippet:
            lines.append(f"  摘要: {snippet}")
        lines.append("")

    return "\n".join(lines)


# ============================================================
# Tool: get_document_detail
# ============================================================

@mcp.tool()
async def get_document_detail(document_id: int) -> str:
    """获取文档的完整详情，包括元数据、AI提取信息、关联实体、标签和版本历史。

    Args:
        document_id: 文档ID（从搜索结果中获取）
    """
    try:
        doc = await _get(f"/api/v2/documents/{document_id}")
    except httpx.HTTPStatusError as e:
        return f"获取文档失败: {e.response.status_code} {e.response.text}"

    lines = [f"# {doc['title']}\n"]

    # Basic info
    dt = doc.get("doc_type")
    folder = doc.get("folder")
    lines.append(f"- 文档ID: {doc['id']}")
    lines.append(f"- 状态: {doc['status']}")
    lines.append(f"- 文档类型: {dt['name'] if dt else '未分类'}")
    lines.append(f"- 文件夹: {folder['path'] if folder else '未归档'}")
    lines.append(f"- 到期日: {doc.get('expiry_date') or '无'}")
    lines.append(f"- 创建时间: {doc.get('created_at', '未知')}")
    lines.append(f"- 更新时间: {doc.get('updated_at', '未知')}")

    if doc.get("description"):
        lines.append(f"- 描述: {doc['description']}")

    # AI extracted metadata
    meta = doc.get("metadata")
    if meta:
        material_type = meta.get("material_type")
        confidence = meta.get("confidence")
        summary = meta.get("summary")
        extracted = meta.get("extracted_data", {})

        lines.append("\n## AI 提取信息")
        if material_type:
            lines.append(f"- 材料类型: {material_type}")
        if confidence:
            lines.append(f"- 置信度: {round(confidence * 100)}%")
        if summary:
            lines.append(f"- 摘要: {summary}")

        if extracted:
            lines.append("\n### 提取的结构化数据")
            field_labels = {
                "company_name": "公司名称", "legal_person": "法定代表人",
                "credit_code": "统一社会信用代码", "address": "地址",
                "registered_capital": "注册资本", "business_scope": "经营范围",
                "establishment_date": "成立日期", "business_term": "营业期限",
                "name": "姓名", "gender": "性别", "birth_date": "出生日期",
                "id_number": "身份证号", "issue_authority": "签发机关",
                "cert_name": "证书名称", "holder": "持有人/单位",
                "cert_number": "证书编号", "issue_date": "发证日期",
                "expiry_date": "到期日期", "scope": "认证范围",
                "party_a": "甲方", "party_b": "乙方",
                "contract_number": "合同编号", "contract_date": "签订日期",
                "contract_amount": "合同金额", "contract_term": "合同期限",
                "project_name": "项目名称", "project_location": "项目地点",
            }
            for k, v in extracted.items():
                if v:
                    label = field_labels.get(k, k)
                    lines.append(f"- {label}: {v}")

    # Entities
    entities = doc.get("entities", [])
    if entities:
        lines.append("\n## 关联实体")
        for e in entities:
            lines.append(f"- {e.get('entity_name', '未知')} ({e.get('role', '')})")

    # Tags
    tags = doc.get("tags", [])
    if tags:
        lines.append("\n## 标签")
        lines.append(", ".join(t.get("tag_name", "") for t in tags))

    # Current revision files
    rev = doc.get("current_revision")
    if rev and rev.get("files"):
        lines.append(f"\n## 附件 (版本 v{rev['version_number']})")
        for f in rev["files"]:
            size_kb = round(f.get("file_size", 0) / 1024, 1)
            lines.append(f"- {f['filename']} ({f['file_type']}, {size_kb}KB)")
            lines.append(f"  下载: {API_BASE}{f['url']}")

    return "\n".join(lines)


# ============================================================
# Tool: list_expiring_documents
# ============================================================

@mcp.tool()
async def list_expiring_documents(days: int = 30, limit: int = 20, offset: int = 0) -> str:
    """查询即将过期或已过期的文档。支持分页。

    用于资质到期预警、证书续期提醒等场景。

    Args:
        days: 查询未来多少天内到期的文档，默认30天
        limit: 每页返回数量上限，默认20
        offset: 分页偏移量，默认0。设为20获取第二页
    """
    try:
        summary = await _get("/api/v2/expiry/summary")
    except httpx.HTTPStatusError as e:
        return f"查询失败: {e.response.status_code}"

    lines = ["# 到期概览\n"]
    lines.append(f"- 已过期: {summary.get('expired', 0)} 份")
    lines.append(f"- 30天内到期: {summary.get('expiring_30d', 0)} 份")
    lines.append(f"- 60天内到期: {summary.get('expiring_60d', 0)} 份")
    lines.append(f"- 90天内到期: {summary.get('expiring_90d', 0)} 份")

    by_type = summary.get("by_doc_type", [])
    if by_type:
        lines.append("\n## 按文档类型统计")
        for item in by_type:
            if item.get("expired", 0) > 0 or item.get("expiring_30d", 0) > 0:
                lines.append(f"- {item['doc_type_name']}: 已过期 {item['expired']}, 30天内到期 {item['expiring_30d']}")

    # Fetch expiring list
    try:
        expiring = await _get("/api/v2/expiry/expiring", {"days": days, "limit": limit, "offset": offset})
    except Exception:
        expiring = {"results": []}

    docs = expiring.get("results", [])
    if docs:
        lines.append(f"\n## {days}天内到期的文档")
        for d in docs:
            dt_name = d["doc_type"]["name"] if d.get("doc_type") else "未分类"
            days_left = d.get("days_until_expiry")
            days_str = f"{days_left}天后" if days_left and days_left > 0 else "已过期"
            entities_str = ", ".join(d.get("entity_names", [])) or ""
            lines.append(f"- [{d['id']}] {d['title']} ({dt_name})")
            lines.append(f"  到期: {d.get('expiry_date', '未知')} ({days_str})")
            if entities_str:
                lines.append(f"  实体: {entities_str}")
    else:
        lines.append(f"\n{days}天内无到期文档。")

    return "\n".join(lines)


# ============================================================
# Tool: list_entity_documents
# ============================================================

@mcp.tool()
async def list_entity_documents(entity_name: str, limit: int = 30, offset: int = 0) -> str:
    """查询某个公司或人员关联的所有文档。支持分页。

    Args:
        entity_name: 公司名称或人员姓名
        limit: 每页返回数量，默认30，最大50
        offset: 分页偏移量，默认0。设为30获取第二页
    """
    # Find entity
    try:
        ent_data = await _get("/api/v2/entities/", {"q": entity_name, "limit": 5})
    except httpx.HTTPStatusError as e:
        return f"查询失败: {e.response.status_code}"

    entities = ent_data.get("results", [])
    if not entities:
        return f"未找到名为 '{entity_name}' 的实体（公司/人员）"

    lines = []
    for ent in entities:
        lines.append(f"# {ent['name']} ({ent['entity_type']})")
        lines.append(f"- 实体ID: {ent['id']}")
        lines.append(f"- 关联文档数: {ent.get('document_count', '未知')}")

        if ent.get("attributes"):
            lines.append("- 属性:")
            for k, v in ent["attributes"].items():
                if v:
                    lines.append(f"  - {k}: {v}")

        # Search documents linked to this entity
        try:
            docs = await _get("/api/v2/search", {"entity_id": ent["id"], "limit": _safe_limit(limit), "offset": offset})
            results = docs.get("results", [])
            total_docs = docs.get("total", len(results))
            if results:
                page_info = f"显示 {offset+1}-{offset+len(results)}"
                lines.append(f"\n## 关联文档 ({total_docs} 份, {page_info})")
                for r in results:
                    dt_name = r["doc_type"]["name"] if r["doc_type"] else "未分类"
                    expiry = r.get("expiry_date") or ""
                    expiry_str = f" | 到期: {expiry}" if expiry else ""
                    lines.append(f"- [{r['id']}] {r['title']} ({dt_name}, {r['status']}{expiry_str})")
        except Exception:
            pass

        lines.append("")

    return "\n".join(lines)


# ============================================================
# Tool: list_doc_types
# ============================================================

@mcp.tool()
async def list_doc_types(category: str = "") -> str:
    """列出系统中所有可用的文档类型分类。可按类别过滤。

    Args:
        category: 类别过滤 (company/personnel/project/bid/general)，留空返回全部
    """
    try:
        data = await _get("/api/v2/doc-types/")
    except httpx.HTTPStatusError as e:
        return f"查询失败: {e.response.status_code}"

    cat_labels = {
        "company": "企业资质", "personnel": "人员证件",
        "project": "项目文档", "bid": "投标文档", "general": "通用文档",
    }

    lines = ["# 文档类型列表\n"]
    for cat, types in data.get("doc_types", {}).items():
        label = cat_labels.get(cat, cat)
        lines.append(f"## {label}")
        for dt in types:
            desc = f" - {dt['description']}" if dt.get("description") else ""
            lines.append(f"- {dt['name']} (code: {dt['code']}){desc}")
        lines.append("")

    return "\n".join(lines)


# ============================================================
# Tool: browse_folder
# ============================================================

@mcp.tool()
async def browse_folder(folder_path: str = "", limit: int = 30, offset: int = 0) -> str:
    """浏览文件夹结构和文件夹内的文档。支持分页。

    不传参数时返回整个文件夹树；传入文件夹路径时列出该文件夹下的文档。

    Args:
        folder_path: 文件夹路径（如 "/企业资质/营业执照"），留空查看整棵文件夹树
        limit: 每页文档数，默认30，最大50（仅列出文档时生效）
        offset: 分页偏移量，默认0（仅列出文档时生效）
    """
    try:
        data = await _get("/api/v2/folders/tree")
        tree = data.get("tree", []) if isinstance(data, dict) else data
    except httpx.HTTPStatusError as e:
        return f"查询失败: {e.response.status_code}"

    if not folder_path:
        # Return folder tree
        lines = ["# 文件夹结构\n"]

        def _render(nodes: list, indent: int = 0):
            for n in nodes:
                prefix = "  " * indent
                lines.append(f"{prefix}- {n['name']} (id:{n['id']}, path:{n['path']})")
                if n.get("children"):
                    _render(n["children"], indent + 1)

        _render(tree)
        return "\n".join(lines)

    # Find folder by path
    target_id = None

    def _find(nodes: list):
        nonlocal target_id
        for n in nodes:
            if n["path"] == folder_path or n["name"] == folder_path:
                target_id = n["id"]
                return
            if n.get("children"):
                _find(n["children"])

    _find(tree)

    if not target_id:
        return f"未找到文件夹: {folder_path}\n请使用 browse_folder() 查看可用的文件夹结构。"

    # List documents in folder (with pagination)
    try:
        data = await _get("/api/v2/search", {"folder_id": target_id, "limit": _safe_limit(limit), "offset": offset})
    except httpx.HTTPStatusError as e:
        return f"查询失败: {e.response.status_code}"

    results = data.get("results", [])
    total = data.get("total", 0)

    if not results:
        return f"文件夹 '{folder_path}' 下暂无文档"

    page_info = f"第{offset//_safe_limit(limit)+1}页, 显示{offset+1}-{offset+len(results)}"
    lines = [f"# 文件夹: {folder_path} ({total} 份文档, {page_info})\n"]
    for r in results:
        dt_name = r["doc_type"]["name"] if r["doc_type"] else "未分类"
        lines.append(f"- [{r['id']}] {r['title']} ({dt_name}, {r['status']})")

    return "\n".join(lines)


# ============================================================
# Tool: add_document (Direct Import)
# ============================================================

@mcp.tool()
async def add_document(
    file_path: str,
    title: str,
    doc_type: str = "",
    folder: str = "",
    expiry_date: str = "",
    description: str = "",
    entity_names: str = "",
    material_type: str = "",
    summary: str = "",
    extracted_data: str = "",
    confidence: float = 0.0,
    force: bool = False,
) -> str:
    """将文件直接导入 MaterialHub 并创建文档记录。

    适用于客户端已完成分析（OCR、分类等）后，直接带分类结果入库。
    文件会直接创建为 active 状态，后台自动完成实体链接和全文索引。

    ## 权限说明
    - 当前 Agent 受文件夹权限限制，只能导入到被授权的文件夹中。
    - 如果 Agent 只被分配了一个文件夹，可以不传 folder 参数，系统自动使用该文件夹。
    - 如果 Agent 被分配了多个文件夹，必须明确指定 folder 参数。
    - 指定的文件夹必须在 Agent 的授权范围内，否则返回 403。

    ## 使用步骤
    1. 先调用 list_doc_types 查看可用的文档类型 code
    2. 先调用 browse_folder 查看可用的文件夹路径
    3. 调用本工具上传文件并指定分类信息

    Args:
        file_path: 本地文件的绝对路径（支持 PDF、JPEG、PNG、TIFF、DOCX）
        title: 文档标题（如"广州XX公司营业执照"）
        doc_type: 文档类型（code 或名称，如 "business_license" 或 "营业执照"）。
                  可通过 list_doc_types 查看所有可用类型
        folder: 目标文件夹（路径如 "/企业资质/营业执照"，或名称如 "营业执照"）。
                可通过 browse_folder 查看文件夹结构。
                如果 Agent 只有一个授权文件夹则可省略
        expiry_date: 到期日期（YYYY-MM-DD），如 "2027-09-25"
        description: 文档描述/备注
        entity_names: 关联实体名称（公司名或人名），多个用逗号分隔
        material_type: 材料类型标识（如 "business_license"、"id_card"、"pmp_cert"）
        summary: 文档摘要
        extracted_data: 提取的结构化数据（JSON字符串），如 '{"company_name":"XX公司","credit_code":"91440..."}'
        confidence: 分类置信度（0.0-1.0）
        force: 是否跳过重复文件检查
    """
    # Validate file exists
    if not os.path.isfile(file_path):
        return f"错误: 文件不存在: {file_path}"

    form_data: dict[str, Any] = {"title": title}

    if doc_type:
        form_data["doc_type_code"] = doc_type
    if folder:
        form_data["folder_path"] = folder
    if expiry_date:
        form_data["expiry_date"] = expiry_date
    if description:
        form_data["description"] = description
    if entity_names:
        form_data["entity_names"] = entity_names
    if material_type:
        form_data["material_type"] = material_type
    if summary:
        form_data["summary"] = summary
    if extracted_data:
        form_data["extracted_data"] = extracted_data
    if confidence > 0:
        form_data["confidence"] = str(confidence)
    if force:
        form_data["force"] = "true"

    try:
        result = await _post_file("/api/v2/documents/actions/import", file_path, form_data)
    except httpx.HTTPStatusError as e:
        body = e.response.text
        if e.response.status_code == 409:
            try:
                detail = json.loads(json.loads(body).get("detail", "{}"))
                existing = detail.get("existing_document", {})
                return (
                    f"文件已存在（重复）:\n"
                    f"- 已有文档: [{existing.get('id')}] {existing.get('title')} ({existing.get('status')})\n"
                    f"如需强制导入，请设置 force=true"
                )
            except Exception:
                pass
        return f"导入失败: {e.response.status_code} {body}"
    except FileNotFoundError:
        return f"错误: 文件不存在: {file_path}"
    except Exception as e:
        return f"导入失败: {e}"

    doc_id = result.get("id")
    doc_title = result.get("title", title)
    dt = result.get("doc_type")
    fld = result.get("folder")
    expiry = result.get("expiry_date")

    lines = [
        f"文档导入成功!",
        f"- 文档ID: {doc_id}",
        f"- 标题: {doc_title}",
        f"- 状态: {result.get('status', 'active')}",
        f"- 文档类型: {dt['name'] if dt else '未分类'}",
        f"- 文件夹: {fld['path'] if fld else '未归档'}",
    ]
    if expiry:
        lines.append(f"- 到期日: {expiry}")
    lines.append(f"\n后台正在自动完成实体链接和全文索引。")

    return "\n".join(lines)


# ============================================================
# Tool: get_person_complete
# ============================================================

@mcp.tool()
async def get_person_complete(person_name: str) -> str:
    """获取人员的完整信息，包括所属公司、职位、关联文档等。

    通过 dms_entity_relations 表查找雇佣关系，返回人员→公司的归属信息。

    Args:
        person_name: 人员姓名
    """
    try:
        ent_data = await _get("/api/v2/entities/", {"q": person_name, "type": "person", "limit": 5})
    except httpx.HTTPStatusError as e:
        return f"查询失败: {e.response.status_code}"

    persons = [e for e in ent_data.get("results", []) if e["entity_type"] == "person"]
    if not persons:
        return f"未找到名为 '{person_name}' 的人员"

    lines = []
    for person in persons:
        # Get full detail with relations
        try:
            detail = await _get(f"/api/v2/entities/{person['id']}")
        except Exception:
            detail = person

        lines.append(f"# {detail['name']} (人员)")
        lines.append(f"- 实体ID: {detail['id']}")

        # Attributes
        attrs = detail.get("attributes") or {}
        if attrs.get("id_number"):
            lines.append(f"- 身份证号: {attrs['id_number']}")
        if attrs.get("education"):
            lines.append(f"- 学历: {attrs['education']}")
        if attrs.get("position"):
            lines.append(f"- 职位: {attrs['position']}")

        # Relations — find employed_by companies
        relations = detail.get("relations", {})
        outgoing = relations.get("outgoing", [])
        companies = [r for r in outgoing if r["relation"] == "employed_by"]
        if companies:
            lines.append("\n## 所属公司")
            for rel in companies:
                lines.append(f"- {rel['to_name']} (关系: {rel['relation']})")
                # Try to get company details
                try:
                    comp_detail = await _get(f"/api/v2/entities/{rel['to_id']}")
                    comp_attrs = comp_detail.get("attributes") or {}
                    if comp_attrs.get("credit_code"):
                        lines.append(f"  统一社会信用代码: {comp_attrs['credit_code']}")
                    if comp_attrs.get("legal_person"):
                        lines.append(f"  法定代表人: {comp_attrs['legal_person']}")
                except Exception:
                    pass
        else:
            lines.append("\n(未关联公司)")

        # Document count
        doc_count = detail.get("document_count", 0)
        lines.append(f"\n关联文档数: {doc_count}")

        lines.append("")

    return "\n".join(lines)


# ============================================================
# Tool: get_company_complete
# ============================================================

@mcp.tool()
async def get_company_complete(company_name: str) -> str:
    """获取公司的完整信息，包括基本信息、员工列表、关联文档等。

    通过 dms_entity_relations 表查找雇佣关系，返回公司→人员的列表。

    Args:
        company_name: 公司名称
    """
    try:
        ent_data = await _get("/api/v2/entities/", {"q": company_name, "type": "org", "limit": 5})
    except httpx.HTTPStatusError as e:
        return f"查询失败: {e.response.status_code}"

    companies = [e for e in ent_data.get("results", []) if e["entity_type"] == "org"]
    if not companies:
        return f"未找到名为 '{company_name}' 的公司"

    lines = []
    for comp in companies:
        try:
            detail = await _get(f"/api/v2/entities/{comp['id']}")
        except Exception:
            detail = comp

        lines.append(f"# {detail['name']} (公司)")
        lines.append(f"- 实体ID: {detail['id']}")

        # Attributes
        attrs = detail.get("attributes") or {}
        if attrs.get("credit_code"):
            lines.append(f"- 统一社会信用代码: {attrs['credit_code']}")
        if attrs.get("legal_person"):
            lines.append(f"- 法定代表人: {attrs['legal_person']}")
        if attrs.get("address"):
            lines.append(f"- 地址: {attrs['address']}")

        # Relations — find employees (incoming employed_by)
        relations = detail.get("relations", {})
        incoming = relations.get("incoming", [])
        employees = [r for r in incoming if r["relation"] == "employed_by"]
        if employees:
            lines.append(f"\n## 员工列表 ({len(employees)} 人)")
            for rel in employees:
                lines.append(f"- {rel['from_name']}")
                # Try to get person details
                try:
                    person_detail = await _get(f"/api/v2/entities/{rel['from_id']}")
                    person_attrs = person_detail.get("attributes") or {}
                    extras = []
                    if person_attrs.get("position"):
                        extras.append(f"职位: {person_attrs['position']}")
                    if person_attrs.get("id_number"):
                        extras.append(f"身份证: {person_attrs['id_number']}")
                    if extras:
                        lines.append(f"  {', '.join(extras)}")
                except Exception:
                    pass
        else:
            lines.append("\n(无关联员工)")

        # Document count
        doc_count = detail.get("document_count", 0)
        lines.append(f"\n关联文档数: {doc_count}")

        lines.append("")

    return "\n".join(lines)


# ============================================================
# Tool: update_document
# ============================================================

@mcp.tool()
async def update_document(
    document_id: int,
    title: str = "",
    doc_type_code: str = "",
    folder_path: str = "",
    status: str = "",
    expiry_date: str = "",
) -> str:
    """更新文档的分类、标题、状态等信息。用于重新归类。

    Args:
        document_id: 文档ID（必填）
        title: 新标题（留空不修改）
        doc_type_code: 新文档类型代码（如 "business-license", "iso-cert"），留空不修改
        folder_path: 新文件夹路径（如 "/公司资质/营业执照/"），留空不修改
        status: 新状态（active/draft/expired/archived），留空不修改
        expiry_date: 到期日期（YYYY-MM-DD），留空不修改
    """
    body: dict[str, object] = {}
    if title:
        body["title"] = title

    # Resolve doc_type_code → doc_type_id
    if doc_type_code:
        try:
            dt_data = await _get("/api/v2/doc-types/")
            for cat_types in dt_data.get("doc_types", {}).values():
                for dt in cat_types:
                    if dt["code"] == doc_type_code:
                        body["doc_type_id"] = dt["id"]
                        break
        except Exception:
            pass

    # Resolve folder_path → folder_id
    if folder_path:
        try:
            tree_data = await _get("/api/v2/folders/tree")
            tree = tree_data.get("tree", []) if isinstance(tree_data, dict) else tree_data

            def _find(nodes: list, target: str) -> int | None:
                for n in nodes:
                    if n["path"] == target or n["name"] == target:
                        return n["id"]
                    if n.get("children"):
                        found = _find(n["children"], target)
                        if found is not None:
                            return found
                return None

            fid = _find(tree, folder_path)
            if fid:
                body["folder_id"] = fid
        except Exception:
            pass

    if status:
        body["status"] = status
    if expiry_date:
        body["expiry_date"] = expiry_date

    if not body:
        return "未提供任何修改字段"

    try:
        async with httpx.AsyncClient(base_url=API_BASE, timeout=30) as client:
            resp = await client.patch(
                f"/api/v2/documents/{document_id}",
                json=body,
                headers=_headers(API_READ_TOKEN),
            )
            if resp.status_code == 404:
                return f"文档 {document_id} 不存在"
            resp.raise_for_status()
            doc = resp.json()
            dt_name = doc.get("doc_type", {}).get("name", "-")
            fld_path = doc.get("folder", {}).get("path", "-")
            return f"✅ 已更新文档 #{document_id}: 标题={doc['title']}, 类型={dt_name}, 文件夹={fld_path}, 状态={doc['status']}"
    except httpx.HTTPStatusError as e:
        return f"更新失败: {e.response.status_code} {e.response.text}"


# ============================================================
# Tool: create_doc_type
# ============================================================

@mcp.tool()
async def create_doc_type(name: str, code: str, category: str = "company", description: str = "") -> str:
    """创建新的文档类型。当系统缺少某个分类时使用。

    Args:
        name: 类型中文名，如"完税证明"
        code: 类型代码(英文)，如"tax-payment-cert"
        category: 所属类别: company/personnel/project/bid/general
        description: 描述（可选）
    """
    try:
        async with httpx.AsyncClient(base_url=API_BASE, timeout=30) as client:
            resp = await client.post(
                "/api/v2/doc-types/",
                json={"name": name, "code": code, "category": category, "description": description},
                headers=_headers(API_READ_TOKEN),
            )
            if resp.status_code == 409:
                return f"类型 '{code}' 或 '{name}' 已存在"
            resp.raise_for_status()
            data = resp.json()
            return f"✅ 已创建文档类型: {data['name']} (code={data['code']}, category={data['category']})"
    except httpx.HTTPStatusError as e:
        return f"创建失败: {e.response.status_code} {e.response.text}"


# ============================================================
# Tool: manage_folder_mappings
# ============================================================

@mcp.tool()
async def list_folder_mappings() -> str:
    """列出所有文档类型到文件夹的映射关系。

    显示每个文档类型自动归档到哪个文件夹，标注来源（builtin=内置, custom=自定义, none=未配置）。
    """
    try:
        data = await _get("/api/v2/doc-types/mappings")
    except httpx.HTTPStatusError as e:
        return f"查询失败: {e.response.status_code}"

    mappings = data.get("mappings", [])
    lines = ["# 文档类型 → 文件夹映射\n"]
    lines.append("| 文档类型(code) | 文档类型(名称) | 目标文件夹 | 来源 |")
    lines.append("|---|---|---|---|")
    for m in mappings:
        src = {"builtin": "内置", "custom": "自定义", "none": "未配置"}.get(m["source"], m["source"])
        folder = m["folder_path"] or "—"
        lines.append(f"| {m['doc_type_code']} | {m['doc_type_name']} | {folder} | {src} |")

    return "\n".join(lines)


@mcp.tool()
async def set_folder_mapping(doc_type_code: str, folder_path: str) -> str:
    """设置或修改文档类型到文件夹的自动归档映射。

    Args:
        doc_type_code: 文档类型代码（如 "business-license", "iso-cert", "contract"）
                       可通过 list_folder_mappings 查看所有可用类型
        folder_path: 目标文件夹路径（如 "/公司资质/营业执照/"）
                     可通过 browse_folder 查看可用文件夹
    """
    try:
        async with httpx.AsyncClient(base_url=API_BASE, timeout=30) as client:
            resp = await client.put(
                f"/api/v2/doc-types/mappings/{doc_type_code}",
                json={"folder_path": folder_path},
                headers=_headers(API_READ_TOKEN),
            )
            if resp.status_code == 404:
                return f"文档类型 '{doc_type_code}' 不存在。请使用 list_doc_types 查看可用的文档类型代码。"
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        return f"设置失败: {e.response.status_code} {e.response.text}"

    return f"✅ 已设置: {doc_type_code} → {folder_path}"


@mcp.tool()
async def remove_folder_mapping(doc_type_code: str) -> str:
    """移除文档类型的自定义文件夹映射（恢复为内置映射或无映射）。

    Args:
        doc_type_code: 文档类型代码
    """
    try:
        async with httpx.AsyncClient(base_url=API_BASE, timeout=30) as client:
            resp = await client.delete(
                f"/api/v2/doc-types/mappings/{doc_type_code}",
                headers=_headers(API_READ_TOKEN),
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        return f"移除失败: {e.response.status_code} {e.response.text}"

    return f"✅ 已移除 {doc_type_code} 的自定义映射"


# ============================================================
# Tool: KB Search / Knowledge Graph (Phase 4)
# ============================================================

@mcp.tool()
async def kb_search(
    query: str,
    mode: str = "hybrid",
    max_hops: int = 2,
    limit: int = 20,
) -> str:
    """AI-powered semantic/knowledge graph search with multi-hop reasoning.

    Unlike search_documents (keyword-only), this tool understands the MEANING
    of your query and can find documents through entity relationships.

    Modes:
    - "vector": pure semantic similarity search
    - "hybrid": combines keyword + semantic (fast, good for most queries)
    - "multihop": deep reasoning across entity/event graph (finds hidden links)

    Use this when:
    - Keyword search returns too few or irrelevant results
    - You need to find documents related through entities
    - You want to understand relationships between documents, entities, and events

    Args:
        query: natural language question or keywords
        mode: search mode ("vector", "hybrid", or "multihop")
        max_hops: graph expansion depth for multihop mode (1-3)
        limit: max results
    """
    params: dict[str, Any] = {"q": query, "top_k": min(limit, 50)}

    if mode == "multihop":
        params["max_hops"] = max_hops
        try:
            data = await _get("/api/v2/kb/search/multihop", params)
        except httpx.HTTPStatusError as e:
            return f"多跳搜索失败: {e.response.status_code}"
    else:
        params["mode"] = mode
        try:
            data = await _get("/api/v2/kb/search", params)
        except httpx.HTTPStatusError as e:
            return f"语义搜索失败: {e.response.status_code}"

    results = data.get("results", [])
    if not results:
        return f"未找到与 '{query}' 语义相关的结果 (mode={mode})"

    lines = [f"语义搜索 '{query}' 找到 {len(results)} 条结果 (mode={mode}):\n"]
    for r in results:
        doc_id = r.get("doc_id", "?")
        title = r.get("title", "无标题")
        score = r.get("score", r.get("rrf_score", 0))
        doc_type = r.get("doc_type", "")
        content_preview = (r.get("content") or "")[:200]
        entities = ", ".join(r.get("entity_names", [])[:5]) or "无"

        lines.append(f"- [doc:{doc_id}] {title} (score={score:.4f}, {doc_type})")
        lines.append(f"  关联: {entities}")
        if content_preview:
            lines.append(f"  摘要: {content_preview}")
        lines.append("")

    # Include trace for multihop
    trace = data.get("trace")
    if trace and mode == "multihop":
        lines.append(f"---")
        lines.append(f"搜索过程 ({trace.get('total_ms', 0)}ms):")
        lines.append(f"  发现实体: {trace.get('entities_found', 0)}")
        lines.append(f"  发现事件: {trace.get('events_found', 0)}")
        for step in trace.get("steps", []):
            lines.append(f"  {step.get('name')}: {step.get('detail')}")

    return "\n".join(lines)


@mcp.tool()
async def kb_get_entity_graph(entity_name: str, depth: int = 1) -> str:
    """Explore the knowledge graph around an entity (company or person).

    Shows relationships, linked events, and connected documents.
    Useful for understanding a company's or person's full context.

    Args:
        entity_name: company or person name (e.g. "XX公司")
        depth: exploration depth (1-3, default 1)
    """
    try:
        data = await _get(f"/api/v2/kb/entities/{entity_name}/graph", {"depth": depth})
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            # Try entity search instead
            try:
                search_data = await _get("/api/v2/kb/entities/search", {"q": entity_name, "limit": 5})
                entities = search_data.get("entities", [])
                if not entities:
                    return f"未找到名为 '{entity_name}' 的实体"
                lines = [f"搜索 '{entity_name}' 找到 {len(entities)} 个实体:\n"]
                for e in entities:
                    lines.append(f"- [{e['id']}] {e['name']} ({e.get('entity_type', 'unknown')})")
                lines.append("\n使用 kb_get_entity_graph 查看具体实体的关系图谱")
                return "\n".join(lines)
            except Exception:
                return f"未找到名为 '{entity_name}' 的实体"
        return f"查询失败: {e.response.status_code}"

    if "error" in data:
        return f"未找到实体: {entity_name}"

    entity = data["entity"]
    relations = data.get("relations", [])
    related = data.get("related_entities", [])
    events = data.get("events", [])

    lines = [f"# {entity['name']} ({entity['type']}) 知识图谱\n"]

    if relations:
        lines.append(f"## 关系 ({len(relations)})")
        for rel in relations:
            lines.append(f"- {rel.get('relation', 'unknown')}: → entity_id={rel.get('target_id') or rel.get('source_id')}")

    if related:
        lines.append(f"\n## 关联实体 ({len(related)})")
        for e in related:
            lines.append(f"- [{e.get('dms_entity_id', e['id'])}] {e['name']} ({e.get('entity_type', '?')})")

    if events:
        lines.append(f"\n## 关联事件 ({len(events)})")
        for evt in events[:10]:
            date = evt.get("event_date") or ""
            lines.append(f"- {date} [{evt.get('event_type')}] {evt['title']} (doc:{evt.get('doc_id')})")

    if not relations and not events:
        lines.append("该实体暂无关系或事件关联。")

    return "\n".join(lines)


# ============================================================
# Tool: Agent Memory (history / persistent notes)
# ============================================================

@mcp.tool()
async def agent_remember(key: str, value: str) -> str:
    """存储一条记忆，供后续对话使用。用于记录处理进度、决策等。

    Args:
        key: 记忆标识（如 "reclassified_docs", "last_batch_id"）
        value: 记忆内容（任意文本）
    """
    try:
        async with httpx.AsyncClient(base_url=API_BASE, timeout=30) as client:
            resp = await client.put(
                f"/api/v2/settings/agent_memory_{key}",
                json={"value": value},
                headers=_headers(API_READ_TOKEN),
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        return f"❌ 存储失败: {e.response.status_code}"
    return f"✅ 已记忆: {key}"


@mcp.tool()
async def agent_recall(key: str) -> str:
    """读取之前存储的记忆。"""
    try:
        data = await _get(f"/api/v2/settings/agent_memory_{key}")
        val = data.get("value", "")
        return val if val else f"(空记忆: {key})"
    except Exception:
        return f"(未找到记忆: {key})"


@mcp.tool()
async def agent_list_memories() -> str:
    """列出所有已存储的记忆。"""
    try:
        data = await _get("/api/v2/settings/?prefix=agent_memory_")
        items = data.get("settings", [])
        if not items:
            return "(暂无记忆)"
        lines = ["# Agent 记忆\n"]
        for item in items:
            key = item["key"].replace("agent_memory_", "")
            val = (item.get("value") or "")[:100]
            lines.append(f"- **{key}**: {val}")
        return "\n".join(lines)
    except Exception as e:
        return f"读取失败: {e}"


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")  # stdio | sse
    if transport == "sse":
        import uvicorn
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.responses import JSONResponse
        import httpx as _httpx

        API_BASE_URL = os.getenv("MATERIALHUB_API_URL", "http://localhost:8201")

        class AuthMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                # Extract token
                token = request.query_params.get("token", "")
                if not token:
                    auth = request.headers.get("authorization", "")
                    if auth.startswith("Bearer "):
                        token = auth[7:]

                # POST /messages/ — use cached _last_agent from SSE connect
                if request.url.path.startswith("/messages/") and request.method == "POST":
                    return await call_next(request)

                if not token:
                    return JSONResponse({"error": "MCP token required"}, status_code=401)

                # SSE connect — resolve token and cache agent
                try:
                    async with _httpx.AsyncClient(timeout=5) as c:
                        resp = await c.get(
                            f"{API_BASE_URL}/api/v2/settings/mcp/resolve",
                            params={"token": token},
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            global _last_agent
                            _last_agent = {"api_key": data["api_key"], "agent_role": data["agent_role"]}
                            logger.info(f"Resolved agent: role={data['agent_role']}")
                        else:
                            return JSONResponse({"error": "Token resolution failed"}, status_code=401)
                except Exception as e:
                    logger.warning(f"Token resolution error: {e}")
                    return JSONResponse({"error": "Auth service unavailable"}, status_code=503)

                return await call_next(request)

        host = os.getenv("MCP_HOST", "0.0.0.0")
        port = int(os.getenv("MCP_PORT", "8202"))
        logger.info(f"Starting MCP SSE server on {host}:{port} (token-based auth)")
        app = mcp.sse_app()
        app.add_middleware(AuthMiddleware)
        uvicorn.run(app, host=host, port=port, log_level="info", server_header=False)
    else:
        mcp.run()
