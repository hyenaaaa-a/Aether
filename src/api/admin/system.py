"""系统设置API端点。"""

from dataclasses import dataclass
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from src.api.base.admin_adapter import AdminApiAdapter
from src.api.base.pipeline import ApiRequestPipeline
from src.core.exceptions import InvalidRequestException, NotFoundException, translate_pydantic_error
from src.database import get_db
from src.models.api import SystemSettingsRequest, SystemSettingsResponse
from src.models.database import ApiKey, Provider, Usage, User
from src.services.system.config import SystemConfigService

router = APIRouter(prefix="/api/admin/system", tags=["Admin - System"])
pipeline = ApiRequestPipeline()


@router.get("/settings")
async def get_system_settings(request: Request, db: Session = Depends(get_db)):
    """获取系统设置（管理员）"""

    adapter = AdminGetSystemSettingsAdapter()
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=adapter.mode)


@router.put("/settings")
async def update_system_settings(http_request: Request, db: Session = Depends(get_db)):
    """更新系统设置（管理员）"""

    adapter = AdminUpdateSystemSettingsAdapter()
    return await pipeline.run(adapter=adapter, http_request=http_request, db=db, mode=adapter.mode)


@router.get("/configs")
async def get_all_system_configs(request: Request, db: Session = Depends(get_db)):
    """获取所有系统配置（管理员）"""

    adapter = AdminGetAllConfigsAdapter()
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=adapter.mode)


@router.get("/configs/{key}")
async def get_system_config(key: str, request: Request, db: Session = Depends(get_db)):
    """获取特定系统配置（管理员）"""

    adapter = AdminGetSystemConfigAdapter(key=key)
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=adapter.mode)


@router.put("/configs/{key}")
async def set_system_config(
    key: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """设置系统配置（管理员）"""

    adapter = AdminSetSystemConfigAdapter(key=key)
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=adapter.mode)


@router.delete("/configs/{key}")
async def delete_system_config(key: str, request: Request, db: Session = Depends(get_db)):
    """删除系统配置（管理员）"""

    adapter = AdminDeleteSystemConfigAdapter(key=key)
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=adapter.mode)


@router.get("/stats")
async def get_system_stats(request: Request, db: Session = Depends(get_db)):
    adapter = AdminSystemStatsAdapter()
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=adapter.mode)


@router.post("/cleanup")
async def trigger_cleanup(request: Request, db: Session = Depends(get_db)):
    """Manually trigger usage record cleanup task"""
    adapter = AdminTriggerCleanupAdapter()
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=adapter.mode)


@router.get("/api-formats")
async def get_api_formats(request: Request, db: Session = Depends(get_db)):
    """获取所有可用的API格式列表"""
    adapter = AdminGetApiFormatsAdapter()
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=adapter.mode)


# -------- 系统设置适配器 --------


class AdminGetSystemSettingsAdapter(AdminApiAdapter):
    async def handle(self, context):  # type: ignore[override]
        db = context.db
        default_provider = SystemConfigService.get_default_provider(db)
        default_model = SystemConfigService.get_config(db, "default_model")
        enable_usage_tracking = (
            SystemConfigService.get_config(db, "enable_usage_tracking", "true") == "true"
        )

        return SystemSettingsResponse(
            default_provider=default_provider,
            default_model=default_model,
            enable_usage_tracking=enable_usage_tracking,
        )


class AdminUpdateSystemSettingsAdapter(AdminApiAdapter):
    async def handle(self, context):  # type: ignore[override]
        db = context.db
        payload = context.ensure_json_body()
        try:
            settings_request = SystemSettingsRequest.model_validate(payload)
        except ValidationError as e:
            errors = e.errors()
            if errors:
                raise InvalidRequestException(translate_pydantic_error(errors[0]))
            raise InvalidRequestException("请求数据验证失败")

        if settings_request.default_provider is not None:
            provider = (
                db.query(Provider)
                .filter(
                    Provider.name == settings_request.default_provider,
                    Provider.is_active.is_(True),
                )
                .first()
            )

            if not provider and settings_request.default_provider != "":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"提供商 '{settings_request.default_provider}' 不存在或未启用",
                )

            if settings_request.default_provider:
                SystemConfigService.set_default_provider(db, settings_request.default_provider)
            else:
                SystemConfigService.delete_config(db, "default_provider")

        if settings_request.default_model is not None:
            if settings_request.default_model:
                SystemConfigService.set_config(db, "default_model", settings_request.default_model)
            else:
                SystemConfigService.delete_config(db, "default_model")

        if settings_request.enable_usage_tracking is not None:
            SystemConfigService.set_config(
                db,
                "enable_usage_tracking",
                str(settings_request.enable_usage_tracking).lower(),
            )

        return {"message": "系统设置更新成功"}


