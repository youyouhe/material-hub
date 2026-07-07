"""System settings API endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from dms_auth import require_role
from dms_models import get_dms_session, SystemSetting, get_setting, set_setting

logger = logging.getLogger("materialhub.routers.v2_settings")

router = APIRouter(prefix="/api/v2/settings", tags=["settings"])

# Settings that are managed by this API
MANAGED_SETTINGS = {
    # OCR settings
    "ocr_provider": {
        "description": "OCR提供者 (deepseek / bigmodel / paddleocr)",
        "default": "deepseek",
    },
    "ocr_service_url": {
        "description": "DeepSeek OCR服务地址",
        "default": "http://host.docker.internal:8010",
    },
    "bigmodel_api_key": {
        "description": "BigModel (智谱) API密钥",
        "default": "",
        "sensitive": True,
    },
    "bigmodel_tool_type": {
        "description": "BigModel OCR工具类型 (hand_write / print / both)",
        "default": "hand_write",
    },
    "bigmodel_language_type": {
        "description": "BigModel OCR语言 (CHN_ENG / ENG / CHN)",
        "default": "CHN_ENG",
    },
    "paddleocr_lang": {
        "description": "PaddleOCR 识别语言 (ch / en / japan / korean 等)",
        "default": "ch",
    },
    # LLM settings
    "llm_provider": {
        "description": "LLM提供者 (deepseek / openrouter / anthropic)",
        "default": "deepseek",
    },
    "llm_api_key": {
        "description": "LLM API密钥",
        "default": "",
        "sensitive": True,
    },
    "llm_base_url": {
        "description": "LLM API地址 (可选，留空使用默认)",
        "default": "",
    },
    "llm_model": {
        "description": "LLM模型名称 (可选，留空使用默认)",
        "default": "",
    },
}

SENSITIVE_KEYS = {k for k, v in MANAGED_SETTINGS.items() if v.get("sensitive")}


class UpdateSettingRequest(BaseModel):
    value: str
    description: Optional[str] = None


class BatchUpdateRequest(BaseModel):
    settings: dict[str, str]


def _mask_sensitive(key: str, value: str) -> str:
    """Mask sensitive values for display."""
    if key in SENSITIVE_KEYS and value:
        if len(value) <= 8:
            return "****"
        return value[:4] + "****" + value[-4:]
    return value


@router.get("/")
async def list_settings(prefix: Optional[str] = Query(None)):
    """List settings. If prefix given, returns all matching (for agent memory)."""
    # Prefix mode: return raw settings (used by agent memory tools)
    if prefix:
        with get_dms_session() as s:
            items = s.query(SystemSetting).filter(
                SystemSetting.key.like(f"{prefix}%")
            ).order_by(SystemSetting.key).all()
            return {
                "settings": [
                    {"key": i.key, "value": i.value, "description": i.description,
                     "updated_at": i.updated_at.isoformat() if i.updated_at else None}
                    for i in items
                ]
            }

    # Default: managed settings list
    result = {}
    for key, meta in MANAGED_SETTINGS.items():
        value = get_setting(key, meta["default"])
        result[key] = {
            "value": _mask_sensitive(key, value or ""),
            "description": meta["description"],
            "default": meta["default"],
            "sensitive": key in SENSITIVE_KEYS,
        }
    return {"settings": result}


@router.put("/batch", dependencies=[require_role("admin")])
async def batch_update_settings(data: BatchUpdateRequest):
    """Batch update multiple settings."""
    updated = []
    for key, value in data.settings.items():
        if key not in MANAGED_SETTINGS:
            continue
        if key == "ocr_provider" and value not in ("deepseek", "bigmodel", "paddleocr"):
            raise HTTPException(status_code=400, detail="OCR provider must be 'deepseek', 'bigmodel', or 'paddleocr'")
        if key == "llm_provider" and value not in ("deepseek", "openrouter", "anthropic"):
            raise HTTPException(status_code=400, detail="LLM provider must be 'deepseek', 'openrouter', or 'anthropic'")
        set_setting(key, value, MANAGED_SETTINGS[key]["description"])
        updated.append(key)

    return {"updated": updated, "success": True}


@router.get("/mcp/status", dependencies=[require_role("admin")])
def mcp_status():
    """Check MCP SSE server status via port availability."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    token = get_setting("mcp_access_token") or ""
    try:
        s.connect(("localhost", 8202))
        s.close()
        return {
            "running": True,
            "url": f"http://172.26.209.253:8202/sse?token={token}",
            "transport": "SSE",
            "token": token,
        }
    except Exception:
        return {
            "running": False,
            "url": f"http://172.26.209.253:8202/sse?token={token}",
            "transport": "SSE",
            "token": token,
        }


