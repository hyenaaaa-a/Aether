"""
IP 安全管理接口

提供 IP 黑白名单管理和速率限制统计
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from src.api.base.adapter import ApiMode
from src.api.base.authenticated_adapter import AuthenticatedApiAdapter
from src.api.base.pipeline import ApiRequestPipeline
from src.core.exceptions import InvalidRequestException, translate_pydantic_error
from src.core.logger import logger
from src.database import get_db
from src.services.rate_limit.ip_limiter import IPRateLimiter

router = APIRouter(prefix="/api/admin/security/ip", tags=["IP Security"])
pipeline = ApiRequestPipeline()


# ========== Pydantic 模型 ==========


class AddIPToBlacklistRequest(BaseModel):
    """添加 IP 到黑名单请求"""

    ip_address: str = Field(..., description="IP 地址")
    reason: str = Field(..., min_length=1, max_length=200, description="加入黑名单的原因")
    ttl: Optional[int] = Field(None, gt=0, description="过期时间（秒），None 表示永久")


class RemoveIPFromBlacklistRequest(BaseModel):
    """从黑名单移除 IP 请求"""

    ip_address: str = Field(..., description="IP 地址")


class AddIPToWhitelistRequest(BaseModel):
    """添加 IP 到白名单请求"""

    ip_address: str = Field(..., description="IP 地址或 CIDR 格式（如 192.168.1.0/24）")


class RemoveIPFromWhitelistRequest(BaseModel):
    """从白名单移除 IP 请求"""

    ip_address: str = Field(..., description="IP 地址")


# ========== API 端点 ==========


@router.post("/blacklist")
async def add_to_blacklist(request: Request, db: Session = Depends(get_db)):
    """Add IP to blacklist"""
    adapter = AddToBlacklistAdapter()
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=ApiMode.ADMIN)


@router.delete("/blacklist/{ip_address}")
async def remove_from_blacklist(ip_address: str, request: Request, db: Session = Depends(get_db)):
    """Remove IP from blacklist"""
    adapter = RemoveFromBlacklistAdapter(ip_address=ip_address)
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=ApiMode.ADMIN)


@router.get("/blacklist/stats")
async def get_blacklist_stats(request: Request, db: Session = Depends(get_db)):
    """Get blacklist statistics"""
    adapter = GetBlacklistStatsAdapter()
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=ApiMode.ADMIN)


@router.post("/whitelist")
async def add_to_whitelist(request: Request, db: Session = Depends(get_db)):
    """Add IP to whitelist"""
    adapter = AddToWhitelistAdapter()
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=ApiMode.ADMIN)


@router.delete("/whitelist/{ip_address}")
async def remove_from_whitelist(ip_address: str, request: Request, db: Session = Depends(get_db)):
    """Remove IP from whitelist"""
    adapter = RemoveFromWhitelistAdapter(ip_address=ip_address)
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=ApiMode.ADMIN)


@router.get("/whitelist")
async def get_whitelist(request: Request, db: Session = Depends(get_db)):
    """Get whitelist"""
    adapter = GetWhitelistAdapter()
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=ApiMode.ADMIN)


# ========== 适配器实现 ==========


class AddToBlacklistAdapter(AuthenticatedApiAdapter):
    """添加 IP 到黑名单适配器"""

    async def handle(self, context):  # type: ignore[override]
        payload = context.ensure_json_body()
        try:
            req = AddIPToBlacklistRequest.model_validate(payload)
        except ValidationError as e:
            errors = e.errors()
            if errors:
                raise InvalidRequestException(translate_pydantic_error(errors[0]))
            raise InvalidRequestException("请求数据验证失败")

        success = await IPRateLimiter.add_to_blacklist(req.ip_address, req.reason, req.ttl)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="添加 IP 到黑名单失败（Redis 不可用）",
            )

        return {
            "success": True,
            "message": f"IP {req.ip_address} 已加入黑名单",
            "reason": req.reason,
            "ttl": req.ttl or "永久",
        }


class RemoveFromBlacklistAdapter(AuthenticatedApiAdapter):
    """从黑名单移除 IP 适配器"""

    def __init__(self, ip_address: str):
        self.ip_address = ip_address

    async def handle(self, context):  # type: ignore[override]
        success = await IPRateLimiter.remove_from_blacklist(self.ip_address)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"IP {self.ip_address} 不在黑名单中"
            )

        return {"success": True, "message": f"IP {self.ip_address} 已从黑名单移除"}


class GetBlacklistStatsAdapter(AuthenticatedApiAdapter):
    """获取黑名单统计适配器"""

    async def handle(self, context):  # type: ignore[override]
        stats = await IPRateLimiter.get_blacklist_stats()
        return stats


class AddToWhitelistAdapter(AuthenticatedApiAdapter):
    """添加 IP 到白名单适配器"""

    async def handle(self, context):  # type: ignore[override]
        payload = context.ensure_json_body()
        try:
            req = AddIPToWhitelistRequest.model_validate(payload)
        except ValidationError as e:
            errors = e.errors()
            if errors:
                raise InvalidRequestException(translate_pydantic_error(errors[0]))
            raise InvalidRequestException("请求数据验证失败")

        success = await IPRateLimiter.add_to_whitelist(req.ip_address)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"添加 IP 到白名单失败（无效的 IP 格式或 Redis 不可用）",
            )

        return {"success": True, "message": f"IP {req.ip_address} 已加入白名单"}


class RemoveFromWhitelistAdapter(AuthenticatedApiAdapter):
    """从白名单移除 IP 适配器"""

    def __init__(self, ip_address: str):
        self.ip_address = ip_address

    async def handle(self, context):  # type: ignore[override]
        success = await IPRateLimiter.remove_from_whitelist(self.ip_address)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"IP {self.ip_address} 不在白名单中"
            )

        return {"success": True, "message": f"IP {self.ip_address} 已从白名单移除"}


class GetWhitelistAdapter(AuthenticatedApiAdapter):
    """获取白名单适配器"""

    async def handle(self, context):  # type: ignore[override]
        whitelist = await IPRateLimiter.get_whitelist()
        return {"whitelist": list(whitelist), "total": len(whitelist)}
