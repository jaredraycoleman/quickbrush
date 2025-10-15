import os
from dotenv import load_dotenv
load_dotenv()

class Config:
    AUTH0_DOMAIN: str = os.environ["AUTH0_DOMAIN"]
    AUTH0_AUDIENCE: str = os.environ["AUTH0_AUDIENCE"]
    AUTH0_CLIENT_ID: str = os.environ["AUTH0_CLIENT_ID"]
    AUTH0_CLIENT_SECRET: str = os.environ["AUTH0_CLIENT_SECRET"]
    AUTH0_CALLBACK_URL: str = os.environ["AUTH0_CALLBACK_URL"]

    STRIPE_SECRET_KEY: str = os.environ["STRIPE_SECRET_KEY"]

    PORTAL_RETURN_URL: str = os.environ["PORTAL_RETURN_URL"]
    STRIPE_PRICE_ID: str = os.environ["STRIPE_PRICE_ID"]
