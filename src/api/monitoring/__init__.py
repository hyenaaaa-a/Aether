"""User monitoring routers."""

from fastapi import APIRouter

from .user import router as monitoring_router

router = APIRouter()
router.include_router(monitoring_router)

__all__ = ["router"]
