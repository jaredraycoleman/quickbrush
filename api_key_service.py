"""
API key management service.

This module provides CRUD operations for API keys and authentication.
"""

from models import APIKey, User
from typing import Optional, List, Tuple
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)


def create_api_key(user: User, name: str, expires_in_days: Optional[int] = None) -> Tuple[APIKey, str]:
    """
    Create a new API key for a user.

    Args:
        user: User object
        name: User-provided name for the key
        expires_in_days: Optional number of days until expiration

    Returns:
        (APIKey object, secret_key) - The secret is only returned once and must be shown to user
    """
    # Generate key pair
    key_id, secret = APIKey.generate_key()

    # Hash the secret for storage
    key_hash = APIKey.hash_key(secret)

    # Calculate expiration if specified
    expires_at = None
    if expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

    # Create API key
    api_key = APIKey(
        user=user,
        key_id=key_id,
        key_hash=key_hash,
        key_prefix=key_id[:8],  # Store first 8 chars of key_id for user identification
        name=name,
        expires_at=expires_at,
    )
    api_key.save()

    logger.info(f"Created API key for user {user.email}: {key_id}")

    # Return the API key object and the secret (only time it's available)
    return api_key, secret


def get_user_api_keys(user: User, include_inactive: bool = False) -> List[APIKey]:
    """
    Get all API keys for a user.

    Args:
        user: User object
        include_inactive: Whether to include inactive/expired keys

    Returns:
        List of APIKey objects
    """
    if include_inactive:
        keys = APIKey.objects(user=user).order_by('-created_at') # type: ignore
    else:
        keys = APIKey.objects(user=user, is_active=True).order_by('-created_at') # type: ignore

    return list(keys)


def revoke_api_key(api_key: APIKey) -> bool:
    """
    Revoke an API key (mark as inactive).

    Args:
        api_key: APIKey object to revoke

    Returns:
        True if successful
    """
    try:
        api_key.is_active = False
        api_key.save()
        logger.info(f"Revoked API key: {api_key.key_id}")
        return True
    except Exception as e:
        logger.error(f"Error revoking API key: {e}")
        return False


def delete_api_key(api_key: APIKey) -> bool:
    """
    Permanently delete an API key.

    Args:
        api_key: APIKey object to delete

    Returns:
        True if successful
    """
    try:
        key_id = api_key.key_id
        api_key.delete()
        logger.info(f"Deleted API key: {key_id}")
        return True
    except Exception as e:
        logger.error(f"Error deleting API key: {e}")
        return False


def authenticate_api_key(authorization: str) -> Optional[User]:
    """
    Authenticate an API key from Authorization header.

    Expected format: "Bearer qb_xxxxx:secret"

    Args:
        authorization: Authorization header value

    Returns:
        User object if authenticated, None otherwise
    """
    if not authorization:
        return None

    # Parse Bearer token
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        logger.warning("Invalid authorization header format")
        return None

    token = parts[1]

    # Parse key_id and secret
    if ':' not in token:
        logger.warning("Invalid API key format (missing colon)")
        return None

    key_id, secret = token.split(':', 1)

    # Verify key
    from models import verify_api_key
    api_key = verify_api_key(key_id, secret)
    if not api_key:
        logger.warning(f"Invalid API key: {key_id}")
        return None

    # Record usage
    api_key.record_usage()
    api_key.save()

    return api_key.user # type: ignore
