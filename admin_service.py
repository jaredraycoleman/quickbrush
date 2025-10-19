"""
Admin service for user management and invitation codes.

This module provides functionality for:
- Searching and managing users
- Gifting purchased tokens
- Creating and managing invitation codes
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from models import User, InvitationCode, BrushstrokeTransaction, TransactionType


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

        # Get invitation info
        invitation_info = None
        if user.invitation_code:
            invite = InvitationCode.objects(code=user.invitation_code).first()  # type: ignore
            if invite:
                invitation_info = {
                    'code': invite.code,
                    'created_by': invite.created_by.email if invite.created_by else 'Unknown',
                    'created_at': invite.created_at,
                }

        return {
            'user': user,
            'recent_transactions': list(recent_transactions),
            'invitation_info': invitation_info,
        }
    except Exception as e:
        print(f"Error getting user details: {e}")
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
        print(f"Error gifting tokens: {e}")
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
        print(f"Error toggling admin status: {e}")
        return None


def grant_invite_access(target_user_id: str, admin_user: User) -> bool:
    """
    Manually grant invite access to a user without requiring a code.

    Args:
        target_user_id: MongoDB ID of the target user
        admin_user: Admin user performing the action

    Returns:
        True if successful, False otherwise
    """
    try:
        user = User.objects(id=target_user_id).first()  # type: ignore
        if not user:
            return False

        user.has_valid_invite = True
        user.invitation_code = f"ADMIN_GRANT_{admin_user.email}_{datetime.now(timezone.utc).isoformat()}"
        user.save()

        return True
    except Exception as e:
        print(f"Error granting invite access: {e}")
        return False


# ========================================
# INVITATION CODE MANAGEMENT
# ========================================

def create_invitation_code(admin_user: User, description: str = "", expires_at: Optional[datetime] = None) -> Optional[InvitationCode]:
    """
    Create a new invitation code.

    Args:
        admin_user: Admin user creating the code
        description: Optional description/note
        expires_at: Optional expiration date

    Returns:
        The created InvitationCode or None on error
    """
    try:
        code = InvitationCode.generate_code()

        invitation = InvitationCode(
            code=code,
            created_by=admin_user,
            description=description,
            expires_at=expires_at,
        )
        invitation.save()

        return invitation
    except Exception as e:
        print(f"Error creating invitation code: {e}")
        return None


def get_invitation_codes(include_used: bool = False, limit: int = 50) -> List[InvitationCode]:
    """
    Get invitation codes.

    Args:
        include_used: Whether to include used codes
        limit: Maximum number of results

    Returns:
        List of invitation codes
    """
    try:
        if include_used:
            codes = InvitationCode.objects().order_by('-created_at').limit(limit)  # type: ignore
        else:
            codes = InvitationCode.objects(is_used=False).order_by('-created_at').limit(limit)  # type: ignore

        return list(codes)
    except Exception as e:
        print(f"Error fetching invitation codes: {e}")
        return []


def redeem_invitation_code(code: str, user: User) -> tuple[bool, str]:
    """
    Redeem an invitation code for a user.

    Args:
        code: The invitation code
        user: User redeeming the code

    Returns:
        (success, message) tuple
    """
    try:
        invitation = InvitationCode.objects(code=code).first()  # type: ignore

        if not invitation:
            return False, "Invalid invitation code."

        if invitation.is_used:
            return False, "This invitation code has already been used."

        if invitation.expires_at and invitation.expires_at < datetime.now(timezone.utc):
            return False, "This invitation code has expired."

        # Redeem the code
        success = invitation.redeem(user)
        if success:
            return True, "Invitation code redeemed successfully! You now have full access to Quickbrush."
        else:
            return False, "Failed to redeem invitation code. Please try again."

    except Exception as e:
        print(f"Error redeeming invitation code: {e}")
        return False, "An error occurred while redeeming the code."


def delete_invitation_code(code_id: str) -> bool:
    """
    Delete an invitation code.

    Args:
        code_id: MongoDB ID of the invitation code

    Returns:
        True if successful, False otherwise
    """
    try:
        invitation = InvitationCode.objects(id=code_id).first()  # type: ignore
        if not invitation:
            return False

        invitation.delete()
        return True
    except Exception as e:
        print(f"Error deleting invitation code: {e}")
        return False


def get_user_stats() -> Dict[str, Any]:
    """
    Get statistics about users and invitations.

    Returns:
        Dictionary with various stats
    """
    try:
        total_users = User.objects().count()  # type: ignore
        users_with_invites = User.objects(has_valid_invite=True).count()  # type: ignore
        admin_users = User.objects(is_admin=True).count()  # type: ignore
        total_codes = InvitationCode.objects().count()  # type: ignore
        used_codes = InvitationCode.objects(is_used=True).count()  # type: ignore
        available_codes = total_codes - used_codes

        return {
            'total_users': total_users,
            'users_with_invites': users_with_invites,
            'users_without_invites': total_users - users_with_invites,
            'admin_users': admin_users,
            'total_codes': total_codes,
            'used_codes': used_codes,
            'available_codes': available_codes,
        }
    except Exception as e:
        print(f"Error getting user stats: {e}")
        return {
            'total_users': 0,
            'users_with_invites': 0,
            'users_without_invites': 0,
            'admin_users': 0,
            'total_codes': 0,
            'used_codes': 0,
            'available_codes': 0,
        }
