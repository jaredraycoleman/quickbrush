"""
Image storage service for Quickbrush.

Manages image storage in MongoDB with a configurable image limit per user.
All images are stored as WebP format.
"""

from models import User, Generation
from datetime import datetime, timezone
from typing import Optional
import logging
from config import Config

logger = logging.getLogger(__name__)

# Maximum number of images to store per user (from config)
MAX_IMAGES_PER_USER = Config.MAX_IMAGES_PER_USER


def enforce_image_limit(user: User) -> int:
    """
    Enforce the per-user image limit by deleting oldest generations.

    Args:
        user: User object

    Returns:
        int: Number of images deleted
    """
    try:
        # Get all completed generations for this user, ordered by creation date (newest first)
        all_generations = Generation.objects( # type: ignore
            user=user,
            status="completed",
            image_data__ne=None  # Only count generations with image data
        ).order_by('-created_at')

        total_count = all_generations.count()

        if total_count <= MAX_IMAGES_PER_USER:
            return 0

        # Delete the oldest images beyond the limit
        images_to_delete = total_count - MAX_IMAGES_PER_USER
        oldest_generations = all_generations.skip(MAX_IMAGES_PER_USER)

        deleted_count = 0
        for gen in oldest_generations:
            try:
                # Clear the image data but keep the generation record for history
                gen.image_data = None
                gen.save()
                deleted_count += 1
            except Exception as e:
                logger.error(f"Failed to delete image data for generation {gen.id}: {e}")

        logger.info(f"Enforced image limit for user {user.email}: deleted {deleted_count} old images")
        return deleted_count

    except Exception as e:
        logger.error(f"Error enforcing image limit: {e}")
        return 0


def save_generation_with_image(
    user: User,
    image_data: bytes,
    generation_type: str,
    quality: str,
    user_text: str,
    user_prompt: str,
    refined_description: str,
    image_size: str,
    brushstrokes_used: int,
    aspect_ratio: Optional[str] = None,
    source: str = "web",
    api_key=None,
    image_name: Optional[str] = None
) -> Generation:
    """
    Save a generation with image data to MongoDB.
    Automatically enforces the per-user image limit.

    Args:
        user: User object
        image_data: WebP image as bytes
        generation_type: Type of generation (character, scene, etc.)
        quality: Quality level
        user_text: User's original text
        user_prompt: User's prompt
        refined_description: GPT-4o refined description
        image_size: Image size
        brushstrokes_used: Number of brushstrokes used
        aspect_ratio: Aspect ratio (square, landscape, portrait)
        source: Source of generation (web or api)
        api_key: Optional API key if from API

    Returns:
        Generation: The saved generation object
    """
    # Create generation record
    generation = Generation(
        user=user,
        generation_type=generation_type,
        quality=quality,
        aspect_ratio=aspect_ratio,
        user_text=user_text,
        user_prompt=user_prompt,
        refined_description=refined_description,
        image_size=image_size,
        image_data=image_data,
        image_format="webp",
        image_name=image_name,
        brushstrokes_used=brushstrokes_used,
        status="completed",
        source=source,
        api_key=api_key,
        completed_at=datetime.now(timezone.utc),
    )
    generation.save()

    # Enforce the per-user image limit
    enforce_image_limit(user)

    return generation


def get_user_generations(
    user: User,
    limit: Optional[int] = None,
    include_without_images: bool = False
) -> list:
    """
    Get user's generations, ordered by most recent first.

    Args:
        user: User object
        limit: Maximum number of generations to return
        include_without_images: Whether to include generations without image data

    Returns:
        list: List of Generation objects
    """
    query = Generation.objects(user=user) # type: ignore

    if not include_without_images:
        query = query.filter(image_data__ne=None)

    query = query.order_by('-created_at')

    if limit:
        query = query.limit(limit)

    return list(query)


def get_generation_by_id(generation_id: str, user: User) -> Optional[Generation]:
    """
    Get a generation by ID, ensuring it belongs to the user.

    Args:
        generation_id: Generation ID
        user: User object

    Returns:
        Generation object or None
    """
    try:
        generation = Generation.objects(id=generation_id, user=user).first() # type: ignore
        return generation
    except Exception as e:
        logger.error(f"Error getting generation {generation_id}: {e}")
        return None


def get_remaining_image_slots(user: User) -> int:
    """
    Get the number of remaining image slots for a user.

    Args:
        user: User object

    Returns:
        int: Number of remaining slots (0 to MAX_IMAGES_PER_USER)
    """
    try:
        current_count = Generation.objects( # type: ignore
            user=user,
            status="completed",
            image_data__ne=None
        ).count()

        remaining = MAX_IMAGES_PER_USER - current_count
        return max(0, remaining)

    except Exception as e:
        logger.error(f"Error getting remaining image slots: {e}")
        return MAX_IMAGES_PER_USER  # Return max on error to avoid blocking user
