"""
FastAPI routes for the Quickbrush API.

This module provides RESTful API endpoints for:
- Image generation
- API key management
- User account information
"""

from fastapi import FastAPI, HTTPException, Depends, Security, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Literal
from datetime import datetime
import logging

from models import User, Generation
from api_key_service import authenticate_api_key
from generation_service import generate_image as generate_image_shared

logger = logging.getLogger(__name__)

# Initialize FastAPI app
api = FastAPI(
    title="Quickbrush API",
    description="API for generating fantasy RPG artwork using AI",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Security
security = HTTPBearer()


# ========================================
# AUTHENTICATION DEPENDENCY
# ========================================

async def get_current_user(authorization: Optional[str] = Header(None)) -> User:
    """
    Dependency to authenticate API requests via API key.

    Expects: Authorization: Bearer qb_xxxxx:secret
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = authenticate_api_key(authorization)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if subscription needs renewal
    from stripe_utils import check_and_renew_subscription
    check_and_renew_subscription(user)

    return user


# ========================================
# REQUEST/RESPONSE MODELS
# ========================================

class GenerateImageRequest(BaseModel):
    """Request model for image generation."""
    text: str = Field(..., description="Description of the image to generate", min_length=1, max_length=1000)
    prompt: Optional[str] = Field(None, description="Additional context or prompt", max_length=2000)
    generation_type: Literal["character", "scene", "creature", "item"] = Field(
        default="character",
        description="Type of image to generate"
    )
    quality: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="Image quality (affects brushstroke cost: low=1, medium=3, high=5)"
    )
    aspect_ratio: Optional[Literal["square", "landscape", "portrait"]] = Field(
        None,
        description="Aspect ratio (square=1024x1024, landscape=1536x1024, portrait=1024x1536). Defaults to square for most types, landscape for scenes."
    )
    # Deprecated field - kept for backward compatibility
    size: Optional[Literal["1024x1024", "1536x1024", "1024x1536"]] = Field(
        None,
        description="[DEPRECATED] Use aspect_ratio instead. Image size in pixels"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "text": "A brave knight with silver armor",
                "prompt": "Fantasy RPG character for my campaign",
                "generation_type": "character",
                "quality": "medium",
                "aspect_ratio": "square"
            }
        }


class GenerateImageResponse(BaseModel):
    """Response model for image generation."""
    success: bool
    generation_id: str
    image_url: str
    refined_description: str
    brushstrokes_used: int
    brushstrokes_remaining: int
    remaining_image_slots: int
    message: str


class ErrorResponse(BaseModel):
    """Error response model."""
    detail: str
    code: Optional[str] = None


class UserInfoResponse(BaseModel):
    """Response model for user information."""
    email: str
    subscription_tier: str
    subscription_status: str
    total_brushstrokes: int
    subscription_allowance_remaining: int
    purchased_brushstrokes: int
    current_period_end: Optional[datetime]


# ========================================
# API ENDPOINTS
# ========================================

@api.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "quickbrush-api"}


@api.get("/rate-limit", tags=["User"])
async def get_rate_limit_status(user: User = Depends(get_current_user)):
    """
    Get current rate limit status for the authenticated user.

    Returns information about current usage and limits for image generation.
    """
    from rate_limiter import get_rate_limit_status
    return get_rate_limit_status(user, action="generate_image")


@api.get("/user", response_model=UserInfoResponse, tags=["User"])
async def get_user_info(user: User = Depends(get_current_user)):
    """
    Get current user information including subscription and brushstroke balance.
    """
    # Get subscription info from Stripe (single source of truth)
    from stripe_utils import get_subscription_info
    subscription_info_tuple = get_subscription_info(user)

    if subscription_info_tuple and subscription_info_tuple[0]:
        sub_dict, monthly_allowance = subscription_info_tuple
        if not sub_dict:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve subscription information"
            )
        allowance_used = user.subscription.allowance_used_this_period if user.subscription else 0 # type: ignore
        return UserInfoResponse(
            email=user.email, # type: ignore
            subscription_tier=sub_dict["tier"],
            subscription_status=sub_dict["status"],
            total_brushstrokes=user.total_brushstrokes(monthly_allowance),
            subscription_allowance_remaining=max(0, monthly_allowance - allowance_used), # type: ignore
            purchased_brushstrokes=user.purchased_brushstrokes, # type: ignore
            current_period_end=sub_dict["current_period_end"],
        )
    else:
        return UserInfoResponse(
            email=user.email, # type: ignore
            subscription_tier="free",
            subscription_status="none",
            total_brushstrokes=user.total_brushstrokes(0),
            subscription_allowance_remaining=0,
            purchased_brushstrokes=user.purchased_brushstrokes, # type: ignore
            current_period_end=None,
        )


@api.post(
    "/generate",
    response_model=GenerateImageResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        402: {"model": ErrorResponse, "description": "Insufficient brushstrokes"},
        500: {"model": ErrorResponse, "description": "Generation failed"},
    },
    tags=["Generation"]
)
async def generate_image(
    request: GenerateImageRequest,
    user: User = Depends(get_current_user)
):
    """
    Generate an image using AI.

    This endpoint:
    1. Validates the request
    2. Checks brushstroke balance
    3. Generates the image using OpenAI
    4. Deducts brushstrokes
    5. Returns the generated image URL

    **Authentication**: Requires valid API key in Authorization header.

    **Rate Limits**: Respects OpenAI rate limits.

    **Costs**:
    - Low quality: 1 brushstroke
    - Medium quality: 3 brushstrokes
    - High quality: 5 brushstrokes

    **Note**: Images are stored as WebP format in MongoDB. Only the last 100 images per user are kept.
    """
    # Handle backward compatibility: convert size to aspect_ratio if provided
    aspect_ratio = request.aspect_ratio
    if not aspect_ratio and request.size:
        # Map old size values to aspect_ratio
        size_to_aspect = {
            "1024x1024": "square",
            "1536x1024": "landscape",
            "1024x1536": "portrait"
        }
        aspect_ratio = size_to_aspect.get(request.size)

    # Use shared generation service
    result = generate_image_shared(
        user=user,
        text=request.text,
        generation_type=request.generation_type,
        quality=request.quality,
        aspect_ratio=aspect_ratio,
        prompt=request.prompt or "",
        reference_image_paths=[],
        source="api"
    )

    if not result.success:
        # Determine appropriate status code
        if "rate limit exceeded" in (result.error_message or "").lower():
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=result.error_message
            )
        elif "insufficient brushstrokes" in (result.error_message or "").lower():
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=result.error_message
            )
        elif "invalid generation_type" in (result.error_message or "").lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.error_message
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.error_message
            )
        
    if not result.generation_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Generation failed: missing generation ID"
        )
    
    if not result.refined_description:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Generation failed: missing refined description"
        )

    # Success - return response
    return GenerateImageResponse(
        success=True,
        generation_id=result.generation_id,
        image_url=f"/api/image/{result.generation_id}",
        refined_description=result.refined_description,
        brushstrokes_used=result.brushstrokes_used,
        brushstrokes_remaining=result.brushstrokes_remaining,
        remaining_image_slots=result.remaining_image_slots,
        message="Image generated successfully"
    )


@api.get("/image/{generation_id}", tags=["Generation"])
async def get_image(
    generation_id: str,
    user: User = Depends(get_current_user)
):
    """
    Get a generated image by ID.

    Returns the WebP image data.
    """
    from image_service import get_generation_by_id
    from fastapi.responses import Response

    generation = get_generation_by_id(generation_id, user)
    if not generation or not generation.image_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found"
        )

    return Response(
        content=generation.image_data,
        media_type="image/webp",
        headers={"Content-Disposition": f'inline; filename="generated_{generation_id}.webp"'}
    )


@api.get("/generations", tags=["Generation"])
async def list_generations(
    limit: int = 10,
    offset: int = 0,
    user: User = Depends(get_current_user)
):
    """
    List user's recent image generations.

    **Parameters**:
    - limit: Maximum number of results (default: 10, max: 100)
    - offset: Number of results to skip (default: 0)

    **Note**: Only the last 100 images are stored. Image URLs point to `/api/image/{id}`.
    """
    limit = min(limit, 100)

    from image_service import get_user_generations

    generations = get_user_generations(user, limit=limit, include_without_images=False)

    # Skip offset manually since we're using the service
    generations = generations[offset:]

    return {
        "generations": [
            {
                "id": str(gen.id),
                "generation_type": gen.generation_type,
                "quality": gen.quality,
                "user_text": gen.user_text,
                "image_url": f"/api/image/{str(gen.id)}",
                "brushstrokes_used": gen.brushstrokes_used,
                "status": gen.status,
                "created_at": gen.created_at,
                "completed_at": gen.completed_at,
            }
            for gen in generations
        ],
        "total": len(get_user_generations(user, limit=100, include_without_images=False)),
        "limit": limit,
        "offset": offset,
    }


# ========================================
# API KEY MANAGEMENT
# ========================================
# Note: API key management is only available through the web UI
# at /api-keys for security reasons.


# ========================================
# ERROR HANDLERS
# ========================================

@api.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": exc.status_code}
    )


# ========================================
# STARTUP/SHUTDOWN
# ========================================

@api.on_event("startup")
async def startup_event():
    """Initialize connections on startup."""
    logger.info("FastAPI application starting up")
    from database import init_db
    init_db()


@api.on_event("shutdown")
async def shutdown_event():
    """Clean up on shutdown."""
    logger.info("FastAPI application shutting down")
    from database import close_db
    close_db()
