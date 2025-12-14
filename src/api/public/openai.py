"""
OpenAI API 端点

- /v1/chat/completions - OpenAI Chat API
- /v1/responses - OpenAI Responses API (CLI)
- /v1/models - 模型列表 API
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.api.base.pipeline import ApiRequestPipeline
from src.api.handlers.openai import OpenAIChatAdapter
from src.api.handlers.openai_cli import OpenAICliAdapter
from src.core.api_format_metadata import get_api_format_definition
from src.core.enums import APIFormat
from src.database import get_db
from src.models.database import GlobalModel, ModelMapping

_openai_def = get_api_format_definition(APIFormat.OPENAI)
router = APIRouter(tags=["OpenAI API"], prefix=_openai_def.path_prefix)
pipeline = ApiRequestPipeline()


@router.get("/v1/models")
async def list_models(
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    返回所有可用的模型别名
    
    返回 OpenAI 兼容格式，只包含别名（ModelMapping.source_model）
    """
    # 获取所有活跃的别名（ModelMapping.source_model）
    aliases = (
        db.query(ModelMapping.source_model)
        .join(GlobalModel, ModelMapping.target_global_model_id == GlobalModel.id)
        .filter(
            ModelMapping.is_active.is_(True),
            GlobalModel.is_active.is_(True),
        )
        .distinct()
        .all()
    )
    
    # 构建 OpenAI 兼容的响应格式
    data: List[Dict[str, Any]] = []
    for (alias,) in sorted(aliases, key=lambda x: x[0]):
        data.append({
            "id": alias,
            "object": "model",
            "created": 0,
            "owned_by": "aether",
        })
    
    return {
        "object": "list",
        "data": data,
    }


@router.post("/v1/chat/completions")
async def create_chat_completion(
    http_request: Request,
    db: Session = Depends(get_db),
):
    adapter = OpenAIChatAdapter()
    return await pipeline.run(
        adapter=adapter,
        http_request=http_request,
        db=db,
        mode=adapter.mode,
        api_format_hint=adapter.allowed_api_formats[0],
    )


@router.post("/v1/responses")
async def create_responses(
    http_request: Request,
    db: Session = Depends(get_db),
):
    adapter = OpenAICliAdapter()
    return await pipeline.run(
        adapter=adapter,
        http_request=http_request,
        db=db,
        mode=adapter.mode,
        api_format_hint=adapter.allowed_api_formats[0],
    )

