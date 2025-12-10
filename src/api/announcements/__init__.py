'"""Announcement system routers."""'

from fastapi import APIRouter

from .routes import router as announcement_router

router = APIRouter()
router.include_router(announcement_router)

__all__ = ["router"]
