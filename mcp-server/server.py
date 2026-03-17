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

mcp = FastMCP(
    "MaterialHub",
    instructions="MaterialHub 材料管理系统 - 搜索和查询企业资质文档、证书、合同等材料",
)


def _headers(token: str = "") -> dict:
    """Build request headers with auth token."""
    t = token or API_READ_TOKEN
    h = {"Content-Type": "application/json"}
    if t:
        h["Authorization"] = f"Bearer {t}"
    return h


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
) -> str:
    """搜索 MaterialHub 中的文档资料。

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
        limit: 返回结果数量上限，默认20
    """
    params: dict[str, Any] = {"limit": min(limit, 50), "offset": 0}

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
                            "folder_id": fid, "limit": 50,
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

    lines = [f"找到 {total} 条结果 (显示前 {len(results)} 条):\n"]
    for r in results:
        dt_name = r["doc_type"]["name"] if r["doc_type"] else "未分类"
        folder_name = r["folder"]["name"] if r["folder"] else "未归档"
        entities = ", ".join(r.get("entity_names", [])) or "无"
        expiry = r.get("expiry_date") or "无"
        snippet = r.get("snippet") or ""

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
async def list_expiring_documents(days: int = 30, limit: int = 20) -> str:
    """查询即将过期或已过期的文档。

    用于资质到期预警、证书续期提醒等场景。

    Args:
        days: 查询未来多少天内到期的文档，默认30天
        limit: 返回结果数量上限
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
        expiring = await _get("/api/v2/expiry/expiring", {"days": days, "limit": limit})
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
async def list_entity_documents(entity_name: str) -> str:
    """查询某个公司或人员关联的所有文档。

    Args:
        entity_name: 公司名称或人员姓名
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
            docs = await _get("/api/v2/search", {"entity_id": ent["id"], "limit": 50})
            results = docs.get("results", [])
            if results:
                lines.append(f"\n## 关联文档 ({len(results)} 份)")
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
async def list_doc_types() -> str:
    """列出系统中所有可用的文档类型分类。

    返回按类别分组的文档类型列表，帮助了解系统中管理的材料种类。
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
async def browse_folder(folder_path: str = "") -> str:
    """浏览文件夹结构和文件夹内的文档。

    不传参数时返回整个文件夹树；传入文件夹路径时列出该文件夹下的文档。

    Args:
        folder_path: 文件夹路径（如 "/企业资质/营业执照"），留空查看整棵文件夹树
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

    # List documents in folder
    try:
        data = await _get("/api/v2/search", {"folder_id": target_id, "limit": 50})
    except httpx.HTTPStatusError as e:
        return f"查询失败: {e.response.status_code}"

    results = data.get("results", [])
    total = data.get("total", 0)

    if not results:
        return f"文件夹 '{folder_path}' 下暂无文档"

    lines = [f"# 文件夹: {folder_path} ({total} 份文档)\n"]
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
# Tool: get_company_complete
# ============================================================

