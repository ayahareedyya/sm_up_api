"""
Health Check Endpoints

System health and status monitoring endpoints.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime
import torch
import redis
import logging

from app.core.config import settings
from app.core.database import get_db, check_db_connection
from app.models.schemas import HealthCheckResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/health", tags=["health"])


def check_redis_connection() -> bool:
    """Check Redis connectivity."""
    try:
        r = redis.from_url(settings.redis_url)
        r.ping()
        return True
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        return False


def check_gpu_availability() -> bool:
    """Check GPU availability."""
    try:
        return torch.cuda.is_available()
    except Exception as e:
        logger.error(f"GPU check failed: {e}")
        return False


@router.get("/", response_model=HealthCheckResponse)
async def health_check(db: Session = Depends(get_db)):
    """
    Comprehensive health check endpoint.
    
    Returns:
        HealthCheckResponse: System health status
    """
    # Check database
    db_status = check_db_connection()
    
    # Check Redis
    redis_status = check_redis_connection()
    
    # Check GPU
    gpu_status = check_gpu_availability()
    
    # Determine overall status
    overall_status = "healthy" if all([db_status, redis_status, gpu_status]) else "unhealthy"
    
    return HealthCheckResponse(
        status=overall_status,
        timestamp=datetime.utcnow(),
        version=settings.api_version,
        database=db_status,
        redis=redis_status,
        gpu=gpu_status
    )


@router.get("/simple")
async def simple_health_check():
    """
    Simple health check for load balancers.
    
    Returns:
        dict: Basic status information
    """
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/database")
async def database_health_check(db: Session = Depends(get_db)):
    """
    Database-specific health check.
    
    Returns:
        dict: Database connectivity status
    """
    db_status = check_db_connection()
    
    return {
        "database": {
            "status": "connected" if db_status else "disconnected",
            "timestamp": datetime.utcnow().isoformat()
        }
    }


@router.get("/redis")
async def redis_health_check():
    """
    Redis-specific health check.
    
    Returns:
        dict: Redis connectivity status
    """
    redis_status = check_redis_connection()
    
    return {
        "redis": {
            "status": "connected" if redis_status else "disconnected",
            "timestamp": datetime.utcnow().isoformat()
        }
    }


@router.get("/gpu")
async def gpu_health_check():
    """
    GPU-specific health check.
    
    Returns:
        dict: GPU availability and information
    """
    gpu_available = check_gpu_availability()
    gpu_info = {}
    
    if gpu_available:
        try:
            gpu_info = {
                "device_count": torch.cuda.device_count(),
                "current_device": torch.cuda.current_device(),
                "device_name": torch.cuda.get_device_name(),
                "memory_allocated": torch.cuda.memory_allocated(),
                "memory_reserved": torch.cuda.memory_reserved(),
                "memory_total": torch.cuda.get_device_properties(0).total_memory
            }
        except Exception as e:
            logger.error(f"Error getting GPU info: {e}")
    
    return {
        "gpu": {
            "available": gpu_available,
            "info": gpu_info,
            "timestamp": datetime.utcnow().isoformat()
        }
    }
