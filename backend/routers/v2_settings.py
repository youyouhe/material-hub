"""System settings API endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
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


class BatchUpdateRequest(BaseModel):
    settings: dict[str, str]


def _mask_sensitive(key: str, value: str) -> str:
    """Mask sensitive values for display."""
    if key in SENSITIVE_KEYS and value:
        if len(value) <= 8:
            return "****"
        return value[:4] + "****" + value[-4:]
    return value


@router.get("/", dependencies=[require_role("admin")])
async def list_settings():
    """List all system settings."""
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


@router.put("/{key}", dependencies=[require_role("admin")])
async def update_setting(key: str, data: UpdateSettingRequest):
    """Update a single setting."""
    if key not in MANAGED_SETTINGS:
        raise HTTPException(status_code=400, detail=f"Unknown setting: {key}")

    # Validate specific settings
    if key == "ocr_provider" and data.value not in ("deepseek", "bigmodel", "paddleocr"):
        raise HTTPException(status_code=400, detail="OCR provider must be 'deepseek', 'bigmodel', or 'paddleocr'")
    if key == "llm_provider" and data.value not in ("deepseek", "openrouter", "anthropic"):
        raise HTTPException(status_code=400, detail="LLM provider must be 'deepseek', 'openrouter', or 'anthropic'")

    set_setting(key, data.value, MANAGED_SETTINGS[key]["description"])
    return {"key": key, "value": _mask_sensitive(key, data.value), "success": True}


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