@router.post("/mcp/start", dependencies=[require_role("admin")])
def mcp_start():
    """Start MCP SSE server as background process. Kills existing first."""
    import subprocess, os, socket

    # Check if already running
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    try:
        s.connect(("localhost", 8202))
        s.close()
        return {"status": "already_running", "port": 8202}
    except Exception:
        pass

    # Kill any stale process on 8202
    result = subprocess.run(["lsof", "-t", "-i:8202"], capture_output=True, text=True)
    for pid in result.stdout.strip().split("\n"):
        if pid.strip():
            try: os.kill(int(pid.strip()), 9)
            except Exception: pass

    server_dir = os.path.join(os.path.dirname(__file__), "..", "..", "mcp-server")
    server_script = os.path.join(server_dir, "server.py")
    log_file = "/tmp/mcp-sse.log"

    # Get or generate SSE access token
    token = get_setting("mcp_access_token") or ""
    if not token:
        import secrets
        token = "mcp-sse-" + secrets.token_hex(16)
        set_setting("mcp_access_token", token, "MCP SSE server access token")

    env = {
        **os.environ,
        "MCP_TRANSPORT": "sse", "MCP_PORT": "8202",
        "MATERIALHUB_API_URL": "http://localhost:8201",
    }
    with open(log_file, "w") as lf:
        subprocess.Popen(
            ["python3", server_script],
            cwd=server_dir, env=env,
            stdout=lf, stderr=lf,
            start_new_session=True,
        )
    logger.info("Started MCP SSE server")
    return {"status": "started", "port": 8202}


@router.post("/mcp/stop", dependencies=[require_role("admin")])
def mcp_stop():
    """Stop MCP SSE server."""
    import subprocess, os as _os
    result = subprocess.run(["lsof", "-t", "-i:8202"], capture_output=True, text=True)
    pids = result.stdout.strip().split("\n")
    killed = []
    for pid in pids:
        if pid.strip():
            try:
                _os.kill(int(pid.strip()), 9)
                killed.append(pid.strip())
            except Exception:
                pass
    logger.info(f"Stopped MCP SSE server: PIDs {killed}")
    return {"status": "stopped", "pids": killed}


# Public (no auth) — called by MCP server to resolve token→agent
@router.get("/mcp/resolve")
def resolve_mcp_token(token: str = Query(...)):
    """Resolve an MCP SSE token to its agent's API key. Called by MCP server."""
    from dms_models import DmsMcpToken
    with get_dms_session() as s:
        t = s.query(DmsMcpToken).filter(
            DmsMcpToken.sse_token == token, DmsMcpToken.is_active == True
        ).first()
        if not t or not t.agent or not t.agent.is_active:
            raise HTTPException(status_code=401, detail="Invalid or inactive MCP token")
        return {
            "api_key": t.agent.token,
            "agent_role": t.agent.role,
            "agent_name": t.agent.name,
            "folder_ids": [a.folder_id for a in t.agent.folder_access],
        }


@router.post("/ocr/test", dependencies=[require_role("admin")])
async def test_ocr():
    """Test the current OCR configuration."""
    from ocr_client import check_ocr_service, _get_ocr_provider

    provider = _get_ocr_provider()
    available = check_ocr_service()

    return {
        "provider": provider,
        "available": available,
        "message": f"OCR服务 ({provider}) {'可用' if available else '不可用'}",
    }


# ============================================================
# MCP Token Management
# ============================================================

class McpTokenCreate(BaseModel):
    name: str
    agent_id: Optional[int] = None
    role_id: Optional[int] = None


@router.get("/mcp/tokens", dependencies=[require_role("admin")])
def list_mcp_tokens():
    """List all MCP SSE tokens with their bound agents."""
    from dms_models import DmsMcpToken
    with get_dms_session() as s:
        tokens = s.query(DmsMcpToken).order_by(DmsMcpToken.created_at.desc()).all()
        return {"tokens": [t.to_dict() for t in tokens]}


