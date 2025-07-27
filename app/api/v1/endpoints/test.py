"""
Test Endpoints for Development

Temporary endpoints for testing without Paymob integration.
These endpoints should be removed in production.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import uuid
import logging

from app.core.database import get_db
from app.core.config import settings
from app.models.database import User, CreditTransaction
from app.api.v1.dependencies import auth_service, verify_api_key
from app.services.credit_service import CreditService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/test", tags=["testing"])


@router.post("/create-user")
async def create_test_user(
    email: str,
    credits: int = 100,
    api_key_valid: bool = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    Create a test user with initial credits.
    
    Args:
        email: User email
        credits: Initial credits (default: 100)
        
    Returns:
        dict: User info and JWT token
    """
    try:
        # Check if user already exists
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            raise HTTPException(400, f"User with email {email} already exists")
        
        # Create new user
        user = User(
            id=uuid.uuid4(),
            email=email,
            username=email.split('@')[0],
            full_name=f"Test User {email.split('@')[0]}",
            credits_balance=credits,
            total_credits_purchased=credits,
            is_active=True,
            is_verified=True
        )
        
        db.add(user)
        db.commit()
        db.refresh(user)
        
        # Create initial credit transaction
        transaction = CreditTransaction(
            id=uuid.uuid4(),
            user_id=user.id,
            amount=credits,
            transaction_type="bonus",
            description="Initial test credits",
            balance_before=0,
            balance_after=credits
        )
        
        db.add(transaction)
        db.commit()
        
        # Generate JWT token
        token = auth_service.create_access_token(
            user_id=str(user.id),
            expires_delta=timedelta(days=30)  # Long expiry for testing
        )
        
        logger.info(f"Created test user: {email} with {credits} credits")
        
        return {
            "message": "Test user created successfully",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "credits_balance": user.credits_balance
            },
            "access_token": token,
            "token_type": "bearer",
            "expires_in": 30 * 24 * 3600  # 30 days
        }
        
    except Exception as e:
        logger.error(f"Error creating test user: {str(e)}")
        db.rollback()
        raise HTTPException(500, f"Failed to create test user: {str(e)}")


@router.post("/add-credits")
async def add_test_credits(
    user_email: str,
    amount: int,
    api_key_valid: bool = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    Add credits to a test user.
    
    Args:
        user_email: User email
        amount: Credits to add
        
    Returns:
        dict: Updated user info
    """
    try:
        # Find user
        user = db.query(User).filter(User.email == user_email).first()
        if not user:
            raise HTTPException(404, f"User with email {user_email} not found")
        
        # Add credits using credit service
        credit_service = CreditService(db)
        success = credit_service.add_credits(
            user_id=str(user.id),
            amount=amount,
            payment_method="test"
        )
        
        if not success:
            raise HTTPException(500, "Failed to add credits")
        
        # Get updated user
        db.refresh(user)
        
        logger.info(f"Added {amount} credits to user: {user_email}")
        
        return {
            "message": f"Added {amount} credits successfully",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "credits_balance": user.credits_balance,
                "total_credits_purchased": user.total_credits_purchased
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding credits: {str(e)}")
        raise HTTPException(500, f"Failed to add credits: {str(e)}")


@router.get("/users")
async def list_test_users(
    api_key_valid: bool = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    List all test users.
    
    Returns:
        list: List of users
    """
    try:
        users = db.query(User).all()
        
        return {
            "users": [
                {
                    "id": str(user.id),
                    "email": user.email,
                    "credits_balance": user.credits_balance,
                    "total_credits_used": user.total_credits_used,
                    "is_active": user.is_active,
                    "created_at": user.created_at.isoformat()
                }
                for user in users
            ]
        }
        
    except Exception as e:
        logger.error(f"Error listing users: {str(e)}")
        raise HTTPException(500, f"Failed to list users: {str(e)}")


@router.delete("/user/{user_email}")
async def delete_test_user(
    user_email: str,
    api_key_valid: bool = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    Delete a test user.
    
    Args:
        user_email: User email to delete
        
    Returns:
        dict: Deletion confirmation
    """
    try:
        # Find user
        user = db.query(User).filter(User.email == user_email).first()
        if not user:
            raise HTTPException(404, f"User with email {user_email} not found")
        
        # Delete user (cascade will delete related records)
        db.delete(user)
        db.commit()
        
        logger.info(f"Deleted test user: {user_email}")
        
        return {
            "message": f"User {user_email} deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user: {str(e)}")
        db.rollback()
        raise HTTPException(500, f"Failed to delete user: {str(e)}")


@router.post("/reset-database")
async def reset_test_database(
    confirm: bool = False,
    api_key_valid: bool = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    Reset test database (delete all users and transactions).
    
    Args:
        confirm: Must be True to confirm deletion
        
    Returns:
        dict: Reset confirmation
    """
    if not confirm:
        raise HTTPException(400, "Must set confirm=True to reset database")
    
    try:
        # Delete all users (cascade will delete related records)
        deleted_users = db.query(User).delete()
        db.commit()
        
        logger.warning(f"Reset test database: deleted {deleted_users} users")
        
        return {
            "message": f"Database reset successfully. Deleted {deleted_users} users.",
            "warning": "All test data has been removed."
        }
        
    except Exception as e:
        logger.error(f"Error resetting database: {str(e)}")
        db.rollback()
        raise HTTPException(500, f"Failed to reset database: {str(e)}")


@router.get("/info")
async def test_info():
    """
    Get test environment information.
    
    Returns:
        dict: Test environment info
    """
    return {
        "message": "SM Image Processing API - Test Environment",
        "environment": settings.environment,
        "debug": settings.debug,
        "features": {
            "test_user_creation": True,
            "free_credits": True,
            "no_payment_required": True
        },
        "endpoints": {
            "create_user": "POST /api/v1/test/create-user",
            "add_credits": "POST /api/v1/test/add-credits",
            "list_users": "GET /api/v1/test/users",
            "delete_user": "DELETE /api/v1/test/user/{email}",
            "reset_db": "POST /api/v1/test/reset-database"
        },
        "note": "These endpoints are for testing only and should be removed in production"
    }
