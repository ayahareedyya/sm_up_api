"""
Credit Service

Service for managing user credits, transactions, and billing.
"""

from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from datetime import datetime
import logging
import uuid

from app.models.database import User, CreditTransaction
from app.core.config import settings
from app.core.exceptions import InsufficientCreditsError

logger = logging.getLogger(__name__)


class CreditService:
    """Service for managing user credits and transactions."""
    
    def __init__(self, db: Session):
        self.db = db
        self.credit_costs = settings.credit_costs
    
    def calculate_cost(self, operation: str, parameters: Dict[str, Any], image_count: int) -> int:
        """
        Calculate the cost of an image processing operation.
        
        Args:
            operation: Processing operation (enhance, upscale)
            parameters: Processing parameters
            image_count: Number of images to process
            
        Returns:
            int: Total cost in credits
        """
        try:
            base_cost = 1  # Default cost
            
            if operation == "enhance":
                quality = parameters.get("quality", "medium")
                base_cost = self.credit_costs.get(f"enhance_{quality}", 2)
            
            elif operation == "upscale":
                upscale_factor = parameters.get("upscale_factor", 2)
                base_cost = self.credit_costs.get(f"upscale_{upscale_factor}x", 2)
            
            # Apply multipliers for advanced parameters
            if parameters.get("steps", 20) > 50:
                base_cost = int(base_cost * 1.5)  # 50% more for high step count
            
            if parameters.get("guidance_scale", 7.5) > 15:
                base_cost = int(base_cost * 1.2)  # 20% more for high guidance
            
            total_cost = base_cost * image_count
            
            logger.info(f"Cost calculated: {operation} x{image_count} = {total_cost} credits")
            return total_cost
            
        except Exception as e:
            logger.error(f"Error calculating cost: {str(e)}")
            return 2 * image_count  # Fallback cost
    
    def check_user_credits(self, user_id: str, required_credits: int) -> bool:
        """
        Check if user has sufficient credits.
        
        Args:
            user_id: User identifier
            required_credits: Required credits amount
            
        Returns:
            bool: True if user has sufficient credits
        """
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                return False
            
            return user.credits_balance >= required_credits
            
        except Exception as e:
            logger.error(f"Error checking user credits: {str(e)}")
            return False
    
    def check_and_reserve_credits(self, user_id: str, required_credits: int) -> bool:
        """
        Check and reserve credits for a processing job.
        
        Args:
            user_id: User identifier
            required_credits: Required credits amount
            
        Returns:
            bool: True if credits were successfully reserved
        """
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.warning(f"User not found: {user_id}")
                return False
            
            if user.credits_balance < required_credits:
                logger.warning(f"Insufficient credits for user {user_id}: {user.credits_balance} < {required_credits}")
                return False
            
            # Reserve credits by deducting from balance
            balance_before = user.credits_balance
            user.credits_balance -= required_credits
            user.total_credits_used += required_credits
            user.updated_at = datetime.utcnow()
            
            # Create transaction record
            transaction = CreditTransaction(
                id=uuid.uuid4(),
                user_id=user.id,
                amount=-required_credits,
                transaction_type="usage",
                description=f"Credits reserved for image processing",
                balance_before=balance_before,
                balance_after=user.credits_balance
            )
            
            self.db.add(transaction)
            self.db.commit()
            
            logger.info(f"Reserved {required_credits} credits for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error reserving credits: {str(e)}")
            self.db.rollback()
            return False
    
    def refund_credits(self, user_id: str, amount: int, reason: str) -> bool:
        """
        Refund credits to user.
        
        Args:
            user_id: User identifier
            amount: Amount to refund
            reason: Reason for refund
            
        Returns:
            bool: True if refund was successful
        """
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.warning(f"User not found for refund: {user_id}")
                return False
            
            balance_before = user.credits_balance
            user.credits_balance += amount
            user.total_credits_used -= amount
            user.updated_at = datetime.utcnow()
            
            # Create refund transaction
            transaction = CreditTransaction(
                id=uuid.uuid4(),
                user_id=user.id,
                amount=amount,
                transaction_type="refund",
                description=reason,
                balance_before=balance_before,
                balance_after=user.credits_balance
            )
            
            self.db.add(transaction)
            self.db.commit()
            
            logger.info(f"Refunded {amount} credits to user {user_id}: {reason}")
            return True
            
        except Exception as e:
            logger.error(f"Error refunding credits: {str(e)}")
            self.db.rollback()
            return False
    
    def add_credits(self, user_id: str, amount: int, payment_id: str = None, payment_method: str = None) -> bool:
        """
        Add credits to user account (for purchases).
        
        Args:
            user_id: User identifier
            amount: Credits to add
            payment_id: Payment transaction ID
            payment_method: Payment method used
            
        Returns:
            bool: True if credits were added successfully
        """
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.warning(f"User not found for credit addition: {user_id}")
                return False
            
            balance_before = user.credits_balance
            user.credits_balance += amount
            user.total_credits_purchased += amount
            user.updated_at = datetime.utcnow()
            
            # Create purchase transaction
            transaction = CreditTransaction(
                id=uuid.uuid4(),
                user_id=user.id,
                amount=amount,
                transaction_type="purchase",
                description=f"Credits purchased via {payment_method or 'unknown'}",
                payment_id=payment_id,
                payment_method=payment_method,
                payment_status="completed",
                balance_before=balance_before,
                balance_after=user.credits_balance
            )
            
            self.db.add(transaction)
            self.db.commit()
            
            logger.info(f"Added {amount} credits to user {user_id} via {payment_method}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding credits: {str(e)}")
            self.db.rollback()
            return False
    
    def get_user_credits(self, user_id: str) -> Optional[int]:
        """
        Get user's current credit balance.
        
        Args:
            user_id: User identifier
            
        Returns:
            Optional[int]: User's credit balance or None if user not found
        """
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            return user.credits_balance if user else None
            
        except Exception as e:
            logger.error(f"Error getting user credits: {str(e)}")
            return None
    
    def get_user_transactions(self, user_id: str, limit: int = 50, offset: int = 0) -> list:
        """
        Get user's credit transaction history.
        
        Args:
            user_id: User identifier
            limit: Maximum number of transactions to return
            offset: Number of transactions to skip
            
        Returns:
            list: List of credit transactions
        """
        try:
            transactions = self.db.query(CreditTransaction).filter(
                CreditTransaction.user_id == user_id
            ).order_by(
                CreditTransaction.created_at.desc()
            ).offset(offset).limit(limit).all()
            
            return transactions
            
        except Exception as e:
            logger.error(f"Error getting user transactions: {str(e)}")
            return []
