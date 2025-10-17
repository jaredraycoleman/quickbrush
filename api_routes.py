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

from models import (
    User, Generation, ImageGenerationType, ImageQuality,
    QUALITY_COSTS
)
from api_key_service import authenticate_api_key, get_user_api_keys, create_api_key, revoke_api_key
from stripe_utils import record_generation
from maker import (
    CharacterImageGenerator, SceneImageGenerator,
    CreatureImageGenerator, ItemImageGenerator,
    IMAGE_SIZE, QUALITY
)
import pathlib
import uuid

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

GENERATED_DIR = pathlib.Path("static/generated")
GENERATED_DIR.mkdir(parents=True, exist_ok=True)


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
    size: Literal["1024x1024", "1536x1024"] = Field(
        default="1024x1024",
        description="Image size in pixels"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "text": "A brave knight with silver armor",
                "prompt": "Fantasy RPG character for my campaign",
                "generation_type": "character",
                "quality": "medium",
                "size": "1024x1024"
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


class APIKeyInfo(BaseModel):
    """Response model for API key information."""
    key_id: str
    name: str
    key_prefix: str
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime]
    total_requests: int
    expires_at: Optional[datetime]


class CreateAPIKeyRequest(BaseModel):
    """Request model for creating an API key."""
    name: str = Field(..., description="Name/description for this API key", min_length=1, max_length=100)
    expires_in_days: Optional[int] = Field(None, description="Optional: Days until expiration", gt=0, le=365)


class CreateAPIKeyResponse(BaseModel):
    """Response model for API key creation."""
    key_id: str
    secret_key: str
    name: str
    expires_at: Optional[datetime]
    message: str = "API key created successfully. Save the secret key - it won't be shown again!"


# ========================================
# API ENDPOINTS
# ========================================

