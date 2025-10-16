import os
from dotenv import load_dotenv
load_dotenv()

class Config:
    APP_SECRET_KEY: str = os.getenv("APP_SECRET_KEY", "replace-with-random-secret")

    AUTH0_DOMAIN: str = os.environ["AUTH0_DOMAIN"]
    AUTH0_AUDIENCE: str = os.environ["AUTH0_AUDIENCE"]
    AUTH0_CLIENT_ID: str = os.environ["AUTH0_CLIENT_ID"]
    AUTH0_CLIENT_SECRET: str = os.environ["AUTH0_CLIENT_SECRET"]
    AUTH0_CALLBACK_URL: str = os.environ["AUTH0_CALLBACK_URL"]

    STRIPE_SECRET_KEY: str = os.environ["STRIPE_SECRET_KEY"]

    PORTAL_RETURN_URL: str = os.environ["PORTAL_RETURN_URL"]

    # Stripe Billing Meter for usage tracking
    STRIPE_METER_EVENT_NAME: str = os.environ.get("STRIPE_METER_EVENT_NAME", "brushstrokes_used")

    # Credit packages (in cents) - maps to number of brushstrokes
    # Pricing: $0.02 per brushstroke
    CREDIT_PACKAGES = {
        500: 250,    # $5.00 = 250 brushstrokes
        1000: 500,   # $10.00 = 500 brushstrokes
        2000: 1000,  # $20.00 = 1,000 brushstrokes
    }

    # Default auto-recharge amount (in cents)
    DEFAULT_AUTO_RECHARGE_AMOUNT: int = 500  # $5
