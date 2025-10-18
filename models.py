"""
MongoDB models for Quickbrush application.

This module defines the data schemas for:
- Users (Auth0 + Stripe integration)
- API Keys
- Image Generations (history/logs)
- Brushstroke Transactions (purchases, usage)
"""

from datetime import datetime, timezone
from typing import Optional
from enum import Enum
from mongoengine import (
    Document,
    EmbeddedDocument,
    StringField,
    IntField,
    BooleanField,
    DateTimeField,
    ListField,
    DictField,
    EmbeddedDocumentField,
    ReferenceField,
    BinaryField,
    NULLIFY,
)
import secrets


# ========================================
# ENUMS
# ========================================

class TransactionType(str, Enum):
    """Types of brushstroke transactions."""
    PURCHASE = "purchase"  # One-time pack purchase
    SUBSCRIPTION_RENEWAL = "subscription_renewal"  # Monthly allowance grant
    USAGE = "usage"  # Image generation usage
    REFUND = "refund"  # Refunded brushstrokes
    ADMIN_GRANT = "admin_grant"  # Manual admin credit


class ImageGenerationType(str, Enum):
    """Types of image generation."""
    CHARACTER = "character"
    SCENE = "scene"
    CREATURE = "creature"
    ITEM = "item"


class ImageQuality(str, Enum):
    """Image quality levels with brushstroke costs."""
    LOW = "low"  # 1 brushstroke
    MEDIUM = "medium"  # 3 brushstrokes
    HIGH = "high"  # 5 brushstrokes


class AspectRatio(str, Enum):
    """Aspect ratio options for image generation."""
    SQUARE = "square"  # 1024x1024
    LANDSCAPE = "landscape"  # 1536x1024
    PORTRAIT = "portrait"  # 1024x1536


QUALITY_COSTS = {
    ImageQuality.LOW: 1,
    ImageQuality.MEDIUM: 3,
    ImageQuality.HIGH: 5,
}

ASPECT_RATIO_SIZES = {
    AspectRatio.SQUARE: "1024x1024",
    AspectRatio.LANDSCAPE: "1536x1024",
    AspectRatio.PORTRAIT: "1024x1536",
}


# ========================================
# EMBEDDED DOCUMENTS
# ========================================

class SubscriptionInfo(EmbeddedDocument):
    """
    Minimal subscription tracking in MongoDB.

    Only stores usage data - all subscription details (tier, status, dates, etc.)
    are fetched from Stripe on-demand to maintain a single source of truth.
    """
    # Stripe reference - this is the ONLY subscription data we store
    stripe_subscription_id = StringField(sparse=True)

    # Usage tracking for current period - THIS is what we need to track
    current_period_start = DateTimeField()  # Track period to know when to reset
    allowance_used_this_period = IntField(default=0)  # How many brushstrokes used this period

    updated_at = DateTimeField(default=lambda: datetime.now(timezone.utc))

    def reset_allowance(self, new_period_start: datetime):
        """Reset allowance for new billing period."""
        self.allowance_used_this_period = 0
        self.current_period_start = new_period_start
        self.updated_at = datetime.now(timezone.utc)


# ========================================
# USER MODEL
# ========================================

