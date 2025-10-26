"""
Admin service for user management.

This module provides functionality for:
- Searching and managing users
- Gifting purchased tokens
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from models import User, BrushstrokeTransaction, TransactionType

logger = logging.getLogger(__name__)


# ========================================
# USER MANAGEMENT
# ========================================

def search_users(query: str, limit: int = 20) -> List[User]:
    """
    Search for users by email, name, or Auth0 ID.

    Args:
        query: Search query string
        limit: Maximum number of results

    Returns:
        List of matching users
    """
    if not query:
        # Return recent users if no query
        return list(User.objects().order_by('-created_at').limit(limit))  # type: ignore

    # Search in email, name, and auth0_sub
    users = User.objects(  # type: ignore
        __raw__={
            "$or": [
                {"email": {"$regex": query, "$options": "i"}},
                {"name": {"$regex": query, "$options": "i"}},
                {"auth0_sub": {"$regex": query, "$options": "i"}},
            ]
        }
    ).limit(limit)

    return list(users)


def get_user_details(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Get detailed information about a user.

    Args:
        user_id: MongoDB user ID

    Returns:
        Dictionary with user details or None if not found
    """
    try:
        user = User.objects(id=user_id).first()  # type: ignore
        if not user:
            return None

        # Get recent transactions
        recent_transactions = BrushstrokeTransaction.objects(  # type: ignore
            user=user
        ).order_by('-created_at').limit(10)

        return {
            'user': user,
            'recent_transactions': list(recent_transactions),
        }
    except Exception as e:
        logger.error(f"Error getting user details: {e}")
        return None


def gift_tokens(admin_user: User, target_user_id: str, amount: int, description: str = "") -> bool:
    """
    Gift purchased tokens (brushstrokes) to a user.

    Args:
        admin_user: Admin user performing the action
        target_user_id: MongoDB ID of the target user
        amount: Number of brushstrokes to gift
        description: Optional description for the transaction

    Returns:
        True if successful, False otherwise
    """
    try:
        user = User.objects(id=target_user_id).first()  # type: ignore
        if not user:
            return False

        # Add tokens
        user.add_purchased_brushstrokes(amount)
        user.save()

        # Record transaction
        transaction = BrushstrokeTransaction(
            user=user,
            transaction_type=TransactionType.ADMIN_GRANT.value,
            amount=amount,
            balance_after=user.purchased_brushstrokes,
            description=description or f"Admin gift from {admin_user.email}",
            metadata={
                'admin_user_id': str(admin_user.id),
                'admin_email': admin_user.email,
            }
        )
        transaction.save()

        return True
    except Exception as e:
        logger.error(f"Error gifting tokens: {e}")
        return False


def toggle_admin_status(target_user_id: str) -> Optional[bool]:
    """
    Toggle admin status for a user.

    Args:
        target_user_id: MongoDB ID of the target user

    Returns:
        New admin status (True/False) or None if user not found
    """
    try:
        user = User.objects(id=target_user_id).first()  # type: ignore
        if not user:
            return None

        user.is_admin = not user.is_admin
        user.save()

        return user.is_admin
    except Exception as e:
        logger.error(f"Error toggling admin status: {e}")
        return None


def remove_tokens(admin_user: User, target_user_id: str, amount: int, description: str = "") -> bool:
    """
    Remove purchased tokens (brushstrokes) from a user.

    Args:
        admin_user: Admin user performing the action
        target_user_id: MongoDB ID of the target user
        amount: Number of brushstrokes to remove (positive number)
        description: Optional description for the transaction

    Returns:
        True if successful, False otherwise
    """
    try:
        user = User.objects(id=target_user_id).first()  # type: ignore
        if not user:
            return False

        # Ensure we don't go negative
        amount_to_remove = min(amount, user.purchased_brushstrokes)

        # Remove tokens
        user.purchased_brushstrokes -= amount_to_remove
        user.save()

        # Record transaction as negative amount
        transaction = BrushstrokeTransaction(
            user=user,
            transaction_type=TransactionType.ADMIN_GRANT.value,
            amount=-amount_to_remove,  # Negative for removal
            balance_after=user.purchased_brushstrokes,
            description=description or f"Admin removal by {admin_user.email}",
            metadata={
                'admin_user_id': str(admin_user.id),
                'admin_email': admin_user.email,
            }
        )
        transaction.save()

        return True
    except Exception as e:
        logger.error(f"Error removing tokens: {e}")
        return False


def delete_user_account(admin_user: User, target_user_id: str) -> bool:
    """
    Delete a user account (admin version).

    Args:
        admin_user: Admin user performing the action
        target_user_id: MongoDB ID of the target user

    Returns:
        True if successful, False otherwise
    """
    try:
        from account_service import delete_user_account as delete_account_service

        user = User.objects(id=target_user_id).first()  # type: ignore
        if not user:
            return False

        # Prevent deleting admin accounts
        if user.is_admin:
            logger.warning(f"Cannot delete admin account: {user.email}")
            return False

        # Use the existing account service to delete
        success = delete_account_service(user)

        if success:
            logger.info(f"Admin {admin_user.email} deleted user account: {user.email}")

        return success
    except Exception as e:
        logger.error(f"Error deleting user account: {e}")
        return False


def get_user_stats() -> Dict[str, Any]:
    """
    Get statistics about users.

    Returns:
        Dictionary with various stats
    """
    try:
        total_users = User.objects().count()  # type: ignore
        admin_users = User.objects(is_admin=True).count()  # type: ignore

        return {
            'total_users': total_users,
            'admin_users': admin_users,
        }
    except Exception as e:
        logger.error(f"Error getting user stats: {e}")
        return {
            'total_users': 0,
            'admin_users': 0,
        }


# ========================================
# SETTINGS MANAGEMENT
# ========================================

def get_app_settings() -> Dict[str, Any]:
    """
    Get current application settings.

    Returns:
        Dictionary with app settings
    """
    try:
        from models import AppSettings

        settings = AppSettings.get_settings()
        return {
            'updated_at': settings.updated_at,
            'updated_by': settings.updated_by.email if settings.updated_by else None,
        }
    except Exception as e:
        logger.error(f"Error getting app settings: {e}")
        return {
            'updated_at': None,
            'updated_by': None,
        }
