"""Public-facing API routers."""

from fastapi import APIRouter

from .capabilities import router as capabilities_router
from .catalog import router as catalog_router
from .claude import router as claude_router
from .gemini import router as gemini_router
from .openai import router as openai_router
from .system_catalog import router as system_catalog_router

router = APIRouter()
router.include_router(claude_router, tags=["Claude API"])
router.include_router(openai_router)
router.include_router(gemini_router, tags=["Gemini API"])
router.include_router(system_catalog_router, tags=["System Catalog"])
router.include_router(catalog_router)
router.include_router(capabilities_router)

__all__ = ["router"]
