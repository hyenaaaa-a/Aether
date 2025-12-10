"""
模型映射中间件
根据数据库中的配置，将用户请求的模型映射到提供商的实际模型
"""

from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from src.core.cache_utils import SyncLRUCache
from src.core.logger import logger
from src.models.claude import ClaudeMessagesRequest
from src.models.database import GlobalModel, Model, ModelMapping, Provider, ProviderEndpoint
from src.services.cache.model_cache import ModelCacheService
from src.services.model.mapping_resolver import (
    get_model_mapping_resolver,
    resolve_model_to_global_name,
)



class ModelMapperMiddleware:
    """
    模型映射中间件
    负责将用户请求的模型名映射到提供商的实际模型名
    """

    def __init__(self, db: Session, cache_max_size: int = 1000, cache_ttl: int = 300):
        """
        初始化模型映射中间件

        Args:
            db: 数据库会话
            cache_max_size: 缓存最大容量（默认 1000）
            cache_ttl: 缓存过期时间（秒，默认 300）
        """
        self.db = db
        self._cache = SyncLRUCache(max_size=cache_max_size, ttl=cache_ttl)

        logger.debug(f"[ModelMapper] 初始化（max_size={cache_max_size}, ttl={cache_ttl}s）")

        # 注册到缓存失效服务
        try:
            from src.services.cache.invalidation import get_cache_invalidation_service

            cache_service = get_cache_invalidation_service()
            cache_service.register_model_mapper(self)
            logger.debug("[ModelMapper] 已注册到缓存失效服务")
        except Exception as e:
            logger.warning(f"[ModelMapper] 注册缓存失效服务失败: {e}")

    async def apply_mapping(
        self, request: ClaudeMessagesRequest, provider: Provider
    ) -> ClaudeMessagesRequest:
        """
        应用模型映射到请求

        Args:
            request: 原始请求
            provider: 目标提供商

        Returns:
            应用映射后的请求
        """
        # 获取请求的模型名
        source_model = request.model

        # 查找映射
        mapping = await self.get_mapping(source_model, provider.id)

        if mapping:
            # 应用映射
            original_model = request.model
            request.model = mapping.model.provider_model_name

            logger.debug(f"Applied model mapping for provider {provider.name}: "
                f"{original_model} -> {mapping.model.provider_model_name}")
        else:
            # 没有找到映射，使用原始模型名
            logger.debug(f"No model mapping found for {source_model} with provider {provider.name}, "
                f"forwarding with original model name")

        return request

    async def get_mapping(
        self, source_model: str, provider_id: str
    ) -> Optional[ModelMapping]:  # UUID
        """
        获取模型映射

        优化后逻辑:
        1. 使用统一的 ModelMappingResolver 解析别名（带缓存）
        2. 通过 GlobalModel 找到该 Provider 的 Model 实现
        3. 使用独立的映射缓存

        Args:
            source_model: 用户请求的模型名或别名
            provider_id: 提供商ID (UUID)

        Returns:
            模型映射对象（包含 model 字段），如果没有找到返回None
        """
        # 检查缓存
        cache_key = f"{provider_id}:{source_model}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        mapping = None

        # 步骤 1 & 2: 通过统一的模型映射解析服务
        mapping_resolver = get_model_mapping_resolver()
        global_model = await mapping_resolver.get_global_model_by_request(
            self.db, source_model, provider_id
        )

        if not global_model:
            logger.debug(f"GlobalModel not found: {source_model} (provider={provider_id[:8]}...)")
            self._cache[cache_key] = None
            return None

        # 步骤 3: 查找该 Provider 是否有实现这个 GlobalModel 的 Model（使用缓存）
        model = await ModelCacheService.get_model_by_provider_and_global_model(
            self.db, provider_id, global_model.id
        )

        if model:
            # 只有当模型名发生变化时才返回映射
            if model.provider_model_name != source_model:
                mapping = type(
                    "obj",
                    (object,),
                    {
                        "source_model": source_model,
                        "model": model,
                        "is_active": True,
                        "provider_id": provider_id,
                    },
                )()

                logger.debug(f"Found model mapping: {source_model} -> {model.provider_model_name} "
                    f"(provider={provider_id[:8]}...)")
            else:
                logger.debug(f"Model found but no name change: {source_model} (provider={provider_id[:8]}...)")

        # 缓存结果
        self._cache[cache_key] = mapping

        return mapping

    def get_all_mappings(self, provider_id: str) -> List[ModelMapping]:  # UUID
        """
        获取提供商的所有可用模型(通过 GlobalModel)

        方案 A: 返回该 Provider 所有可用的 GlobalModel

        Args:
            provider_id: 提供商ID (UUID)

        Returns:
            模型映射列表（模拟的 ModelMapping 对象列表）
        """
        # 查询该 Provider 的所有活跃 Model
        models = (
            self.db.query(Model)
            .join(GlobalModel)
            .filter(
                Model.provider_id == provider_id,
                Model.is_active == True,
                GlobalModel.is_active == True,
            )
            .all()
        )

        # 构造兼容的 ModelMapping 对象列表
        mappings = []
        for model in models:
            mapping = type(
                "obj",
                (object,),
                {
                    "source_model": model.global_model.name,
                    "model": model,
                    "is_active": True,
                    "provider_id": provider_id,
                },
            )()
            mappings.append(mapping)

        return mappings

    def get_supported_models(self, provider_id: str) -> List[str]:  # UUID
        """
        获取提供商支持的所有源模型名

        Args:
            provider_id: 提供商ID (UUID)

        Returns:
            支持的模型名列表
        """
        mappings = self.get_all_mappings(provider_id)
        return [mapping.source_model for mapping in mappings]

    async def validate_request(
        self, request: ClaudeMessagesRequest, provider: Provider
    ) -> tuple[bool, Optional[str]]:
        """
        验证请求是否符合映射的限制

        Args:
            request: 请求对象
            provider: 提供商对象

        Returns:
            (是否有效, 错误信息)
        """
        mapping = await self.get_mapping(request.model, provider.id)

        if not mapping:
            # 没有映射，可能是默认支持的模型
            return True, None

        if not mapping.is_active:
            return False, f"Model mapping for {request.model} is disabled"

        # 不限制max_tokens，作为中转服务不应该限制用户的请求
        # if request.max_tokens and request.max_tokens > mapping.max_output_tokens:
        #     return False, (
        #         f"Requested max_tokens {request.max_tokens} exceeds limit "
        #         f"{mapping.max_output_tokens} for model {request.model}"
        #     )

        # 可以添加更多验证逻辑，比如检查输入长度等

        return True, None

    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
        logger.debug("Model mapping cache cleared")

    def refresh_cache(self, provider_id: Optional[str] = None):  # UUID
        """
        刷新缓存

        Args:
            provider_id: 如果指定，只刷新该提供商的缓存 (UUID)
        """
        if provider_id:
            # 清除特定提供商的缓存
            keys_to_remove = [
                key for key in self._cache.keys() if key.startswith(f"{provider_id}:")
            ]
            for key in keys_to_remove:
                del self._cache[key]
            logger.debug(f"Refreshed cache for provider {provider_id}")
        else:
            # 清空所有缓存
            self.clear_cache()


