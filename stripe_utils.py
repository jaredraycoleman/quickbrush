from stripe import StripeClient
from config import Config
import uuid
import time
from typing import Optional

client = StripeClient(api_key=Config.STRIPE_SECRET_KEY)


def get_or_create_customer(user: dict):
    """Get or create a Stripe Customer via client.v1.customers."""
    userinfo = user.get("userinfo", {})
    if "sub" not in userinfo or "email" not in userinfo:
        raise ValueError("User info must contain 'sub' and 'email' fields.")
    auth0_sub = str(userinfo["sub"])
    email = str(userinfo["email"])
    if not auth0_sub:
        raise ValueError("User info does not contain 'sub' field.")

    existing = client.v1.customers.search(
        params={"query": f"metadata['auth0_sub']:'{auth0_sub}'"}
    )
    if existing.data:
        print(f"Found existing customer for auth0_sub {auth0_sub}")
        return existing.data[0]

    new_customer = client.v1.customers.create(
        params={
            "email": email,
            "metadata": {
                "auth0_sub": auth0_sub,
                "auto_recharge_enabled": "true",
                "auto_recharge_amount": str(Config.DEFAULT_AUTO_RECHARGE_AMOUNT),
            },
        }
    )
    return new_customer


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


# ========================================
# CREDITS-BASED BILLING FUNCTIONS
# ========================================


def get_credits_balance(customer_id: str) -> int:
    """
    Get the current credits balance for a customer using Stripe Billing credit grants.
    Returns the balance as an integer (number of brushstrokes).
    Automatically excludes expired credits.
    """
    try:
        # Get all active credit grants and sum their amounts
        grants = client.v1.billing.credit_grants.list(
            params={"customer": customer_id}
        )

        total_balance = 0
        current_time = int(time.time())

        for grant in grants.data:
            # Only count non-expired grants
            if grant.expires_at and grant.expires_at > current_time:
                # Check if grant has been voided or fully used
                if hasattr(grant, 'effective_at') and grant.effective_at:
                    # Get the amount from the grant
                    if hasattr(grant, 'amount') and grant.amount:
                        if grant.amount.get('type') == 'monetary' and grant.amount.get('monetary'):
                            grant_amount = grant.amount['monetary'].get('value', 0)

                            # Subtract any amount that's been applied
                            amount_used = 0
                            if hasattr(grant, 'amount_used') and grant.amount_used:
                                if grant.amount_used.get('type') == 'monetary' and grant.amount_used.get('monetary'):
                                    amount_used = grant.amount_used['monetary'].get('value', 0)

                            remaining = grant_amount - amount_used
                            total_balance += remaining
                            print(f"[Credits] Grant {grant.id}: {grant_amount} total, {amount_used} used, {remaining} remaining")

        print(f"[Credits] Total balance for {customer_id}: {total_balance} brushstrokes")
        return total_balance
    except Exception as e:
        print(f"Error fetching credits balance: {e}")
        import traceback
        traceback.print_exc()
        return 0


def add_credits(customer_id: str, amount: int, expires_in_days: int = 30) -> int:
    """
    Add credits to a customer's balance using Stripe Billing credit grants.
    Credits will expire after the specified number of days (default: 30 days from purchase).

    Args:
        customer_id: The Stripe customer ID
        amount: Number of brushstrokes to add
        expires_in_days: Days until credits expire (default: 30)

    Returns:
        The new total balance.
    """
    try:
        # Calculate expiration timestamp (30 days from now)
        expires_at = int(time.time()) + (expires_in_days * 24 * 60 * 60)

        # Create a credit grant
        # We use monetary credits where 1 cent = 1 brushstroke
        credit_grant = client.v1.billing.credit_grants.create(
            params={
                "customer": customer_id,
                "amount": {
                    "type": "monetary",
                    "monetary": {
                        "currency": "usd",
                        "value": amount,  # brushstrokes (1 brushstroke = 1 cent)
                    }
                },
                "applicability_config": {
                    "scope": {
                        "price_type": "metered",  # Can be used for metered billing
                    }
                },
                "expires_at": expires_at,
                "name": f"Brushstrokes Purchase - {amount} credits",
                "category": "paid",
            }
        )

        new_balance = get_credits_balance(customer_id)

        # Calculate expiration date for logging
        from datetime import datetime, timezone
        expiry_date = datetime.fromtimestamp(expires_at, tz=timezone.utc).strftime('%Y-%m-%d')

        print(f"[Credits] Added {amount} brushstrokes to {customer_id}. New balance: {new_balance}. Expires: {expiry_date}")
        return new_balance

    except Exception as e:
        print(f"Error adding credits: {e}")
        # Fall back to current balance
        return get_credits_balance(customer_id)


