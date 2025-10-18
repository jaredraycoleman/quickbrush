"""
Image generation service for Quickbrush.

Shared service for both web and API image generation to eliminate code duplication.
"""

from models import User, ImageQuality, QUALITY_COSTS, AspectRatio, ASPECT_RATIO_SIZES, ImageGenerationType
from maker import (
    CharacterImageGenerator,
    ImageGenerator,
    SceneImageGenerator,
    CreatureImageGenerator,
    ItemImageGenerator
)
from image_service import save_generation_with_image, get_remaining_image_slots
from stripe_utils import get_subscription_info, record_generation
from typing import Optional, Tuple, List
import pathlib
import logging

logger = logging.getLogger(__name__)


class GenerationResult:
    """Result of an image generation request."""
    def __init__(
        self,
        success: bool,
        generation_id: Optional[str] = None,
        refined_description: Optional[str] = None,
        brushstrokes_used: int = 0,
        brushstrokes_remaining: int = 0,
        remaining_image_slots: int = 0,
        error_message: Optional[str] = None
    ):
        self.success = success
        self.generation_id = generation_id
        self.refined_description = refined_description
        self.brushstrokes_used = brushstrokes_used
        self.brushstrokes_remaining = brushstrokes_remaining
        self.remaining_image_slots = remaining_image_slots
        self.error_message = error_message


def check_brushstroke_balance(user: User, brushstrokes_needed: int) -> Tuple[bool, int, str]:
    """
    Check if user has sufficient brushstrokes.

    Args:
        user: User object
        brushstrokes_needed: Number of brushstrokes required

    Returns:
        Tuple of (has_sufficient: bool, current_balance: int, error_message: str)
    """
    subscription_info_tuple = get_subscription_info(user)
    monthly_allowance = subscription_info_tuple[1] if subscription_info_tuple else 0
    current_balance = user.total_brushstrokes(monthly_allowance)

    if current_balance < brushstrokes_needed:
        return False, current_balance, f"Insufficient brushstrokes. Need {brushstrokes_needed}, have {current_balance}."

    return True, current_balance, ""


def generate_image(
    user: User,
    text: str,
    generation_type: str,
    quality: str,
    aspect_ratio: Optional[str] = None,
    prompt: str = "",
    reference_image_paths: List[pathlib.Path] | None = None,
    source: str = "web",
    api_key=None
) -> GenerationResult:
    """
    Generate an image using AI.

    This is the shared service used by both web and API routes.

    Args:
        user: User object
        text: Description of the image to generate
        generation_type: Type of generation (character, scene, creature, item)
        quality: Quality level (low, medium, high)
        aspect_ratio: Aspect ratio (square, landscape, portrait). If None, defaults to square for most types, landscape for scenes
        prompt: Additional context or prompt (default: "")
        reference_image_paths: List of reference image paths (default: None)
        source: Source of generation ("web" or "api", default: "web")
        api_key: API key object if from API (default: None)

    Returns:
        GenerationResult object
    """
    if reference_image_paths is None:
        reference_image_paths = []

    # Determine aspect ratio and size
    if aspect_ratio is None:
        # Default: square for all except scenes which default to landscape
        if generation_type == ImageGenerationType.SCENE.value:
            aspect_ratio = AspectRatio.LANDSCAPE.value
        else:
            aspect_ratio = AspectRatio.SQUARE.value

    # Convert aspect ratio to size
    size = ASPECT_RATIO_SIZES.get(AspectRatio(aspect_ratio), "1024x1024")

    # Calculate cost
    brushstrokes_needed = QUALITY_COSTS.get(ImageQuality(quality), 3)

    # Check balance
    has_sufficient, current_balance, error_msg = check_brushstroke_balance(user, brushstrokes_needed)
    if not has_sufficient:
        return GenerationResult(
            success=False,
            error_message=error_msg,
            brushstrokes_remaining=current_balance
        )

    # Select generator
    generator_map: dict[str, ImageGenerator] = {
        "character": CharacterImageGenerator(),
        "scene": SceneImageGenerator(),
        "creature": CreatureImageGenerator(),
        "item": ItemImageGenerator(),
    }

    generator = generator_map.get(generation_type)
    if not generator:
        return GenerationResult(
            success=False,
            error_message=f"Invalid generation_type: {generation_type}",
            brushstrokes_remaining=current_balance
        )

    try:
        # Step 1: Generate refined description (include reference images so description is consistent)
        try:
            description = generator.get_description(
                text=text,
                prompt=prompt,
                reference_images=reference_image_paths
            )
        except Exception as e:
            logger.error(f"Error generating description: {e}")
            return GenerationResult(
                success=False,
                error_message=f"Failed to generate image description: {str(e)}",
                brushstrokes_remaining=current_balance
            )

        # Step 2: Generate image (returns WebP bytes)
        try:
            image_data = generator.generate_image(
                description=description,
                reference_images=reference_image_paths,
                image_size=size,  # type: ignore
                quality=quality,  # type: ignore
            )
        except Exception as e:
            logger.error(f"Error generating image: {e}")
            error_msg = str(e)
            # Provide more helpful error messages for common failures
            if "rate_limit" in error_msg.lower():
                error_msg = "OpenAI rate limit reached. Please wait a moment and try again."
            elif "insufficient_quota" in error_msg.lower():
                error_msg = "OpenAI API quota exceeded. Please contact support."
            elif "invalid_api_key" in error_msg.lower():
                error_msg = "API configuration error. Please contact support."
            else:
                error_msg = f"Failed to generate image: {error_msg}"

            return GenerationResult(
                success=False,
                error_message=error_msg,
                brushstrokes_remaining=current_balance
            )

        # Step 3: Save generation with image data to MongoDB
        try:
            generation = save_generation_with_image(
                user=user,
                image_data=image_data,
                generation_type=generation_type,
                quality=quality,
                aspect_ratio=aspect_ratio,
                user_text=text,
                user_prompt=prompt,
                refined_description=description,
                image_size=size,
                brushstrokes_used=brushstrokes_needed,
                source=source,
                api_key=api_key,
            )
        except Exception as e:
            logger.error(f"Error saving generation: {e}")
            return GenerationResult(
                success=False,
                error_message=f"Failed to save generation: {str(e)}",
                brushstrokes_remaining=current_balance
            )

        # Step 4: Record usage (deduct brushstrokes)
        try:
            success = record_generation(user, brushstrokes_needed, str(generation.id)) # type: ignore
            if not success:
                logger.warning("Image generated but brushstrokes may not have been deducted")
                # Continue anyway - image was generated successfully
        except Exception as e:
            logger.error(f"Error recording generation: {e}")
            # Continue anyway - image was generated successfully

        # Get updated balance and remaining slots
        user.reload()
        subscription_info_tuple = get_subscription_info(user)
        monthly_allowance = subscription_info_tuple[1] if subscription_info_tuple else 0
        remaining_brushstrokes = user.total_brushstrokes(monthly_allowance)
        remaining_slots = get_remaining_image_slots(user)

        return GenerationResult(
            success=True,
            generation_id=str(generation.id), # type: ignore
            refined_description=description,
            brushstrokes_used=brushstrokes_needed,
            brushstrokes_remaining=remaining_brushstrokes,
            remaining_image_slots=remaining_slots
        )

    except Exception as e:
        logger.error(f"Unexpected error in generate_image: {e}")
        import traceback
        traceback.print_exc()

        return GenerationResult(
            success=False,
            error_message=f"Unexpected error: {str(e)}",
            brushstrokes_remaining=current_balance
        )