class ModelRoutingMiddleware:
    """
    模型路由中间件
    根据模型名选择合适的提供商
    """

    def __init__(self, db: Session):
        """
        初始化模型路由中间件

        Args:
            db: 数据库会话
        """
        self.db = db
        self.mapper = ModelMapperMiddleware(db)

    def select_provider(
        self,
        model_name: str,
        preferred_provider: Optional[str] = None,
        allowed_api_formats: Optional[List[str]] = None,
        request_id: Optional[str] = None,
    ) -> Optional[Provider]:
        """
        根据模型名选择提供商

        逻辑：
        1. 如果指定了提供商，使用指定的提供商
        2. 如果没指定，使用默认提供商
        3. 选定提供商后，会检查该提供商的模型映射（在apply_mapping中处理）
        4. 如果指定了allowed_api_formats，只选择符合格式的提供商

        Args:
            model_name: 请求的模型名
            preferred_provider: 首选提供商名称
            allowed_api_formats: 允许的API格式列表（如 ['CLAUDE', 'CLAUDE_CLI']）
            request_id: 请求ID（用于日志关联）

        Returns:
            选中的提供商，如果没有找到返回None
        """
        request_prefix = f"ID:{request_id} | " if request_id else ""

        # 1. 如果指定了提供商，直接使用
        if preferred_provider:
            provider = (
                self.db.query(Provider)
                .filter(Provider.name == preferred_provider, Provider.is_active == True)
                .first()
            )

            if provider:
                # 检查API格式 - 从 endpoints 中检查
                if allowed_api_formats:
                    # 检查是否有符合要求的活跃端点
                    has_matching_endpoint = any(
                        ep.is_active and ep.api_format and ep.api_format in allowed_api_formats
                        for ep in provider.endpoints
                    )
                    if not has_matching_endpoint:
                        logger.warning(f"Specified provider {provider.name} has no active endpoints with allowed API formats ({allowed_api_formats})")
                        # 不返回该提供商，继续查找
                    else:
                        logger.debug(f"  └─ {request_prefix}使用指定提供商: {provider.name} | 模型:{model_name}")
                        return provider
                else:
                    logger.debug(f"  └─ {request_prefix}使用指定提供商: {provider.name} | 模型:{model_name}")
                    return provider
            else:
                logger.warning(f"Specified provider {preferred_provider} not found or inactive")

        # 2. 查找优先级最高的活动提供商（provider_priority 最小）
        query = self.db.query(Provider).filter(Provider.is_active == True)

        # 如果指定了API格式过滤，添加过滤条件 - 检查是否有符合要求的 endpoint
        if allowed_api_formats:
            query = (
                query.join(ProviderEndpoint)
                .filter(
                    ProviderEndpoint.is_active == True,
                    ProviderEndpoint.api_format.in_(allowed_api_formats),
                )
                .distinct()
            )

        # 按 provider_priority 排序，优先级最高（数字最小）的在前
        best_provider = query.order_by(Provider.provider_priority.asc(), Provider.id.asc()).first()

        if best_provider:
            logger.debug(f"  └─ {request_prefix}使用优先级最高提供商: {best_provider.name} (priority:{best_provider.provider_priority}) | 模型:{model_name}")
            return best_provider

        # 3. 没有任何活动提供商
        if allowed_api_formats:
            logger.error(f"No active providers found with allowed API formats {allowed_api_formats}. Please configure at least one provider.")
        else:
            logger.error("No active providers found. Please configure at least one provider.")
        return None

    def get_available_models(self) -> Dict[str, List[str]]:
        """
        获取所有可用的模型及其提供商

        方案 A: 基于 GlobalModel 查询

        Returns:
            字典，键为 GlobalModel.name，值为支持该模型的提供商名列表
        """
        result = {}

        # 查询所有活跃的 GlobalModel 及其 Provider
        models = (
            self.db.query(GlobalModel.name, Provider.name)
            .join(Model, GlobalModel.id == Model.global_model_id)
            .join(Provider, Model.provider_id == Provider.id)
            .filter(
                GlobalModel.is_active == True, Model.is_active == True, Provider.is_active == True
            )
            .all()
        )

        for global_model_name, provider_name in models:
            if global_model_name not in result:
                result[global_model_name] = []
            if provider_name not in result[global_model_name]:
                result[global_model_name].append(provider_name)

        return result

    async def get_cheapest_provider(self, model_name: str) -> Optional[Provider]:
        """
        获取某个模型最便宜的提供商

        方案 A: 通过 GlobalModel 查找

        Args:
            model_name: GlobalModel 名称或别名

        Returns:
            最便宜的提供商
        """
        # 步骤 1: 解析模型名
        global_model_name = await resolve_model_to_global_name(self.db, model_name)

        # 步骤 2: 查找 GlobalModel
        global_model = (
            self.db.query(GlobalModel)
            .filter(GlobalModel.name == global_model_name, GlobalModel.is_active == True)
            .first()
        )

        if not global_model:
            return None

        # 步骤 3: 查询所有支持该模型的 Provider 及其价格
        models_with_providers = (
            self.db.query(Provider, Model)
            .join(Model, Provider.id == Model.provider_id)
            .filter(
                Model.global_model_id == global_model.id,
                Model.is_active == True,
                Provider.is_active == True,
            )
            .all()
        )

        if not models_with_providers:
            return None

        # 按总价格排序（输入+输出价格）
        cheapest = min(
            models_with_providers, key=lambda x: x[1].input_price_per_1m + x[1].output_price_per_1m
        )

        provider = cheapest[0]
        model = cheapest[1]

        logger.debug(f"Selected cheapest provider {provider.name} for model {model_name} "
            f"(input: ${model.input_price_per_1m}/M, output: ${model.output_price_per_1m}/M)")

        return provider