def deduct_credits(customer_id: str, amount: int) -> bool:
    """
    Deduct credits from a customer's balance using Stripe Billing.
    Automatically deducts from the oldest (soonest to expire) credits first.

    Returns True if successful, False if insufficient credits.
    """
    current_balance = get_credits_balance(customer_id)
    if current_balance < amount:
        print(f"[Credits] Insufficient balance: {current_balance} < {amount}")
        return False

    try:
        # Create a credit balance transaction to deduct credits
        transaction = client.v1.billing.credit_balance_transactions.create(
            params={
                "customer": customer_id,
                "type": "credits_applied",
                "credit_amount": {
                    "type": "monetary",
                    "monetary": {
                        "currency": "usd",
                        "value": amount,
                    }
                },
                "description": f"Image generation: {amount} brushstrokes",
            }
        )

        new_balance = get_credits_balance(customer_id)
        print(f"[Credits] Deducted {amount} brushstrokes from {customer_id}. New balance: {new_balance}")
        return True

    except Exception as e:
        print(f"Error deducting credits: {e}")
        return False


def get_credit_grants(customer_id: str) -> list:
    """
    Get a list of all active credit grants for a customer.
    Returns a list of dicts with 'amount', 'expires_at', and 'name' for each grant.
    """
    try:
        grants = client.v1.billing.credit_grants.list(
            params={"customer": customer_id}
        )

        active_grants = []
        from datetime import datetime, timezone

        for grant in grants.data:
            # Only include grants that haven't expired
            if grant.expires_at and grant.expires_at > int(time.time()):
                amount = 0
                if hasattr(grant, 'amount') and grant.amount:
                    if grant.amount.get('type') == 'monetary' and grant.amount.get('monetary'):
                        amount = grant.amount['monetary'].get('value', 0)

                expiry_date = datetime.fromtimestamp(grant.expires_at, tz=timezone.utc)

                active_grants.append({
                    'amount': amount,
                    'expires_at': grant.expires_at,
                    'expires_date': expiry_date.strftime('%Y-%m-%d'),
                    'name': grant.name or 'Credit Grant',
                })

        # Sort by expiration date (soonest first)
        active_grants.sort(key=lambda x: x['expires_at'])
        return active_grants

    except Exception as e:
        print(f"Error fetching credit grants: {e}")
        return []


def record_meter_event(customer_id: str, brushstrokes_used: int):
    """
    Send a meter event to Stripe Billing for usage tracking.
    This is separate from the credits balance and is used for analytics/reporting.
    """
    try:
        # Create a unique idempotency key to prevent duplicate events
        idempotency_key = f"{customer_id}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

        event = client.v1.billing.meter_events.create(
            params={
                "event_name": Config.STRIPE_METER_EVENT_NAME,
                "payload": {
                    "stripe_customer_id": customer_id,
                    "value": str(brushstrokes_used),
                },
                "timestamp": int(time.time()),
            },
            options={
                "idempotency_key": idempotency_key,
            }
        )

        print(f"[Meter] Recorded {brushstrokes_used} brushstrokes for customer {customer_id}")
        return event
    except Exception as e:
        print(f"Error recording meter event: {e}")
        return None