class User(Document):
    """
    User model storing Auth0 and Stripe integration.

    This is the single source of truth for user data, replacing the previous
    approach of storing data in Stripe customer metadata.
    """
    # Auth0 fields
    auth0_sub = StringField(required=True, unique=True)  # Auth0 user ID
    email = StringField(required=True)
    name = StringField()
    picture = StringField()  # Profile picture URL

    # Stripe integration
    stripe_customer_id = StringField(sparse=True, unique=True)  # Created on first purchase

    # Subscription information
    subscription = EmbeddedDocumentField(SubscriptionInfo, default=SubscriptionInfo)

    # Brushstroke balance (non-expiring purchased packs)
    purchased_brushstrokes = IntField(default=0)  # Total purchased via one-time packs

    # Metadata
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=lambda: datetime.now(timezone.utc))
    updated_at = DateTimeField(default=lambda: datetime.now(timezone.utc))
    last_login = DateTimeField()

    # Additional fields
    metadata = DictField(default=dict)  # For any additional data

    meta = {
        'collection': 'users',
        'indexes': [
            'auth0_sub',
            'stripe_customer_id',
            'email',
            'created_at',
        ]
    }

    def __str__(self):
        return f"User({self.email}, {self.auth0_sub})"

    def total_brushstrokes(self, subscription_allowance: int = 0) -> int:
        """
        Calculate total available brushstrokes.

        Args:
            subscription_allowance: Current subscription allowance from Stripe

        Returns:
            Total brushstrokes = subscription allowance remaining + purchased packs
        """
        subscription_used = self.subscription.allowance_used_this_period if self.subscription else 0 # type: ignore
        subscription_remaining = max(0, subscription_allowance - subscription_used) # type: ignore
        return subscription_remaining + self.purchased_brushstrokes # type: ignore

    def use_brushstrokes(self, amount: int, subscription_allowance: int = 0) -> bool:
        """
        Deduct brushstrokes from available balance.
        Priority: Subscription allowance first, then purchased packs.

        Args:
            amount: Number of brushstrokes to deduct
            subscription_allowance: Total subscription allowance for current period

        Returns:
            True if successful, False if insufficient balance
        """
        if self.total_brushstrokes(subscription_allowance) < amount:
            return False

        # First, use subscription allowance
        if self.subscription:
            subscription_used = self.subscription.allowance_used_this_period # type: ignore
            allowance_remaining = max(0, subscription_allowance - subscription_used) # type: ignore

            if allowance_remaining > 0:
                used_from_allowance = min(amount, allowance_remaining)
                self.subscription.allowance_used_this_period += used_from_allowance # type: ignore
                amount -= used_from_allowance

        # Then use purchased packs
        if amount > 0:
            self.purchased_brushstrokes -= amount # type: ignore

        self.updated_at = datetime.now(timezone.utc)
        return True

    def add_purchased_brushstrokes(self, amount: int):
        """Add brushstrokes from one-time pack purchase."""
        self.purchased_brushstrokes += amount # type: ignore
        self.updated_at = datetime.now(timezone.utc)

    def set_subscription_id(self, stripe_subscription_id: str, period_start: datetime):
        """
        Set the Stripe subscription ID and initialize usage tracking.

        This is called when a subscription is first created.
        """
        if not self.subscription:
            self.subscription = SubscriptionInfo()

        self.subscription.stripe_subscription_id = stripe_subscription_id # type: ignore
        self.subscription.current_period_start = period_start # type: ignore
        self.subscription.allowance_used_this_period = 0 # type: ignore
        self.subscription.updated_at = datetime.now(timezone.utc) # type: ignore
        self.updated_at = datetime.now(timezone.utc)

    def clear_subscription(self):
        """Remove subscription reference when it's canceled/deleted."""
        if self.subscription:
            self.subscription.stripe_subscription_id = None # type: ignore
            self.subscription.current_period_start = None # type: ignore
            self.subscription.allowance_used_this_period = 0 # type: ignore
            self.subscription.updated_at = datetime.now(timezone.utc) # type: ignore
            self.updated_at = datetime.now(timezone.utc)


# ========================================
# API KEY MODEL
# ========================================

class APIKey(Document):
    """
    API key for programmatic access to image generation.

    Keys are hashed before storage for security.
    """
    user = ReferenceField(User, required=True, reverse_delete_rule=NULLIFY)

    # Key information
    key_id = StringField(required=True, unique=True)  # Public identifier (e.g., "qb_abc123...")
    key_hash = StringField(required=True)  # Hashed secret key
    key_prefix = StringField(required=True)  # First 8 chars for user identification

    # Metadata
    name = StringField(required=True)  # User-provided name for the key
    is_active = BooleanField(default=True)

    # Usage tracking
    last_used_at = DateTimeField()
    total_requests = IntField(default=0)

    # Timestamps
    created_at = DateTimeField(default=lambda: datetime.now(timezone.utc))
    expires_at = DateTimeField()  # Optional expiration

    meta = {
        'collection': 'api_keys',
        'indexes': [
            'key_id',
            'user',
            'is_active',
            'created_at',
        ]
    }

    def __str__(self):
        return f"APIKey({self.key_id}, {self.name})"

    @staticmethod
    def generate_key() -> tuple[str, str]:
        """
        Generate a new API key pair.

        Returns:
            (key_id, secret_key) - The key_id is stored, secret_key is shown once to user
        """
        # Generate a secure random key (32 bytes = 256 bits)
        secret = secrets.token_urlsafe(32)
        key_id = f"qb_{secrets.token_urlsafe(16)}"
        return key_id, secret

    @staticmethod
    def hash_key(secret: str) -> str:
        """Hash an API key for secure storage."""
        import hashlib
        return hashlib.sha256(secret.encode()).hexdigest()

    def verify_key(self, secret: str) -> bool:
        """Verify a secret key against this API key."""
        return self.key_hash == self.hash_key(secret)

    def record_usage(self):
        """Record that this key was used."""
        self.last_used_at = datetime.now(timezone.utc)
        self.total_requests += 1 # type: ignore


# ========================================
# TRANSACTION MODEL
# ========================================

class BrushstrokeTransaction(Document):
    """
    Record of all brushstroke transactions (purchases, usage, refunds).

    This provides a complete audit trail of all brushstroke movements.
    """
    user = ReferenceField(User, required=True)

    # Transaction details
    transaction_type = StringField(
        required=True,
        choices=[t.value for t in TransactionType]
    )
    amount = IntField(required=True)  # Positive for credits, negative for usage
    balance_after = IntField(required=True)  # Snapshot of total balance after transaction

    # Payment information (for purchases)
    stripe_payment_intent_id = StringField()
    stripe_charge_id = StringField()
    amount_paid_cents = IntField()  # Amount paid in cents (for purchases)

    # Subscription information (for renewals)
    stripe_subscription_id = StringField()
    subscription_period_start = DateTimeField()
    subscription_period_end = DateTimeField()

    # Generation information (for usage)
    generation = ReferenceField('Generation')  # Reference to the generation this was used for

    # Metadata
    description = StringField()
    metadata = DictField(default=dict)
    created_at = DateTimeField(default=lambda: datetime.now(timezone.utc))

    meta = {
        'collection': 'transactions',
        'indexes': [
            'user',
            'transaction_type',
            'created_at',
            'stripe_payment_intent_id',
        ]
    }

    def __str__(self):
        return f"Transaction({self.transaction_type}, {self.amount}, {self.created_at})"


