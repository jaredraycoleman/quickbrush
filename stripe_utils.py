from stripe import StripeClient
from config import Config
import uuid
import time

client = StripeClient(api_key=Config.STRIPE_SECRET_KEY)


def get_or_create_customer(user: dict):
    """Get or create a Stripe Customer via client.v1.customers."""
    userinfo: dict = user.get("userinfo", {})
    auth0_sub = userinfo.get("sub")
    if not auth0_sub:
        raise ValueError("User info does not contain 'sub' field.")
    existing = client.v1.customers.search(
        params={"query": f"metadata['auth0_sub']:'{auth0_sub}'"}
    )
    if existing.data:
        return existing.data[0]

    email = userinfo.get("email")
    new_customer = client.v1.customers.create(
        params={
            "email": email,
            "metadata": {"auth0_sub": auth0_sub},
        }
    )
    return new_customer


def start_subscription(user):
    """Starts a subscription for the usage-based price via client.v1.checkout.sessions."""
    cust = get_or_create_customer(user)
    session = client.v1.checkout.sessions.create(
        params={
            "mode": "subscription",
            "customer": cust.id,
            "line_items": [
                {"price": Config.STRIPE_PRICE_ID, "quantity": 1}
            ],
            "success_url": Config.PORTAL_RETURN_URL + "?checkout=success",
            "cancel_url": Config.PORTAL_RETURN_URL + "?checkout=cancel",
        }
    )
    return session.url


def create_portal_session(user):
    """Creates a Stripe Customer Portal session via client.v1.billing_portal.sessions."""
    cust = get_or_create_customer(user)
    ps = client.v1.billing_portal.sessions.create(
        params={
            "customer": cust.id,
            "return_url": Config.PORTAL_RETURN_URL,
        }
    )
    return ps.url


def record_usage(customer_id: str, tokens_used: int):
    """
    Use client.raw_request (or client.v1) to record usage for a metered price.
    """
    try:
        resp = client.raw_request(
            "post",
            "/v1/billing/meter_events",
            params={
                "event_name": "image_generation",
                "payload[value]": tokens_used,
                "payload[stripe_customer_id]": customer_id,
                "identifier": str(uuid.uuid4()),
                "timestamp": int(time.time()),
            },
        )
        return resp
    except Exception as e:
        print("Error recording meter event:", e)
        return None
