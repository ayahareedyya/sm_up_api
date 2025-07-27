"""
Custom Exception Classes and Error Handling

Centralized exception handling for the SM Image Processing API.
"""

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from datetime import datetime
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class APIException(Exception):
    """Base API exception class."""
    
    def __init__(
        self,
        status_code: int,
        message: str,
        details: Optional[str] = None,
        error_code: Optional[str] = None
    ):
        self.status_code = status_code
        self.message = message
        self.details = details
        self.error_code = error_code
        super().__init__(self.message)


class AuthenticationError(APIException):
    """Authentication related errors."""
    
    def __init__(self, message: str = "Authentication failed", details: Optional[str] = None):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message=message,
            details=details,
            error_code="AUTH_ERROR"
        )


class AuthorizationError(APIException):
    """Authorization related errors."""
    
    def __init__(self, message: str = "Access denied", details: Optional[str] = None):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            message=message,
            details=details,
            error_code="AUTHZ_ERROR"
        )


class InsufficientCreditsError(APIException):
    """Insufficient credits error."""
    
    def __init__(self, required: int, available: int):
        super().__init__(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            message="Insufficient credits",
            details=f"Required: {required} credits, Available: {available} credits",
            error_code="INSUFFICIENT_CREDITS"
        )


class ImageValidationError(APIException):
    """Image validation errors."""
    
    def __init__(self, message: str, details: Optional[str] = None):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Image validation failed: {message}",
            details=details,
            error_code="IMAGE_VALIDATION_ERROR"
        )


class ImageProcessingError(APIException):
    """Image processing errors."""
    
    def __init__(self, message: str, details: Optional[str] = None):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Image processing failed: {message}",
            details=details,
            error_code="PROCESSING_ERROR"
        )


class JobNotFoundError(APIException):
    """Job not found error."""
    
    def __init__(self, job_id: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Job not found",
            details=f"Job with ID '{job_id}' does not exist or you don't have access to it",
            error_code="JOB_NOT_FOUND"
        )


class RateLimitExceededError(APIException):
    """Rate limit exceeded error."""
    
    def __init__(self, limit: int, window: str):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            message="Rate limit exceeded",
            details=f"Maximum {limit} requests per {window} exceeded",
            error_code="RATE_LIMIT_EXCEEDED"
        )


class ModelLoadError(APIException):
    """AI model loading error."""
    
    def __init__(self, model_name: str, details: Optional[str] = None):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            message=f"Failed to load model: {model_name}",
            details=details,
            error_code="MODEL_LOAD_ERROR"
        )


class StorageError(APIException):
    """File storage error."""
    
    def __init__(self, message: str, details: Optional[str] = None):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Storage error: {message}",
            details=details,
            error_code="STORAGE_ERROR"
        )


def create_error_response(
    status_code: int,
    message: str,
    details: Optional[str] = None,
    error_code: Optional[str] = None,
    request_id: Optional[str] = None
) -> Dict[str, Any]:
    """Create standardized error response."""
    
    error_response = {
        "error": {
            "code": error_code or "UNKNOWN_ERROR",
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
        }
    }
    
    if details:
        error_response["error"]["details"] = details
    
    if request_id:
        error_response["error"]["request_id"] = request_id
    
    return error_response


async def api_exception_handler(request: Request, exc: APIException) -> JSONResponse:
    """Handle custom API exceptions."""
    
    request_id = getattr(request.state, "request_id", None)
    
    logger.error(
        f"API Exception: {exc.message}",
        extra={
            "status_code": exc.status_code,
            "error_code": exc.error_code,
            "details": exc.details,
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method
        }
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=create_error_response(
            status_code=exc.status_code,
            message=exc.message,
            details=exc.details,
            error_code=exc.error_code,
            request_id=request_id
        )
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle HTTP exceptions."""
    
    request_id = getattr(request.state, "request_id", None)
    
    logger.warning(
        f"HTTP Exception: {exc.detail}",
        extra={
            "status_code": exc.status_code,
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method
        }
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=create_error_response(
            status_code=exc.status_code,
            message=exc.detail,
            error_code="HTTP_ERROR",
            request_id=request_id
        )
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle request validation errors."""
    
    request_id = getattr(request.state, "request_id", None)
    
    logger.warning(
        f"Validation Error: {exc.errors()}",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method
        }
    )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=create_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            message="Request validation failed",
            details=str(exc.errors()),
            error_code="VALIDATION_ERROR",
            request_id=request_id
        )
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions."""
    
    request_id = getattr(request.state, "request_id", None)
    
    logger.error(
        f"Unexpected error: {str(exc)}",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "exception_type": type(exc).__name__
        },
        exc_info=True
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=create_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Internal server error",
            details="An unexpected error occurred. Please try again later.",
            error_code="INTERNAL_ERROR",
            request_id=request_id
        )
    )