class AdminGetAllConfigsAdapter(AdminApiAdapter):
    async def handle(self, context):  # type: ignore[override]
        return SystemConfigService.get_all_configs(context.db)


@dataclass
class AdminGetSystemConfigAdapter(AdminApiAdapter):
    key: str

    async def handle(self, context):  # type: ignore[override]
        value = SystemConfigService.get_config(context.db, self.key)
        if value is None:
            raise NotFoundException(f"配置项 '{self.key}' 不存在")
        return {"key": self.key, "value": value}


@dataclass
class AdminSetSystemConfigAdapter(AdminApiAdapter):
    key: str

    async def handle(self, context):  # type: ignore[override]
        payload = context.ensure_json_body()
        config = SystemConfigService.set_config(
            context.db,
            self.key,
            payload.get("value"),
            payload.get("description"),
        )

        return {
            "key": config.key,
            "value": config.value,
            "description": config.description,
            "updated_at": config.updated_at.isoformat(),
        }


@dataclass
class AdminDeleteSystemConfigAdapter(AdminApiAdapter):
    key: str

    async def handle(self, context):  # type: ignore[override]
        deleted = SystemConfigService.delete_config(context.db, self.key)
        if not deleted:
            raise NotFoundException(f"配置项 '{self.key}' 不存在")
        return {"message": f"配置项 '{self.key}' 已删除"}


class AdminSystemStatsAdapter(AdminApiAdapter):
    async def handle(self, context):  # type: ignore[override]
        db = context.db
        total_users = db.query(User).count()
        active_users = db.query(User).filter(User.is_active.is_(True)).count()
        total_providers = db.query(Provider).count()
        active_providers = db.query(Provider).filter(Provider.is_active.is_(True)).count()
        total_api_keys = db.query(ApiKey).count()
        total_requests = db.query(Usage).count()

        return {
            "users": {"total": total_users, "active": active_users},
            "providers": {"total": total_providers, "active": active_providers},
            "api_keys": total_api_keys,
            "requests": total_requests,
        }


class AdminTriggerCleanupAdapter(AdminApiAdapter):
    async def handle(self, context):  # type: ignore[override]
        """手动触发清理任务"""
        from datetime import datetime, timedelta, timezone

        from sqlalchemy import func

        from src.services.system.cleanup_scheduler import get_cleanup_scheduler

        db = context.db

        # 获取清理前的统计信息
        total_before = db.query(Usage).count()
        with_body_before = (
            db.query(Usage)
            .filter((Usage.request_body.isnot(None)) | (Usage.response_body.isnot(None)))
            .count()
        )
        with_headers_before = (
            db.query(Usage)
            .filter((Usage.request_headers.isnot(None)) | (Usage.response_headers.isnot(None)))
            .count()
        )

        # 触发清理
        cleanup_scheduler = get_cleanup_scheduler()
        await cleanup_scheduler._perform_cleanup()

        # 获取清理后的统计信息
        total_after = db.query(Usage).count()
        with_body_after = (
            db.query(Usage)
            .filter((Usage.request_body.isnot(None)) | (Usage.response_body.isnot(None)))
            .count()
        )
        with_headers_after = (
            db.query(Usage)
            .filter((Usage.request_headers.isnot(None)) | (Usage.response_headers.isnot(None)))
            .count()
        )

        return {
            "message": "清理任务执行完成",
            "stats": {
                "total_records": {
                    "before": total_before,
                    "after": total_after,
                    "deleted": total_before - total_after,
                },
                "body_fields": {
                    "before": with_body_before,
                    "after": with_body_after,
                    "cleaned": with_body_before - with_body_after,
                },
                "header_fields": {
                    "before": with_headers_before,
                    "after": with_headers_after,
                    "cleaned": with_headers_before - with_headers_after,
                },
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


class AdminGetApiFormatsAdapter(AdminApiAdapter):
    async def handle(self, context):  # type: ignore[override]
        """获取所有可用的API格式"""
        from src.core.api_format_metadata import API_FORMAT_DEFINITIONS
        from src.core.enums import APIFormat

        _ = context  # 参数保留以符合接口规范

        formats = []
        for api_format in APIFormat:
            definition = API_FORMAT_DEFINITIONS.get(api_format)
            formats.append(
                {
                    "value": api_format.value,
                    "label": api_format.value,
                    "default_path": definition.default_path if definition else "/",
                    "aliases": list(definition.aliases) if definition else [],
                }
            )

        return {"formats": formats}
