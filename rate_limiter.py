"""
Rate limiting service for Quickbrush.

Uses MongoDB to track generation attempts and enforce configurable limits.
"""

from datetime import datetime, timezone, timedelta
from typing import Tuple
from models import User, RateLimit
from config import Config
import logging

logger = logging.getLogger(__name__)


class RateLimitResult:
    """Result of a rate limit check."""
    def __init__(
        self,
        allowed: bool,
        limit_type: str = "",
        retry_after: int = 0,
        requests_remaining: int = 0,
        reset_time: datetime | None = None
    ):
        self.allowed = allowed
        self.limit_type = limit_type  # "seconds" or "hourly"
        self.retry_after = retry_after  # Seconds until they can try again
        self.requests_remaining = requests_remaining
        self.reset_time = reset_time


def check_rate_limit(user: User, action: str = "generate_image", source: str = "web") -> RateLimitResult:
    """
    Check if user has exceeded rate limits.

    Args:
        user: User object
        action: Action being performed (default: "generate_image")
        source: Source of request ("web" or "api")

    Returns:
        RateLimitResult: Object containing whether request is allowed and limit details
    """
    try:
        limits = Config.get_rate_limits()
        now = datetime.now(timezone.utc)

        # Check short-term limit (e.g., 1 per 10 seconds)
        seconds_window_start = now - timedelta(seconds=limits['seconds_window'])
        recent_attempts = RateLimit.objects( # type: ignore
            user=user,
            action=action,
            timestamp__gte=seconds_window_start
        ).count()

        if recent_attempts >= limits['seconds_limit']:
            # Calculate when they can try again
            oldest_in_window = RateLimit.objects( # type: ignore
                user=user,
                action=action,
                timestamp__gte=seconds_window_start
            ).order_by('timestamp').first()

            if oldest_in_window:
                retry_after = int((oldest_in_window.timestamp + timedelta(seconds=limits['seconds_window']) - now).total_seconds()) # type: ignore
                return RateLimitResult(
                    allowed=False,
                    limit_type="seconds",
                    retry_after=max(1, retry_after),  # At least 1 second
                    requests_remaining=0,
                    reset_time=oldest_in_window.timestamp + timedelta(seconds=limits['seconds_window']) # type: ignore
                )

        # Check hourly limit (e.g., 50 per hour)
        hour_window_start = now - timedelta(hours=1)
        hourly_attempts = RateLimit.objects( # type: ignore
            user=user,
            action=action,
            timestamp__gte=hour_window_start
        ).count()

        if hourly_attempts >= limits['hourly_limit']:
            # Calculate when they can try again
            oldest_in_hour = RateLimit.objects( # type: ignore
                user=user,
                action=action,
                timestamp__gte=hour_window_start
            ).order_by('timestamp').first()

            if oldest_in_hour:
                retry_after = int((oldest_in_hour.timestamp + timedelta(hours=1) - now).total_seconds()) # type: ignore
                return RateLimitResult(
                    allowed=False,
                    limit_type="hourly",
                    retry_after=max(1, retry_after),
                    requests_remaining=0,
                    reset_time=oldest_in_hour.timestamp + timedelta(hours=1) # type: ignore
                )

        # Request is allowed
        requests_remaining = limits['hourly_limit'] - hourly_attempts
        return RateLimitResult(
            allowed=True,
            requests_remaining=requests_remaining,
            reset_time=hour_window_start + timedelta(hours=1)
        )

    except Exception as e:
        logger.error(f"Error checking rate limit: {e}")
        # On error, allow the request (fail open)
        return RateLimitResult(allowed=True)


def record_attempt(user: User, action: str = "generate_image", source: str = "web", generation_type: str | None = None) -> None:
    """
    Record a generation attempt for rate limiting.

    Args:
        user: User object
        action: Action being performed (default: "generate_image")
        source: Source of request ("web" or "api")
        generation_type: Optional type of generation (character, scene, etc.)
    """
    try:
        rate_limit = RateLimit(
            user=user,
            action=action,
            timestamp=datetime.now(timezone.utc),
            source=source,
            generation_type=generation_type
        )
        rate_limit.save()
        logger.debug(f"Recorded rate limit attempt for user {user.email}, action {action}")
    except Exception as e:
        logger.error(f"Error recording rate limit attempt: {e}")
        # Don't fail the request if we can't record the attempt


def get_rate_limit_status(user: User, action: str = "generate_image") -> dict:
    """
    Get current rate limit status for a user.

    Args:
        user: User object
        action: Action to check (default: "generate_image")

    Returns:
        dict: Rate limit status with limits and usage info
    """
    try:
        limits = Config.get_rate_limits()
        now = datetime.now(timezone.utc)

        # Count recent attempts
        hour_window_start = now - timedelta(hours=1)
        hourly_attempts = RateLimit.objects( # type: ignore
            user=user,
            action=action,
            timestamp__gte=hour_window_start
        ).count()

        seconds_window_start = now - timedelta(seconds=limits['seconds_window'])
        recent_attempts = RateLimit.objects( # type: ignore
            user=user,
            action=action,
            timestamp__gte=seconds_window_start
        ).count()

        return {
            "limits": {
                "seconds_limit": limits['seconds_limit'],
                "seconds_window": limits['seconds_window'],
                "hourly_limit": limits['hourly_limit']
            },
            "usage": {
                "recent_attempts": recent_attempts,
                "hourly_attempts": hourly_attempts,
                "hourly_remaining": max(0, limits['hourly_limit'] - hourly_attempts)
            },
            "reset_time": (hour_window_start + timedelta(hours=1)).isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting rate limit status: {e}")
        return {
            "limits": Config.get_rate_limits(),
            "usage": {"recent_attempts": 0, "hourly_attempts": 0, "hourly_remaining": 50},
            "reset_time": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        }
