"""
API v1 Router

Central router for all v1 API endpoints.
"""

from fastapi import APIRouter
from app.api.v1.endpoints import health, auth, images

# Create main v1 router
router = APIRouter(prefix="/api/v1")

# Include all endpoint routers
router.include_router(health.router, tags=["health"])
router.include_router(auth.router, tags=["authentication"])
router.include_router(images.router, tags=["image-processing"])

# Export router
__all__ = ["router"]