@router.post("/mcp/tokens", dependencies=[require_role("admin")])
def create_mcp_token(data: McpTokenCreate):
    """Create a new MCP SSE token bound to a role via an agent."""
    import secrets
    from dms_models import DmsMcpToken, ApiAgent, DmsRole
    with get_dms_session() as s:
        agent = None
        if data.agent_id:
            agent = s.query(ApiAgent).filter(ApiAgent.id == data.agent_id).first()
        elif data.role_id:
            role = s.query(DmsRole).filter(DmsRole.id == data.role_id).first()
            if not role:
                raise HTTPException(status_code=404, detail="Role not found")
            # Find or create an agent for this role
            agent = s.query(ApiAgent).filter(
                ApiAgent.name == f"MCP-{role.name}",
                ApiAgent.role == role.name,
            ).first()
            if not agent:
                agent = ApiAgent(
                    name=f"MCP-{role.name}",
                    token="mh-agent-" + secrets.token_hex(20),
                    role=role.name,
                    description=f"Auto-created MCP agent for role: {role.name}",
                )
                s.add(agent)
                s.flush()
                # Copy folder permissions from role
                from dms_models import DmsRoleFolderPermission, AgentFolderAccess
                perms = s.query(DmsRoleFolderPermission).filter(
                    DmsRoleFolderPermission.role_id == role.id
                ).all()
                for p in perms:
                    s.add(AgentFolderAccess(agent_id=agent.id, folder_id=p.folder_id))
        if not agent:
            raise HTTPException(status_code=400, detail="agent_id or role_id required")

        sse_token = "mcp-sse-" + secrets.token_hex(16)
        t = DmsMcpToken(name=data.name, sse_token=sse_token, agent_id=agent.id)
        s.add(t)
        s.flush()
        result = t.to_dict()
        result["sse_token"] = sse_token
        return result


@router.get("/mcp/tokens/{token_id}/reveal", dependencies=[require_role("admin")])
def reveal_mcp_token(token_id: int):
    from dms_models import DmsMcpToken
    with get_dms_session() as s:
        t = s.query(DmsMcpToken).filter(DmsMcpToken.id == token_id).first()
        if not t: raise HTTPException(status_code=404)
        return {"url": f"http://172.26.209.253:8202/sse?token={t.sse_token}"}


@router.delete("/mcp/tokens/{token_id}", dependencies=[require_role("admin")])
def delete_mcp_token(token_id: int):
    """Delete an MCP token."""
    from dms_models import DmsMcpToken
    with get_dms_session() as s:
        s.query(DmsMcpToken).filter(DmsMcpToken.id == token_id).delete()
        return {"success": True}


@router.put("/mcp/tokens/{token_id}/toggle", dependencies=[require_role("admin")])
def toggle_mcp_token(token_id: int):
    """Enable/disable an MCP token."""
    from dms_models import DmsMcpToken
    with get_dms_session() as s:
        t = s.query(DmsMcpToken).filter(DmsMcpToken.id == token_id).first()
        if not t:
            raise HTTPException(status_code=404, detail="Token not found")
        t.is_active = not t.is_active
        s.flush()
        return {"success": True, "is_active": t.is_active}


@router.post("/llm/test", dependencies=[require_role("admin")])
async def test_llm():
    """Test the current LLM configuration."""
    try:
        from llm_provider import get_llm_provider
        provider = get_llm_provider()
        result = provider.chat(
            [{"role": "user", "content": "请回复'LLM服务正常'这五个字"}],
            max_tokens=50,
            temperature=0,
        )
        provider_name = get_setting("llm_provider", "deepseek") or "deepseek"
        return {
            "provider": provider_name,
            "available": True,
            "message": f"LLM服务 ({provider_name}) 可用",
            "response": result[:100],
        }
    except Exception as e:
        provider_name = get_setting("llm_provider", "deepseek") or "deepseek"
        return {
            "provider": provider_name,
            "available": False,
            "message": f"LLM服务 ({provider_name}) 不可用: {str(e)[:200]}",
        }


# ============================================================
# Wildcard routes — MUST be last
# ============================================================

@router.get("/{key:path}")
async def get_single_setting(key: str):
    """Get a single setting by key (for agent recall, etc.)."""
    val = get_setting(key)
    return {"key": key, "value": val}


@router.put("/{key:path}", dependencies=[require_role("admin")])
async def update_setting(key: str, data: UpdateSettingRequest):
    """Update a single setting (managed or custom key like agent_memory_*)."""
    if key in MANAGED_SETTINGS:
        if key == "ocr_provider" and data.value not in ("deepseek", "bigmodel", "paddleocr"):
            raise HTTPException(status_code=400, detail="Invalid OCR provider")
        if key == "llm_provider" and data.value not in ("deepseek", "openrouter", "anthropic"):
            raise HTTPException(status_code=400, detail="Invalid LLM provider")
    desc = data.description or (MANAGED_SETTINGS.get(key, {}).get("description") if key in MANAGED_SETTINGS else None)
    set_setting(key, data.value, desc)
    return {"key": key, "value": data.value if key not in SENSITIVE_KEYS else "***", "success": True}
