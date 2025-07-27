"""
Application Configuration

Centralized configuration management using Pydantic Settings.
"""

from pydantic import BaseSettings, Field, validator
from typing import List, Optional, Dict, Any
import os
from pathlib import Path


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # API Configuration
    api_title: str = Field(default="SM Image Processing API", env="API_TITLE")
    api_version: str = Field(default="1.0.0", env="API_VERSION")
    debug: bool = Field(default=False, env="DEBUG")
    environment: str = Field(default="production", env="ENVIRONMENT")
    
    # Server Configuration
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8000, env="PORT")
    workers: int = Field(default=4, env="WORKERS")
    
    # Database Configuration
    database_url: str = Field(..., env="DATABASE_URL")
    db_pool_size: int = Field(default=10, env="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=20, env="DB_MAX_OVERFLOW")
    db_echo: bool = Field(default=False, env="DB_ECHO")
    
    # Redis Configuration
    redis_url: str = Field(..., env="REDIS_URL")
    redis_max_connections: int = Field(default=10, env="REDIS_MAX_CONNECTIONS")
    
    # Security Configuration
    jwt_secret: str = Field(..., env="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", env="JWT_ALGORITHM")
    jwt_expire_hours: int = Field(default=24, env="JWT_EXPIRE_HOURS")
    frontend_api_key: str = Field(..., env="FRONTEND_API_KEY")
    
    # Image Processing Configuration
    max_image_size_mb: int = Field(default=10, env="MAX_IMAGE_SIZE_MB")
    max_images_per_request: int = Field(default=3, env="MAX_IMAGES_PER_REQUEST")
    supported_formats: str = Field(default="jpg,jpeg,png,webp", env="SUPPORTED_FORMATS")
    
    # AI Model Configuration
    flux_model_path: str = Field(..., env="FLUX_MODEL_PATH")
    lora_model_path: str = Field(..., env="LORA_MODEL_PATH")
    gpu_memory_fraction: float = Field(default=0.9, env="GPU_MEMORY_FRACTION")
    torch_device: str = Field(default="cuda", env="TORCH_DEVICE")
    
    # File Storage Configuration
    storage_type: str = Field(default="local", env="STORAGE_TYPE")  # local, s3, minio
    storage_path: str = Field(default="/app/storage", env="STORAGE_PATH")
    storage_url_prefix: str = Field(default="https://api.yourdomain.com/files", env="STORAGE_URL_PREFIX")
    
    # S3/MinIO Configuration
    s3_bucket_name: Optional[str] = Field(default=None, env="S3_BUCKET_NAME")
    s3_access_key: Optional[str] = Field(default=None, env="S3_ACCESS_KEY")
    s3_secret_key: Optional[str] = Field(default=None, env="S3_SECRET_KEY")
    s3_endpoint_url: Optional[str] = Field(default=None, env="S3_ENDPOINT_URL")
    s3_region: str = Field(default="us-east-1", env="S3_REGION")
    
    # Celery Configuration
    celery_broker_url: str = Field(..., env="CELERY_BROKER_URL")
    celery_result_backend: str = Field(..., env="CELERY_RESULT_BACKEND")
    celery_task_serializer: str = Field(default="json", env="CELERY_TASK_SERIALIZER")
    celery_result_serializer: str = Field(default="json", env="CELERY_RESULT_SERIALIZER")
    
    # Monitoring Configuration
    enable_metrics: bool = Field(default=True, env="ENABLE_METRICS")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    sentry_dsn: Optional[str] = Field(default=None, env="SENTRY_DSN")
    
    # Rate Limiting
    rate_limit_per_minute: int = Field(default=60, env="RATE_LIMIT_PER_MINUTE")
    rate_limit_per_hour: int = Field(default=1000, env="RATE_LIMIT_PER_HOUR")
    
    # Credit System
    default_credits: int = Field(default=0, env="DEFAULT_CREDITS")
    credit_costs: Dict[str, int] = Field(default_factory=lambda: {
        "enhance_low": 1,
        "enhance_medium": 2,
        "enhance_high": 3,
        "upscale_2x": 2,
        "upscale_4x": 4
    })
    
    # External Services
    webhook_timeout: int = Field(default=30, env="WEBHOOK_TIMEOUT")
    webhook_retry_attempts: int = Field(default=3, env="WEBHOOK_RETRY_ATTEMPTS")
    
    @validator("supported_formats")
    def parse_supported_formats(cls, v):
        """Parse comma-separated formats into a list."""
        if isinstance(v, str):
            return [fmt.strip().lower() for fmt in v.split(",")]
        return v
    
    @validator("storage_path")
    def create_storage_path(cls, v):
        """Ensure storage path exists."""
        Path(v).mkdir(parents=True, exist_ok=True)
        return v
    
    @property
    def max_image_size_bytes(self) -> int:
        """Convert MB to bytes."""
        return self.max_image_size_mb * 1024 * 1024
    
    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment.lower() in ["development", "dev", "local"]
    
    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment.lower() in ["production", "prod"]
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        validate_assignment = True


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings."""
    return settings
