"""
Authentication Endpoints

User authentication and token management endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import logging

from app.core.database import get_db
from app.api.v1.dependencies import get_authenticated_user, auth_service
from app.models.database import User
from app.models.schemas import UserCreditsResponse
from app.core.exceptions import AuthenticationError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/verify-token")
async def verify_token(user: User = Depends(get_authenticated_user)):
    """
    Verify JWT token validity.
    
    Args:
        user: Authenticated user from token
        
    Returns:
        dict: Token verification result
    """
    return {
        "valid": True,
        "user_id": str(user.id),
        "email": user.email,
        "credits_balance": user.credits_balance,
        "is_active": user.is_active,
        "verified_at": datetime.utcnow().isoformat()
    }


@router.post("/refresh-token")
async def refresh_token(user: User = Depends(get_authenticated_user)):
    """
    Refresh JWT token.
    
    Args:
        user: Authenticated user
        
    Returns:
        dict: New access token
    """
    try:
        # Create new token with extended expiry
        new_token = auth_service.create_access_token(
            user_id=str(user.id),
            expires_delta=timedelta(hours=24)
        )
        
        logger.info(f"Token refreshed for user: {user.id}")
        
        return {
            "access_token": new_token,
            "token_type": "bearer",
            "expires_in": 24 * 3600,  # 24 hours in seconds
            "user_id": str(user.id),
            "refreshed_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Token refresh failed for user {user.id}: {str(e)}")
        raise AuthenticationError("Failed to refresh token")


@router.get("/user-credits", response_model=UserCreditsResponse)
async def get_user_credits(user: User = Depends(get_authenticated_user)):
    """
    Get user's credit information.
    
    Args:
        user: Authenticated user
        
    Returns:
        UserCreditsResponse: User's credit information
    """
    return UserCreditsResponse(
        user_id=str(user.id),
        credits_balance=user.credits_balance,
        total_credits_purchased=user.total_credits_purchased,
        total_credits_used=user.total_credits_used
    )


@router.get("/user-profile")
async def get_user_profile(user: User = Depends(get_authenticated_user)):
    """
    Get user's profile information.
    
    Args:
        user: Authenticated user
        
    Returns:
        dict: User profile information
    """
    return {
        "user_id": str(user.id),
        "email": user.email,
        "username": user.username,
        "full_name": user.full_name,
        "credits_balance": user.credits_balance,
        "total_credits_purchased": user.total_credits_purchased,
        "total_credits_used": user.total_credits_used,
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "created_at": user.created_at.isoformat(),
        "last_login": user.last_login.isoformat() if user.last_login else None
    }


@router.post("/logout")
async def logout(user: User = Depends(get_authenticated_user)):
    """
    Logout user (client-side token invalidation).
    
    Args:
        user: Authenticated user
        
    Returns:
        dict: Logout confirmation
    """
    logger.info(f"User logged out: {user.id}")
    
    return {
        "message": "Successfully logged out",
        "user_id": str(user.id),
        "logged_out_at": datetime.utcnow().isoformat()
    }
