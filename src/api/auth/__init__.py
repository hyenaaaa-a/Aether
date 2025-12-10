"""Authentication route group."""

from fastapi import APIRouter

from .routes import router as auth_router

router = APIRouter()
router.include_router(auth_router)

__all__ = ["router"]