@api.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "quickbrush-api"}


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
        allowance_used = user.subscription.allowance_used_this_period if user.subscription else 0
        return UserInfoResponse(
            email=user.email,
            subscription_tier=sub_dict["tier"],
            subscription_status=sub_dict["status"],
            total_brushstrokes=user.total_brushstrokes(monthly_allowance),
            subscription_allowance_remaining=max(0, monthly_allowance - allowance_used),
            purchased_brushstrokes=user.purchased_brushstrokes,
            current_period_end=sub_dict["current_period_end"],
        )
    else:
        return UserInfoResponse(
            email=user.email,
            subscription_tier="free",
            subscription_status="none",
            total_brushstrokes=user.total_brushstrokes(0),
            subscription_allowance_remaining=0,
            purchased_brushstrokes=user.purchased_brushstrokes,
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
    """
    # Calculate cost
    brushstrokes_needed = QUALITY_COSTS.get(ImageQuality(request.quality), 3)

    # Get subscription allowance
    from stripe_utils import get_subscription_info
    subscription_info_tuple = get_subscription_info(user)
    monthly_allowance = subscription_info_tuple[1] if subscription_info_tuple else 0

    # Check balance
    current_balance = user.total_brushstrokes(monthly_allowance)
    if current_balance < brushstrokes_needed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient brushstrokes. Need {brushstrokes_needed}, have {current_balance}."
        )

    # Select generator
    if request.generation_type == "character":
        generator = CharacterImageGenerator()
    elif request.generation_type == "scene":
        generator = SceneImageGenerator()
    elif request.generation_type == "creature":
        generator = CreatureImageGenerator()
    elif request.generation_type == "item":
        generator = ItemImageGenerator()
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid generation_type: {request.generation_type}"
        )

    try:
        # Step 1: Generate refined description
        description = generator.get_description(
            text=request.text,
            prompt=request.prompt or ""
        )

        # Step 2: Generate image
        output_path = GENERATED_DIR / f"api_generated_{uuid.uuid4()}.png"
        image_path = generator.generate_image(
            description=description,
            savepath=output_path,
            reference_images=[],
            image_size=request.size,  # type: ignore
            quality=request.quality,  # type: ignore
        )

        # Step 3: Create generation record
        generation = Generation(
            user=user,
            generation_type=request.generation_type,
            quality=request.quality,
            user_text=request.text,
            user_prompt=request.prompt,
            refined_description=description,
            image_size=request.size,
            image_url=f"/static/generated/{image_path.name}",
            image_filename=image_path.name,
            brushstrokes_used=brushstrokes_needed,
            status="completed",
            source="api",
        )
        generation.save()

        # Step 4: Deduct brushstrokes
        success = record_generation(user, brushstrokes_needed, str(generation.id))
        if not success:
            # This shouldn't happen as we already checked, but handle it
            generation.status = "failed"
            generation.error_message = "Failed to deduct brushstrokes"
            generation.save()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to record usage"
            )

        generation.completed_at = datetime.now()
        generation.save()

        # Return response (refresh user to get updated balance)
        user.reload()
        subscription_info_tuple = get_subscription_info(user)
        monthly_allowance = subscription_info_tuple[1] if subscription_info_tuple else 0

        return GenerateImageResponse(
            success=True,
            generation_id=str(generation.id),
            image_url=generation.image_url,
            refined_description=description,
            brushstrokes_used=brushstrokes_needed,
            brushstrokes_remaining=user.total_brushstrokes(monthly_allowance),
            message="Image generated successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating image: {e}")
        import traceback
        traceback.print_exc()

        # Create failed generation record
        generation = Generation(
            user=user,
            generation_type=request.generation_type,
            quality=request.quality,
            user_text=request.text,
            user_prompt=request.prompt,
            image_size=request.size,
            brushstrokes_used=0,
            status="failed",
            error_message=str(e),
            source="api",
        )
        generation.save()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Image generation failed: {str(e)}"
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
    """
    limit = min(limit, 100)

    generations = Generation.objects(user=user).order_by('-created_at').skip(offset).limit(limit)

    return {
        "generations": [
            {
                "id": str(gen.id),
                "generation_type": gen.generation_type,
                "quality": gen.quality,
                "user_text": gen.user_text,
                "image_url": gen.image_url,
                "brushstrokes_used": gen.brushstrokes_used,
                "status": gen.status,
                "created_at": gen.created_at,
                "completed_at": gen.completed_at,
            }
            for gen in generations
        ],
        "total": Generation.objects(user=user).count(),
        "limit": limit,
        "offset": offset,
    }


# ========================================
# API KEY MANAGEMENT ENDPOINTS
# ========================================

@api.get("/keys", response_model=List[APIKeyInfo], tags=["API Keys"])
async def list_api_keys(user: User = Depends(get_current_user)):
    """
    List all API keys for the current user.
    """
    keys = get_user_api_keys(user, include_inactive=True)

    return [
        APIKeyInfo(
            key_id=key.key_id,
            name=key.name,
            key_prefix=key.key_prefix,
            is_active=key.is_active,
            created_at=key.created_at,
            last_used_at=key.last_used_at,
            total_requests=key.total_requests,
            expires_at=key.expires_at,
        )
        for key in keys
    ]


@api.post("/keys", response_model=CreateAPIKeyResponse, tags=["API Keys"])
async def create_new_api_key(
    request: CreateAPIKeyRequest,
    user: User = Depends(get_current_user)
):
    """
    Create a new API key.

    **Important**: The secret key is only shown once. Save it securely!
    """
    api_key, secret = create_api_key(user, request.name, request.expires_in_days)

    return CreateAPIKeyResponse(
        key_id=api_key.key_id,
        secret_key=f"{api_key.key_id}:{secret}",
        name=api_key.name,
        expires_at=api_key.expires_at,
    )


@api.delete("/keys/{key_id}", tags=["API Keys"])
async def revoke_api_key_endpoint(
    key_id: str,
    user: User = Depends(get_current_user)
):
    """
    Revoke (deactivate) an API key.

    The key will be marked as inactive but not deleted.
    """
    from models import APIKey
    api_key = APIKey.objects(key_id=key_id, user=user).first()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    success = revoke_api_key(api_key)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke API key"
        )

    return {"message": "API key revoked successfully", "key_id": key_id}


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