# ========================================
# GENERATION MODEL
# ========================================

class Generation(Document):
    """
    Record of image generation requests.

    Stores all details about generated images for history and analytics.
    Images are stored as binary WebP data in MongoDB (max 100 per user).
    """
    user = ReferenceField(User, required=True)

    # Generation parameters
    generation_type = StringField(
        required=True,
        choices=[t.value for t in ImageGenerationType]
    )
    quality = StringField(
        required=True,
        choices=[q.value for q in ImageQuality]
    )
    aspect_ratio = StringField(
        choices=[a.value for a in AspectRatio],
        default=AspectRatio.SQUARE.value
    )

    # Input
    user_text = StringField(required=True)  # User's description
    user_prompt = StringField()  # Additional context/prompt
    refined_description = StringField()  # GPT-4o refined description

    # Image details
    image_size = StringField(default="1024x1024")
    image_data = BinaryField()  # WebP image stored as binary data
    image_format = StringField(default="webp")  # Always webp

    # Legacy fields (deprecated but kept for backward compatibility)
    image_url = StringField()  # Deprecated
    image_filename = StringField()  # Deprecated

    # Reference images
    reference_image_urls = ListField(StringField())

    # Cost and status
    brushstrokes_used = IntField(required=True)
    status = StringField(default="completed", choices=["pending", "completed", "failed"])
    error_message = StringField()

    # API usage
    api_key = ReferenceField(APIKey)  # If generated via API
    source = StringField(default="web", choices=["web", "api"])

    # OpenAI API details
    openai_model = StringField()  # e.g., "gpt-image-1-mini"
    openai_request_id = StringField()

    # Timestamps
    created_at = DateTimeField(default=lambda: datetime.now(timezone.utc))
    completed_at = DateTimeField()

    # Metadata
    metadata = DictField(default=dict)

    meta = {
        'collection': 'generations',
        'indexes': [
            'user',
            'created_at',
            'status',
            'api_key',
            'source',
        ]
    }

    def __str__(self):
        return f"Generation({self.generation_type}, {self.quality}, {self.created_at})"


# ========================================
# LOG MODEL
# ========================================

class Log(Document):
    """
    Application-wide event logging for debugging and auditing.
    """
    level = StringField(required=True, choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    message = StringField(required=True)

    # Context
    user = ReferenceField(User)
    source = StringField()  # Module/function that created the log

    # Additional data
    metadata = DictField(default=dict)
    stack_trace = StringField()

    # Timestamps
    created_at = DateTimeField(default=lambda: datetime.now(timezone.utc))

    meta = {
        'collection': 'logs',
        'indexes': [
            'level',
            'created_at',
            'user',
            'source',
        ]
    }

    def __str__(self):
        return f"Log({self.level}, {self.message[:50]})" # type: ignore


# ========================================
# HELPER FUNCTIONS
# ========================================

def get_user_by_auth0_sub(auth0_sub: str) -> Optional[User]:
    """Get user by Auth0 sub (user ID)."""
    try:
        return User.objects(auth0_sub=auth0_sub).first() # type: ignore
    except Exception as e:
        print(f"Error fetching user by auth0_sub: {e}")
        return None


def get_or_create_user(auth0_sub: str, email: str, name: str | None = None, picture: str | None = None) -> User:
    """Get or create a user by Auth0 sub."""
    user = get_user_by_auth0_sub(auth0_sub)
    if user:
        # Update last login
        user.last_login = datetime.now(timezone.utc)
        # Update email if changed
        if user.email != email:
            user.email = email
        if name and user.name != name:
            user.name = name
        if picture and user.picture != picture:
            user.picture = picture
        user.save()
        return user

    # Create new user
    user = User(
        auth0_sub=auth0_sub,
        email=email,
        name=name,
        picture=picture,
        last_login=datetime.now(timezone.utc),
    )
    user.save()
    return user


def verify_api_key(key_id: str, secret: str) -> Optional[APIKey]:
    """
    Verify an API key and return it if valid.

    Returns None if key is invalid, inactive, or expired.
    """
    try:
        api_key = APIKey.objects(key_id=key_id, is_active=True).first() # type: ignore
        if not api_key:
            return None

        # Check expiration
        if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
            return None

        # Verify secret
        if not api_key.verify_key(secret):
            return None

        return api_key
    except Exception as e:
        print(f"Error verifying API key: {e}")
        return None
