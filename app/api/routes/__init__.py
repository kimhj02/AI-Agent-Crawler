"""FastAPI 라우터 모듈."""

from app.api.routes.live import create_legacy_router, create_v1_router
from app.api.routes.spring_native import create_spring_native_router

__all__ = [
    "create_legacy_router",
    "create_v1_router",
    "create_spring_native_router",
]
