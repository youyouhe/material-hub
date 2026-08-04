"""Capabilities API — 对外能力广播（SmartBid 契约 3.1）。

调用方在流程启动预检时获取并缓存于本次运行；无敏感信息、廉价调用。
"""

import logging

from fastapi import APIRouter

logger = logging.getLogger("materialhub.routers.v2_capabilities")

router = APIRouter(prefix="/api/v2", tags=["capabilities"])

API_VERSION = "2.0"


@router.get("/capabilities")
async def get_capabilities():
    """Broadcast deployment capabilities, currently the mock mode switch."""
    from mock_generator import is_mock_enabled
    enabled = is_mock_enabled()
    return {
        "version": API_VERSION,
        "mock": {
            "enabled": enabled,
            "mode": "enabled" if enabled else "disabled",
        },
    }