def record_usage(customer_id: str, brushstrokes_used: int) -> bool:
    """
    Record usage by:
    1. Deducting credits from the customer's balance
    2. Sending a meter event to Stripe for tracking
    3. Triggering auto-recharge if balance is 0 or negative

    Returns True if successful, False if insufficient credits.
    """
    # Check if we need to auto-recharge
    balance = get_credits_balance(customer_id)
    if balance <= 0:
        try_auto_recharge(customer_id)

    # First, deduct credits
    success = deduct_credits(customer_id, brushstrokes_used)
    if not success:
        return False

    # Send meter event for analytics
    record_meter_event(customer_id, brushstrokes_used)

    # Check if we need to auto-recharge
    balance = get_credits_balance(customer_id)
    if balance <= 0:
        try_auto_recharge(customer_id)

    return True


# ========================================
# AUTO-RECHARGE FUNCTIONS
# ========================================


def get_auto_recharge_settings(customer_id: str) -> dict:
    """
    Get auto-recharge settings for a customer.
    Returns a dict with 'enabled' (bool) and 'amount' (int in cents).
    """
    try:
        customer = client.v1.customers.retrieve(customer_id)
        enabled = (customer.metadata or {}).get("auto_recharge_enabled", "true").lower() == "true"
        amount = int((customer.metadata or {}).get("auto_recharge_amount", Config.DEFAULT_AUTO_RECHARGE_AMOUNT))
        return {
            "enabled": enabled,
            "amount": amount,
        }
    except Exception as e:
        print(f"Error fetching auto-recharge settings: {e}")
        return {
            "enabled": True,
            "amount": Config.DEFAULT_AUTO_RECHARGE_AMOUNT,
        }


def set_auto_recharge_settings(customer_id: str, enabled: bool, amount: Optional[int] = None) -> bool:
    """
    Update auto-recharge settings for a customer.
    """
    try:
        metadata = {
            "auto_recharge_enabled": "true" if enabled else "false",
        }
        if amount is not None:
            # Validate that the amount is one of the allowed packages
            if amount not in Config.CREDIT_PACKAGES:
                raise ValueError(f"Invalid recharge amount: {amount}. Must be one of {list(Config.CREDIT_PACKAGES.keys())}")
            metadata["auto_recharge_amount"] = str(amount)

        client.v1.customers.update(
            customer_id,
            params={"metadata": metadata}
        )
        print(f"[Auto-Recharge] Updated settings for {customer_id}: enabled={enabled}, amount={amount}")
        return True
    except Exception as e:
        print(f"Error updating auto-recharge settings: {e}")
        return False


def try_auto_recharge(customer_id: str) -> bool:
    """
    Attempt to auto-recharge a customer's account if they have auto-recharge enabled.
    Returns True if recharge was successful, False otherwise.
    """
    settings = get_auto_recharge_settings(customer_id)
    if not settings["enabled"]:
        print(f"[Auto-Recharge] Not enabled for {customer_id}")
        return False

    amount_cents = settings["amount"]
    return purchase_credits(customer_id, amount_cents, auto_recharge=True)


# ========================================
# CREDIT PURCHASE FUNCTIONS
# ========================================


def purchase_credits(customer_id: str, amount_cents: int, auto_recharge: bool = False) -> bool:
    """
    Purchase credits for a customer by creating a payment intent.

    Args:
        customer_id: The Stripe customer ID
        amount_cents: The amount to charge in cents ($5 = 500, $10 = 1000, $20 = 2000)
        auto_recharge: Whether this is an automatic recharge (for logging purposes)

    Returns:
        True if successful, False otherwise
    """
    try:
        # Validate amount
        if amount_cents not in Config.CREDIT_PACKAGES:
            raise ValueError(f"Invalid amount: {amount_cents}. Must be one of {list(Config.CREDIT_PACKAGES.keys())}")

        brushstrokes = Config.CREDIT_PACKAGES[amount_cents]

        # Create a payment intent
        payment_intent = client.v1.payment_intents.create(
            params={
                "amount": amount_cents,
                "currency": "usd",
                "customer": customer_id,
                "confirm": True,
                "automatic_payment_methods": {
                    "enabled": True,
                    "allow_redirects": "never",
                },
                "description": f"{'Auto-recharge' if auto_recharge else 'Purchase'}: {brushstrokes} brushstrokes",
                "metadata": {
                    "brushstrokes": str(brushstrokes),
                    "auto_recharge": str(auto_recharge),
                },
            }
        )

        # Check if payment was successful
        if payment_intent.status == "succeeded":
            # Add credits to the customer's balance
            new_balance = add_credits(customer_id, brushstrokes)
            print(f"[Purchase] {'Auto-recharged' if auto_recharge else 'Purchased'} {brushstrokes} brushstrokes for {customer_id}. New balance: {new_balance}")
            return True
        elif payment_intent.status == "requires_action":
            print(f"[Purchase] Payment requires additional action: {payment_intent.next_action}")
            return False
        else:
            print(f"[Purchase] Payment failed with status: {payment_intent.status}")
            return False

    except Exception as e:
        print(f"Error purchasing credits: {e}")
        return False


