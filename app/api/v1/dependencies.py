"""
API Dependencies

Authentication and authorization dependencies for FastAPI endpoints.
"""

from fastapi import Depends, HTTPException, Header, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import jwt
from datetime import datetime, timedelta
import hashlib
import logging

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.models.database import User, APIKey

logger = logging.getLogger(__name__)
security = HTTPBearer()


class AuthService:
    """Authentication service for handling JWT and API key validation."""
    
    def __init__(self):
        self.secret_key = settings.jwt_secret
        self.algorithm = settings.jwt_algorithm
        self.frontend_api_key = settings.frontend_api_key
    
    def create_access_token(self, user_id: str, expires_delta: timedelta = None) -> str:
        """Create JWT access token for user."""
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(hours=settings.jwt_expire_hours)
        
        to_encode = {
            "user_id": user_id,
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "access"
        }
        
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt
    
    def verify_token(self, token: str) -> str:
        """Verify JWT token and return user_id."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            user_id = payload.get("user_id")
            
            if user_id is None:
                raise AuthenticationError("Invalid token: missing user_id")
            
            # Check token type
            if payload.get("type") != "access":
                raise AuthenticationError("Invalid token type")
            
            return user_id
            
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Token has expired")
        except jwt.JWTError as e:
            raise AuthenticationError(f"Invalid token: {str(e)}")
    
    def verify_api_key(self, api_key: str) -> bool:
        """Verify API key for frontend access."""
        return api_key == self.frontend_api_key
    
    def hash_api_key(self, api_key: str) -> str:
        """Hash API key for storage."""
        return hashlib.sha256(api_key.encode()).hexdigest()


# Global auth service instance
auth_service = AuthService()


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> bool:
    """
    Verify API key from header.
    
    Args:
        x_api_key: API key from X-API-Key header
        
    Returns:
        bool: True if API key is valid
        
    Raises:
        AuthenticationError: If API key is invalid
    """
    if not auth_service.verify_api_key(x_api_key):
        logger.warning(f"Invalid API key attempt: {x_api_key[:10]}...")
        raise AuthenticationError("Invalid API key")
    
    return True


async def verify_jwt_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """
    Verify JWT token from Authorization header.
    
    Args:
        credentials: JWT credentials from Authorization header
        
    Returns:
        str: User ID from token
        
    Raises:
        AuthenticationError: If token is invalid
    """
    try:
        user_id = auth_service.verify_token(credentials.credentials)
        return user_id
    except AuthenticationError:
        raise
    except Exception as e:
        logger.error(f"Token verification error: {str(e)}")
        raise AuthenticationError("Token verification failed")


async def get_current_user(
    user_id: str = Depends(verify_jwt_token),
    db: Session = Depends(get_db)
) -> User:
    """
    Get current user from database.
    
    Args:
        user_id: User ID from JWT token
        db: Database session
        
    Returns:
        User: Current user object
        
    Raises:
        AuthenticationError: If user not found or inactive
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise AuthenticationError("User not found")
    
    if not user.is_active:
        raise AuthenticationError("User account is inactive")
    
    # Update last login
    user.last_login = datetime.utcnow()
    db.commit()
    
    return user


async def get_authenticated_user(
    api_key_valid: bool = Depends(verify_api_key),
    user: User = Depends(get_current_user)
) -> User:
    """
    Combined authentication: API key + JWT token.
    
    Args:
        api_key_valid: API key validation result
        user: Current user from JWT token
        
    Returns:
        User: Authenticated user
    """
    return user


async def check_user_credits(
    user: User = Depends(get_authenticated_user),
    required_credits: int = 1
) -> User:
    """
    Check if user has sufficient credits.
    
    Args:
        user: Current user
        required_credits: Minimum credits required
        
    Returns:
        User: User with sufficient credits
        
    Raises:
        AuthorizationError: If insufficient credits
    """
    if user.credits_balance < required_credits:
        raise AuthorizationError(
            f"Insufficient credits. Required: {required_credits}, Available: {user.credits_balance}"
        )
    
    return user


class RateLimiter:
    """Rate limiting functionality."""
    
    def __init__(self, redis_client=None):
        self.redis_client = redis_client
    
    async def check_rate_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int
    ) -> bool:
        """
        Check if request is within rate limit.
        
        Args:
            key: Rate limit key (e.g., user_id, api_key)
            limit: Maximum requests allowed
            window_seconds: Time window in seconds
            
        Returns:
            bool: True if within limit, False otherwise
        """
        if not self.redis_client:
            return True  # No rate limiting if Redis not available
        
        try:
            current_time = datetime.utcnow().timestamp()
            window_start = current_time - window_seconds
            
            # Remove old entries
            self.redis_client.zremrangebyscore(key, 0, window_start)
            
            # Count current requests
            current_count = self.redis_client.zcard(key)
            
            if current_count >= limit:
                return False
            
            # Add current request
            self.redis_client.zadd(key, {str(current_time): current_time})
            self.redis_client.expire(key, window_seconds)
            
            return True
            
        except Exception as e:
            logger.error(f"Rate limiting error: {str(e)}")
            return True  # Allow request if rate limiting fails


# Rate limiter instance (will be initialized with Redis client)
rate_limiter = RateLimiter()


async def rate_limit_check(
    user: User = Depends(get_authenticated_user)
) -> User:
    """
    Rate limiting dependency.
    
    Args:
        user: Current user
        
    Returns:
        User: User if within rate limits
        
    Raises:
        AuthorizationError: If rate limit exceeded
    """
    # Check per-minute rate limit
    if not await rate_limiter.check_rate_limit(
        f"rate_limit:user:{user.id}:minute",
        settings.rate_limit_per_minute,
        60
    ):
        raise AuthorizationError(
            f"Rate limit exceeded: {settings.rate_limit_per_minute} requests per minute"
        )
    
    # Check per-hour rate limit
    if not await rate_limiter.check_rate_limit(
        f"rate_limit:user:{user.id}:hour",
        settings.rate_limit_per_hour,
        3600
    ):
        raise AuthorizationError(
            f"Rate limit exceeded: {settings.rate_limit_per_hour} requests per hour"
        )
    
    return user
