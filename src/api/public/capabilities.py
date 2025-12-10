"""
能力配置公共 API

提供系统支持的能力列表，供前端展示和配置使用。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.core.key_capabilities import (
    get_all_capabilities,
    get_user_configurable_capabilities,
)
from src.database import get_db

router = APIRouter(prefix="/api/capabilities", tags=["Capabilities"])


@router.get("")
async def list_capabilities():
    """获取所有能力定义"""
    return {
        "capabilities": [
            {
                "name": cap.name,
                "display_name": cap.display_name,
                "short_name": cap.short_name,
                "description": cap.description,
                "match_mode": cap.match_mode.value,
                "config_mode": cap.config_mode.value,
            }
            for cap in get_all_capabilities()
        ]
    }


@router.get("/user-configurable")
async def list_user_configurable_capabilities():
    """获取用户可配置的能力列表（用于前端展示配置选项）"""
    return {
        "capabilities": [
            {
                "name": cap.name,
                "display_name": cap.display_name,
                "short_name": cap.short_name,
                "description": cap.description,
                "match_mode": cap.match_mode.value,
                "config_mode": cap.config_mode.value,
            }
            for cap in get_user_configurable_capabilities()
        ]
    }


@router.get("/model/{model_name}")
async def get_model_supported_capabilities(
    model_name: str,
    db: Session = Depends(get_db),
):
    """
    获取指定模型支持的能力列表

    Args:
        model_name: 模型名称（如 claude-sonnet-4-20250514）

    Returns:
        模型支持的能力列表，以及每个能力的详细定义
    """
    from src.services.model.mapping_resolver import get_model_mapping_resolver

    mapping_resolver = get_model_mapping_resolver()
    global_model = await mapping_resolver.get_global_model_by_request(db, model_name, None)

    if not global_model:
        return {
            "model": model_name,
            "supported_capabilities": [],
            "capability_details": [],
            "error": "模型不存在",
        }

    supported_caps = global_model.supported_capabilities or []

    # 获取支持的能力详情
    all_caps = {cap.name: cap for cap in get_all_capabilities()}
    capability_details = []
    for cap_name in supported_caps:
        if cap_name in all_caps:
            cap = all_caps[cap_name]
            capability_details.append({
                "name": cap.name,
                "display_name": cap.display_name,
                "description": cap.description,
                "match_mode": cap.match_mode.value,
                "config_mode": cap.config_mode.value,
            })

    return {
        "model": model_name,
        "global_model_id": str(global_model.id),
        "global_model_name": global_model.name,
        "supported_capabilities": supported_caps,
        "capability_details": capability_details,
    }
