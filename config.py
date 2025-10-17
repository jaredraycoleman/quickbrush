import os
from dotenv import load_dotenv
load_dotenv()

class Config:
    APP_SECRET_KEY: str = os.getenv("APP_SECRET_KEY", "replace-with-random-secret")

    # ========================================
    # AUTH0 CONFIGURATION
    # ========================================
    AUTH0_DOMAIN: str = os.environ["AUTH0_DOMAIN"]
    AUTH0_AUDIENCE: str = os.environ["AUTH0_AUDIENCE"]
    AUTH0_CLIENT_ID: str = os.environ["AUTH0_CLIENT_ID"]
    AUTH0_CLIENT_SECRET: str = os.environ["AUTH0_CLIENT_SECRET"]
    AUTH0_CALLBACK_URL: str = os.environ["AUTH0_CALLBACK_URL"]

    # ========================================
    # MONGODB CONFIGURATION
    # ========================================
    MONGODB_URI: str = os.environ["MONGODB_URI"]
    MONGODB_DB_NAME: str = os.environ.get("MONGODB_DB_NAME", "quickbrush")

    # ========================================
    # STRIPE CONFIGURATION
    # ========================================
    STRIPE_SECRET_KEY: str = os.environ["STRIPE_SECRET_KEY"]
    STRIPE_WEBHOOK_SECRET: str = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

    PORTAL_RETURN_URL: str = os.environ["PORTAL_RETURN_URL"]

    # Subscription Price IDs (set these in Stripe dashboard)
    # Format: price_xxxxx
    STRIPE_PRICE_BASIC: str = os.environ.get("STRIPE_PRICE_BASIC", "CONFIGURE_IN_ENV")  # $5/month - 250 brushstrokes
    STRIPE_PRICE_PRO: str = os.environ.get("STRIPE_PRICE_PRO", "CONFIGURE_IN_ENV")  # $10/month - 500 brushstrokes
    STRIPE_PRICE_PREMIUM: str = os.environ.get("STRIPE_PRICE_PREMIUM", "CONFIGURE_IN_ENV")  # $20/month - 1000 brushstrokes
    STRIPE_PRICE_ULTIMATE: str = os.environ.get("STRIPE_PRICE_ULTIMATE", "CONFIGURE_IN_ENV")  # $50/month - 2500 brushstrokes

    # One-time brushstroke pack Price IDs (set these in Stripe dashboard)
    # Format: price_xxxxx
    # Pricing: $0.04/brushstroke (50% more expensive than subscription)
    STRIPE_PRICE_PACK_250: str = os.environ.get("STRIPE_PRICE_PACK_250", "CONFIGURE_IN_ENV")  # $10 for 250 brushstrokes
    STRIPE_PRICE_PACK_500: str = os.environ.get("STRIPE_PRICE_PACK_500", "CONFIGURE_IN_ENV")  # $20 for 500 brushstrokes
    STRIPE_PRICE_PACK_1000: str = os.environ.get("STRIPE_PRICE_PACK_1000", "CONFIGURE_IN_ENV")  # $40 for 1000 brushstrokes
    STRIPE_PRICE_PACK_2500: str = os.environ.get("STRIPE_PRICE_PACK_2500", "CONFIGURE_IN_ENV")  # $100 for 2500 brushstrokes

    # Brushstroke packs configuration
    # Maps Stripe price IDs to brushstroke amounts
    BRUSHSTROKE_PACKS = {
        # Will be populated dynamically from price IDs
        # price_id: (amount_cents, brushstrokes)
    }

    @classmethod
    def get_brushstroke_packs(cls):
        """Get brushstroke packs mapping."""
        return {
            cls.STRIPE_PRICE_PACK_250: (1000, 250),  # $10 = 250 brushstrokes
            cls.STRIPE_PRICE_PACK_500: (2000, 500),  # $20 = 500 brushstrokes
            cls.STRIPE_PRICE_PACK_1000: (4000, 1000),  # $40 = 1000 brushstrokes
            cls.STRIPE_PRICE_PACK_2500: (10000, 2500),  # $100 = 2500 brushstrokes
        }

    @classmethod
    def get_subscription_tiers(cls):
        """Get subscription tier mapping."""
        return {
            cls.STRIPE_PRICE_BASIC: ("basic", 250),
            cls.STRIPE_PRICE_PRO: ("pro", 500),
            cls.STRIPE_PRICE_PREMIUM: ("premium", 1000),
            cls.STRIPE_PRICE_ULTIMATE: ("ultimate", 2500),
        }
