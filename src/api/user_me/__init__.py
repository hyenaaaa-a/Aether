"""Routes for authenticated user self-service APIs."""

from fastapi import APIRouter

from .routes import router as me_router

router = APIRouter()
router.include_router(me_router)

__all__ = ["router"]