@mcp.tool()
async def get_company_complete(company_name: str = "", company_id: int = 0) -> str:
    """获取公司完整信息（聚合API）- 一次性获取公司基本信息、营业执照、员工、材料和统计数据。

    相比多次调用 search_documents，此工具提供约10倍性能提升，适用于需要全面了解一家公司的场景。

    Args:
        company_name: 公司名称（精确匹配或模糊搜索）
        company_id: 公司实体ID（如果已知ID，优先使用ID查询）
    """
    # Resolve company_name to ID if needed
    if not company_id and not company_name:
        return "错误: 必须提供 company_name 或 company_id 之一"

    if not company_id and company_name:
        try:
            ent_data = await _get("/api/v2/entities/", {"q": company_name, "entity_type": "org", "limit": 5})
            entities = ent_data.get("results", [])
            if not entities:
                return f"未找到名为 '{company_name}' 的公司"
            if len(entities) > 1:
                lines = [f"找到 {len(entities)} 家匹配的公司，请选择：\n"]
                for e in entities[:5]:
                    lines.append(f"- [ID:{e['id']}] {e['name']}")
                lines.append(f"\n请使用 company_id 参数指定具体公司")
                return "\n".join(lines)
            company_id = entities[0]["id"]
        except httpx.HTTPStatusError as e:
            return f"查询失败: {e.response.status_code}"

    # Fetch complete company info
    try:
        data = await _get(f"/api/v2/companies/{company_id}/complete")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"公司 ID {company_id} 不存在"
        return f"查询失败: {e.response.status_code} {e.response.text}"

    company = data.get("company", {})
    license_info = data.get("license", {})
    employees = data.get("employees", [])
    materials = data.get("materials", [])
    aggregated = data.get("aggregated_info", {})
    stats = data.get("statistics", {})

    lines = [f"# {company.get('name', '未知公司')}\n"]

    # Basic company info
    lines.append("## 基本信息")
    lines.append(f"- 公司ID: {company.get('id')}")
    lines.append(f"- 类型: {company.get('entity_type', 'org')}")
    if company.get("attributes"):
        for k, v in company["attributes"].items():
            if v:
                lines.append(f"- {k}: {v}")

    # License info (from aggregated营业执照 data)
    if license_info:
        lines.append("\n## 营业执照信息")
        field_mapping = {
            "credit_code": "统一社会信用代码",
            "legal_person": "法定代表人",
            "registered_capital": "注册资本",
            "establishment_date": "成立日期",
            "business_term": "营业期限",
            "company_type": "公司类型",
            "address": "注册地址",
            "business_scope": "经营范围",
        }
        for k, v in license_info.items():
            if v and k in field_mapping:
                lines.append(f"- {field_mapping[k]}: {v}")

    # Aggregated extended fields
    if aggregated:
        lines.append("\n## 聚合字段")
        for k, v in aggregated.items():
            if v:
                lines.append(f"- {k}: {v}")

    # Statistics
    if stats:
        lines.append("\n## 统计信息")
        lines.append(f"- 材料总数: {stats.get('total_materials', 0)}")
        lines.append(f"- 员工总数: {stats.get('total_employees', 0)}")
        if stats.get('expired_materials', 0) > 0:
            lines.append(f"- ⚠️ 过期材料: {stats['expired_materials']}")

    # Employees
    if employees:
        lines.append(f"\n## 员工 ({len(employees)} 人)")
        for emp in employees[:20]:  # 最多显示20人
            emp_name = emp.get("name", "未知")
            emp_id = emp.get("id")
            emp_attrs = emp.get("attributes", {})

            # 提取关键信息
            info_parts = [f"{emp_name} (ID:{emp_id})"]
            if emp_attrs.get("gender"):
                info_parts.append(emp_attrs["gender"])
            if emp_attrs.get("age"):
                info_parts.append(f"{emp_attrs['age']}岁")
            if emp_attrs.get("education"):
                info_parts.append(emp_attrs["education"])
            if emp_attrs.get("major"):
                info_parts.append(emp_attrs["major"])

            lines.append(f"- {' | '.join(info_parts)}")

        if len(employees) > 20:
            lines.append(f"  ... 及其他 {len(employees) - 20} 人")

    # Materials summary (按类型分组)
    if materials:
        lines.append(f"\n## 材料清单 ({len(materials)} 份)")
        by_type = {}
        for mat in materials:
            doc_type = mat.get("doc_type", {}).get("name", "未分类")
            if doc_type not in by_type:
                by_type[doc_type] = []
            by_type[doc_type].append(mat)

        for doc_type, mats in sorted(by_type.items()):
            lines.append(f"\n### {doc_type} ({len(mats)} 份)")
            for mat in mats[:10]:  # 每个类型最多显示10个
                title = mat.get("title", "未命名")
                doc_id = mat.get("id")
                status = mat.get("status", "")
                expiry = mat.get("expiry_date", "")
                expiry_str = f" | 到期: {expiry}" if expiry else ""
                lines.append(f"- [{doc_id}] {title} ({status}{expiry_str})")
            if len(mats) > 10:
                lines.append(f"  ... 及其他 {len(mats) - 10} 份")

    lines.append(f"\n---\n提示: 使用 get_document_detail(document_id) 查看材料详情")

    return "\n".join(lines)


# ============================================================
# Tool: get_person_complete
# ============================================================

