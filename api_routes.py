"""
FastAPI routes for the Quickbrush API.

This module provides RESTful API endpoints for:
- Image generation
- API key management
- User account information
"""

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
import logging

from models import User
from api_key_service import authenticate_api_key
from generation_service import generate_image as generate_image_shared
from config import Config

logger = logging.getLogger(__name__)

# Initialize FastAPI app
api = FastAPI(
    title="Quickbrush API",
    description="API for generating fantasy RPG artwork using AI",
    version="1.0.1",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    swagger_ui_parameters={
        "persistAuthorization": True,
    }
)

# Add CORS middleware for Foundry VTT integration
api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for local Foundry VTT installations
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security scheme
security = HTTPBearer(
    scheme_name="Bearer",
    description="API Key (qb_keyid:secret) or OAuth Token (qb_at_xxxxx)",
    auto_error=False
)


# ========================================
# AUTHENTICATION DEPENDENCY
# ========================================

async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> User:
    """Authenticate API requests via API key or OAuth token."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get the authorization value (without "Bearer " prefix)
    auth_value = credentials.credentials

    # Try OAuth token first (starts with qb_at_)
    if auth_value.startswith("qb_at_"):
        from oauth_service import verify_access_token
        result = verify_access_token(auth_value)

        if result:
            oauth_token, user = result
            # Check if subscription needs renewal
            from stripe_utils import check_and_renew_subscription
            check_and_renew_subscription(user)
            return user
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired OAuth token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Try API key authentication (qb_keyid:secret format)
    # Need to add "Bearer " prefix back for authenticate_api_key
    user = authenticate_api_key(f"Bearer {auth_value}")
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired credentials",
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
    text: str = Field(..., description="Description of the image to generate", min_length=1, max_length=Config.MAX_TEXT_LENGTH)
    image_name: str = Field(..., description="Name to save the image as", min_length=1, max_length=100)
    prompt: Optional[str] = Field(None, description="Additional context or prompt", max_length=Config.MAX_PROMPT_LENGTH)
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
    reference_image_paths: Optional[list[str]] = Field(
        default=[],
        description="Optional list of reference image paths/URLs (max 3). Supports URLs, data URIs, or file paths.",
        max_length=3
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
                "image_name": "Silver Knight",
                "prompt": "Fantasy RPG character for my campaign",
                "generation_type": "character",
                "quality": "medium",
                "aspect_ratio": "square",
                "reference_image_paths": []
            }
        }


class GenerateImageResponse(BaseModel):
    """Response model for image generation."""
    success: bool
    generation_id: str
    image_url: str
    refined_description: str
    image_name: Optional[str] = None
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
    """Get current rate limit status and usage for image generation."""
    from rate_limiter import get_rate_limit_status
    return get_rate_limit_status(user, action="generate_image")


@api.get("/user", response_model=UserInfoResponse, tags=["User"])
async def get_user_info(user: User = Depends(get_current_user)):
    """Get user account info including subscription tier and brushstroke balance."""
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
    Generate an AI image. Costs: low=1, medium=3, high=5 brushstrokes. Returns WebP format. Max 100 images stored per user.
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

    # Process reference images (URLs, base64, etc.) into temp files
    from image_utils import process_reference_images, cleanup_temp_images

    reference_paths = []
    if request.reference_image_paths:
        try:
            reference_paths = process_reference_images(request.reference_image_paths, max_images=3)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error processing reference images: {str(e)}"
            )

    try:
        # Use shared generation service
        result = generate_image_shared(
            user=user,
            text=request.text,
            generation_type=request.generation_type,
            quality=request.quality,
            image_name=request.image_name,
            aspect_ratio=aspect_ratio,
            prompt=request.prompt or "",
            reference_image_paths=reference_paths,
            source="api"
        )
    finally:
        # Clean up temporary reference image files
        cleanup_temp_images(reference_paths)

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
        image_name=result.image_name,
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
    """Get a generated image by ID. Returns WebP image data."""
    from image_service import get_generation_by_id
    from fastapi.responses import Response

    generation = get_generation_by_id(generation_id, user)
    if not generation or not generation.image_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found"
        )

    # Use generated name if available, otherwise fall back to generation_id
    import re
    if generation.image_name:
        filename = str(generation.image_name)
        # Sanitize filename (remove invalid characters)
        filename = re.sub(r'[^\w\s-]', '', filename).strip()
        filename = re.sub(r'[-\s]+', '-', filename)
    else:
        filename = f"generated_{generation_id}"
    filename = f"{filename}.webp"

    return Response(
        content=generation.image_data,
        media_type="image/webp",
        headers={"Content-Disposition": f'inline; filename="{filename}"'}
    )


@api.get("/generations", tags=["Generation"])
async def list_generations(
    limit: int = 10,
    offset: int = 0,
    user: User = Depends(get_current_user)
):
    """List user's recent generations. Max 100 stored. Supports pagination via limit/offset."""
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
                "aspect_ratio": gen.aspect_ratio,
                "user_text": gen.user_text,
                "user_prompt": gen.user_prompt,
                "image_name": gen.image_name,
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
