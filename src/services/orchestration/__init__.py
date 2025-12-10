"""
Orchestration 模块

提供请求编排相关的组件：
- FallbackOrchestrator: 故障转移编排器，协调请求的完整生命周期
- CandidateResolver: 候选解析器，负责获取和排序可用的 Provider 组合
- RequestDispatcher: 请求分发器，负责执行单个候选请求
- ErrorClassifier: 错误分类器，负责错误分类和处理策略
"""

from .candidate_resolver import CandidateResolver
from .error_classifier import ErrorAction, ErrorClassifier
from .fallback_orchestrator import FallbackOrchestrator
from .request_dispatcher import RequestDispatcher

__all__ = [
    "FallbackOrchestrator",
    "CandidateResolver",
    "RequestDispatcher",
    "ErrorClassifier",
    "ErrorAction",
]