@mcp.tool()
async def get_person_complete(person_name: str = "", person_id: int = 0) -> str:
    """获取人员完整信息（聚合API）- 一次性获取人员基本信息、所属公司、材料和证书清单。

    相比多次调用 search_documents，此工具提供约10倍性能提升，适用于需要全面了解某个员工的场景。

    Args:
        person_name: 人员姓名（精确匹配或模糊搜索）
        person_id: 人员实体ID（如果已知ID，优先使用ID查询）
    """
    # Resolve person_name to ID if needed
    if not person_id and not person_name:
        return "错误: 必须提供 person_name 或 person_id 之一"

    if not person_id and person_name:
        try:
            ent_data = await _get("/api/v2/entities/", {"q": person_name, "entity_type": "person", "limit": 5})
            entities = ent_data.get("results", [])
            if not entities:
                return f"未找到名为 '{person_name}' 的人员"
            if len(entities) > 1:
                lines = [f"找到 {len(entities)} 位匹配的人员，请选择：\n"]
                for e in entities[:5]:
                    attrs = e.get("attributes", {})
                    info = f"{e['name']}"
                    if attrs.get("company"):
                        info += f" ({attrs['company']})"
                    if attrs.get("position"):
                        info += f" - {attrs['position']}"
                    lines.append(f"- [ID:{e['id']}] {info}")
                lines.append(f"\n请使用 person_id 参数指定具体人员")
                return "\n".join(lines)
            person_id = entities[0]["id"]
        except httpx.HTTPStatusError as e:
            return f"查询失败: {e.response.status_code}"

    # Fetch complete person info
    try:
        data = await _get(f"/api/v2/persons/{person_id}/complete")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"人员 ID {person_id} 不存在"
        return f"查询失败: {e.response.status_code} {e.response.text}"

    person = data.get("person", {})
    company = data.get("company")
    materials = data.get("materials", [])
    aggregated = data.get("aggregated_info", {})
    certificates = data.get("certificates", [])

    lines = [f"# {person.get('name', '未知人员')}\n"]

    # Basic person info
    lines.append("## 基本信息")
    lines.append(f"- 人员ID: {person.get('id')}")

    if person.get("attributes"):
        field_mapping = {
            "gender": "性别",
            "age": "年龄",
            "birth_date": "出生日期",
            "id_number": "身份证号",
            "education": "学历",
            "major": "专业",
            "position": "职位",
            "phone": "电话",
            "email": "邮箱",
        }
        for k, v in person["attributes"].items():
            if v:
                label = field_mapping.get(k, k)
                lines.append(f"- {label}: {v}")

    # Company info
    if company:
        lines.append(f"\n## 所属公司")
        lines.append(f"- {company.get('name')} (ID:{company.get('id')})")

    # Aggregated extended fields
    if aggregated:
        lines.append("\n## 聚合字段")
        for k, v in aggregated.items():
            if v:
                lines.append(f"- {k}: {v}")

    # Certificates summary
    if certificates:
        lines.append(f"\n## 证书清单 ({len(certificates)} 个)")
        for cert in certificates:
            cert_name = cert.get("cert_name") or cert.get("title", "未知证书")
            cert_number = cert.get("cert_number", "")
            expiry = cert.get("expiry_date", "")
            issue_date = cert.get("issue_date", "")

            info_parts = [cert_name]
            if cert_number:
                info_parts.append(f"编号: {cert_number}")
            if issue_date:
                info_parts.append(f"发证: {issue_date}")
            if expiry:
                info_parts.append(f"到期: {expiry}")

            lines.append(f"- {' | '.join(info_parts)}")

    # Materials summary
    if materials:
        lines.append(f"\n## 材料清单 ({len(materials)} 份)")
        by_type = {}
        for mat in materials:
            doc_type = mat.get("doc_type", {}).get("name", "未分类")
            if doc_type not in by_type:
                by_type[doc_type] = []
            by_type[doc_type].append(mat)

        for doc_type, mats in sorted(by_type.items()):
            lines.append(f"\n### {doc_type} ({len(mats)} 份)")
            for mat in mats[:5]:  # 每个类型最多显示5个
                title = mat.get("title", "未命名")
                doc_id = mat.get("id")
                status = mat.get("status", "")
                lines.append(f"- [{doc_id}] {title} ({status})")
            if len(mats) > 5:
                lines.append(f"  ... 及其他 {len(mats) - 5} 份")

    lines.append(f"\n---\n提示: 使用 get_document_detail(document_id) 查看材料详情")

    return "\n".join(lines)


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    mcp.run()