def create_checkout_session(customer_id: str, amount_cents: int, success_url: str, cancel_url: str) -> Optional[str]:
    """
    Create a Stripe Checkout session for purchasing credits.
    This provides a hosted payment page for the customer.

    Returns the checkout session URL if successful, None otherwise.
    """
    try:
        # Validate amount
        if amount_cents not in Config.CREDIT_PACKAGES:
            raise ValueError(f"Invalid amount: {amount_cents}. Must be one of {list(Config.CREDIT_PACKAGES.keys())}")

        brushstrokes = Config.CREDIT_PACKAGES[amount_cents]

        # Create a checkout session
        session = client.v1.checkout.sessions.create(
            params={
                "customer": customer_id,
                "payment_method_types": ["card"],
                "line_items": [
                    {
                        "price_data": {
                            "currency": "usd",
                            "unit_amount": amount_cents,
                            "product_data": {
                                "name": f"{brushstrokes} Brushstrokes",
                                "description": f"Credit package: {brushstrokes} brushstrokes for image generation",
                            },
                        },
                        "quantity": 1,
                    }
                ],
                "mode": "payment",
                "success_url": success_url,
                "cancel_url": cancel_url,
                "metadata": {
                    "brushstrokes": str(brushstrokes),
                    "customer_id": customer_id,
                },
            }
        )

        print(f"[Checkout] Created session for {brushstrokes} brushstrokes: {session.id}")
        return session.url
    except Exception as e:
        print(f"Error creating checkout session: {e}")
        return None


def handle_checkout_webhook(session_id: str) -> bool:
    """
    Handle a successful checkout session webhook by adding credits to the customer.
    This should be called from your webhook endpoint when you receive a
    'checkout.session.completed' event from Stripe.

    Returns True if credits were added successfully.
    """
    try:
        session = client.v1.checkout.sessions.retrieve(session_id)

        if session.payment_status != "paid":
            print(f"[Webhook] Session {session_id} not paid yet")
            return False

        customer_id = session.customer
        if not customer_id:
            print(f"[Webhook] No customer ID found in session {session_id}")
            return False
        brushstrokes = int((session.metadata or {}).get("brushstrokes", 0))

        if brushstrokes > 0:
            new_balance = add_credits(customer_id, brushstrokes)
            print(f"[Webhook] Added {brushstrokes} brushstrokes to {customer_id}. New balance: {new_balance}")
            return True
        else:
            print(f"[Webhook] No brushstrokes metadata found in session {session_id}")
            return False

    except Exception as e:
        print(f"Error handling checkout webhook: {e}")
        return False


# ========================================
# LEGACY COMPATIBILITY (for migration)
# ========================================


def get_current_usage(customer_id: str) -> int:
    """
    Legacy function for backwards compatibility.
    Now returns the total brushstrokes used (inverse of credits balance).
    """
    # This is no longer tracked the same way, but we can estimate
    # based on meter events if needed
    return 0


def get_current_cost(customer_id: str) -> float:
    """
    Legacy function for backwards compatibility.
    Returns 0.0 since we're now using a prepaid credits model.
    """
    return 0.0
