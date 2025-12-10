"""管理员 Provider 管理路由。"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session

from src.api.base.admin_adapter import AdminApiAdapter
from src.api.base.pipeline import ApiRequestPipeline
from src.core.enums import ProviderBillingType
from src.core.exceptions import InvalidRequestException, NotFoundException
from src.database import get_db
from src.models.admin_requests import CreateProviderRequest, UpdateProviderRequest
from src.models.database import Provider

router = APIRouter(tags=["Provider CRUD"])
pipeline = ApiRequestPipeline()


@router.get("/")
async def list_providers(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    adapter = AdminListProvidersAdapter(skip=skip, limit=limit, is_active=is_active)
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=adapter.mode)


@router.post("/")
async def create_provider(request: Request, db: Session = Depends(get_db)):
    adapter = AdminCreateProviderAdapter()
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=adapter.mode)


@router.put("/{provider_id}")
async def update_provider(provider_id: str, request: Request, db: Session = Depends(get_db)):
    adapter = AdminUpdateProviderAdapter(provider_id=provider_id)
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=adapter.mode)


@router.delete("/{provider_id}")
async def delete_provider(provider_id: str, request: Request, db: Session = Depends(get_db)):
    adapter = AdminDeleteProviderAdapter(provider_id=provider_id)
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=adapter.mode)


class AdminListProvidersAdapter(AdminApiAdapter):
    def __init__(self, skip: int, limit: int, is_active: Optional[bool]):
        self.skip = skip
        self.limit = limit
        self.is_active = is_active

    async def handle(self, context):  # type: ignore[override]
        db = context.db
        query = db.query(Provider)
        if self.is_active is not None:
            query = query.filter(Provider.is_active == self.is_active)
        providers = query.offset(self.skip).limit(self.limit).all()

        data = []
        for provider in providers:
            api_format = getattr(provider, "api_format", None)
            base_url = getattr(provider, "base_url", None)
            api_key = getattr(provider, "api_key", None)
            priority = getattr(provider, "priority", provider.provider_priority)

            data.append(
                {
                    "id": provider.id,
                    "name": provider.name,
                    "display_name": provider.display_name,
                    "api_format": api_format.value if api_format else None,
                    "base_url": base_url,
                    "api_key": "***" if api_key else None,
                    "priority": priority,
                    "is_active": provider.is_active,
                    "created_at": provider.created_at.isoformat(),
                    "updated_at": provider.updated_at.isoformat() if provider.updated_at else None,
                }
            )
        context.add_audit_metadata(
            action="list_providers",
            filter_is_active=self.is_active,
            limit=self.limit,
            skip=self.skip,
            result_count=len(data),
        )
        return data


class AdminCreateProviderAdapter(AdminApiAdapter):
    async def handle(self, context):  # type: ignore[override]
        db = context.db
        payload = context.ensure_json_body()

        try:
            # 使用 Pydantic 模型进行验证（自动进行 SQL 注入、XSS、SSRF 检测）
            validated_data = CreateProviderRequest.model_validate(payload)
        except ValidationError as exc:
            # 将 Pydantic 验证错误转换为友好的错误信息
            errors = []
            for error in exc.errors():
                field = " -> ".join(str(x) for x in error["loc"])
                errors.append(f"{field}: {error['msg']}")
            raise InvalidRequestException("输入验证失败: " + "; ".join(errors))

        try:
            # 检查名称是否已存在
            existing = db.query(Provider).filter(Provider.name == validated_data.name).first()
            if existing:
                raise InvalidRequestException(f"提供商名称 '{validated_data.name}' 已存在")

            # 将验证后的数据转换为枚举类型
            billing_type = (
                ProviderBillingType(validated_data.billing_type)
                if validated_data.billing_type
                else ProviderBillingType.PAY_AS_YOU_GO
            )

            # 创建 Provider 对象
            provider = Provider(
                name=validated_data.name,
                display_name=validated_data.display_name,
                description=validated_data.description,
                website=validated_data.website,
                billing_type=billing_type,
                monthly_quota_usd=validated_data.monthly_quota_usd,
                quota_reset_day=validated_data.quota_reset_day,
                quota_last_reset_at=validated_data.quota_last_reset_at,
                quota_expires_at=validated_data.quota_expires_at,
                rpm_limit=validated_data.rpm_limit,
                provider_priority=validated_data.provider_priority,
                is_active=validated_data.is_active,
                rate_limit=validated_data.rate_limit,
                concurrent_limit=validated_data.concurrent_limit,
                config=validated_data.config,
            )

            db.add(provider)
            db.commit()
            db.refresh(provider)

            context.add_audit_metadata(
                action="create_provider",
                provider_id=provider.id,
                provider_name=provider.name,
                billing_type=provider.billing_type.value if provider.billing_type else None,
                is_active=provider.is_active,
                provider_priority=provider.provider_priority,
            )

            return {
                "id": provider.id,
                "name": provider.name,
                "display_name": provider.display_name,
                "message": "提供商创建成功",
            }
        except InvalidRequestException:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise


class AdminUpdateProviderAdapter(AdminApiAdapter):
    def __init__(self, provider_id: str):
        self.provider_id = provider_id

    async def handle(self, context):  # type: ignore[override]
        db = context.db
        payload = context.ensure_json_body()

        # 查找 Provider
        provider = db.query(Provider).filter(Provider.id == self.provider_id).first()
        if not provider:
            raise NotFoundException("提供商不存在", "provider")

        try:
            # 使用 Pydantic 模型进行验证（自动进行 SQL 注入、XSS、SSRF 检测）
            validated_data = UpdateProviderRequest.model_validate(payload)
        except ValidationError as exc:
            # 将 Pydantic 验证错误转换为友好的错误信息
            errors = []
            for error in exc.errors():
                field = " -> ".join(str(x) for x in error["loc"])
                errors.append(f"{field}: {error['msg']}")
            raise InvalidRequestException("输入验证失败: " + "; ".join(errors))

        try:
            # 更新字段（只更新非 None 的字段）
            update_data = validated_data.model_dump(exclude_unset=True)

            for field, value in update_data.items():
                if field == "billing_type" and value is not None:
                    # billing_type 需要转换为枚举
                    setattr(provider, field, ProviderBillingType(value))
                else:
                    setattr(provider, field, value)

            provider.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(provider)

            context.add_audit_metadata(
                action="update_provider",
                provider_id=provider.id,
                changed_fields=list(update_data.keys()),
                is_active=provider.is_active,
                provider_priority=provider.provider_priority,
            )

            return {
                "id": provider.id,
                "name": provider.name,
                "is_active": provider.is_active,
                "message": "提供商更新成功",
            }
        except InvalidRequestException:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise


class AdminDeleteProviderAdapter(AdminApiAdapter):
    def __init__(self, provider_id: str):
        self.provider_id = provider_id

    async def handle(self, context):  # type: ignore[override]
        db = context.db
        provider = db.query(Provider).filter(Provider.id == self.provider_id).first()
        if not provider:
            raise NotFoundException("提供商不存在", "provider")

        context.add_audit_metadata(
            action="delete_provider",
            provider_id=provider.id,
            provider_name=provider.name,
        )
        db.delete(provider)
        db.commit()
        return {"message": "提供商已删除"}
