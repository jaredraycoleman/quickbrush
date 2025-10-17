"""
Stripe integration for subscriptions and one-time purchases.

This module handles:
- Subscription management (Basic, Pro, Premium, Ultimate tiers)
- One-time brushstroke pack purchases
- Stripe customer creation and management
- Webhook handling for payment events
"""

from stripe import StripeClient
from config import Config
from models import (
    User, BrushstrokeTransaction, SubscriptionTier,
    SubscriptionStatus, TransactionType, get_user_by_stripe_customer_id
)
from datetime import datetime, timezone
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)
# set logging level to DEBUG for detailed output
logger.setLevel(logging.DEBUG)
# set logger to print to console
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

client = StripeClient(api_key=Config.STRIPE_SECRET_KEY)


# ========================================
# SUBSCRIPTION INFO FETCHING
# ========================================

def get_subscription_info(user: User) -> Tuple[Optional[dict], int]:
    """
    Get subscription info from Stripe (single source of truth).

    Returns tuple of (subscription_dict, allowance), or (None, 0) if no active subscription.

    Returns:
        subscription_dict: {
            "tier": str,  # "basic", "pro", etc.
            "status": str,  # "active", "past_due", etc.
            "current_period_start": datetime,
            "current_period_end": datetime,
            "cancel_at_period_end": bool,
        }
        allowance: int - monthly brushstroke allowance for this tier
    """
    subscription_id = getattr(user.subscription, 'stripe_subscription_id', None)
    if not user.subscription or not subscription_id:
        logger.info(f"No active subscription for user {user.email}")
        return None, 0

    try:
        sub_id = str(subscription_id)
        subscription = client.v1.subscriptions.retrieve(
            sub_id,
            params={"expand": ["items.data.price"]}
        )

        # Get subscription status
        status = getattr(subscription, 'status', 'active')

        # IMPORTANT: The subscription items might have been updated mid-period (e.g., downgrade)
        # But we need to give them the allowance for what they PAID FOR this period
        # So we look at the LATEST INVOICE to see what was actually charged

        # Get the latest invoice for this subscription to see what they paid for
        try:
            invoices = client.v1.invoices.list(params={"subscription": sub_id, "limit": 1})
            latest_invoice = list(invoices)[0] if invoices else None

            if latest_invoice:
                # Get invoice items (includes proration credits/charges)
                invoice_items = client.v1.invoice_items.list(params={"invoice": latest_invoice.id})

                # Get all price IDs from the invoice and find the highest tier
                tiers = Config.get_subscription_tiers()
                max_allowance = 0
                paid_price_id = None

                for item in invoice_items:
                    # Extract price ID from pricing field
                    pricing = getattr(item, 'pricing', None)
                    if pricing:
                        price_details = getattr(pricing, 'price_details', None)
                        if price_details:
                            price = getattr(price_details, 'price', None)
                            if price and str(price) in tiers:
                                # Check if this tier has higher allowance
                                _, allowance = tiers[str(price)]
                                if allowance > max_allowance:
                                    max_allowance = allowance
                                    paid_price_id = str(price)

                if not paid_price_id:
                    # Fallback to subscription items if we can't find invoice item
                    subscription_items = client.v1.subscription_items.list(params={"subscription": sub_id})
                    items_list = subscription_items
                    paid_price_id = str(items_list.data[0].price.id)
            else:
                # No invoice yet, use subscription items
                subscription_items = client.v1.subscription_items.list(params={"subscription": sub_id})
                items_list = subscription_items
                paid_price_id = str(items_list.data[0].price.id)
        except Exception as e:
            logger.warning(f"Could not fetch latest invoice: {e}, falling back to subscription items")
            subscription_items = client.v1.subscription_items.list(params={"subscription": sub_id})
            items_list = subscription_items
            paid_price_id = str(items_list.data[0].price.id)

        # Get tier and allowance from config based on what they PAID for
        tiers = Config.get_subscription_tiers()
        if paid_price_id not in tiers:
            logger.error(f"Unknown subscription price_id: {paid_price_id}")
            return None, 0

        current_tier_name, current_allowance = tiers[paid_price_id]

        # Get period dates
        current_period_start = getattr(subscription, 'current_period_start', None)
        current_period_end = getattr(subscription, 'current_period_end', None)
        cancel_at_period_end = getattr(subscription, 'cancel_at_period_end', False)

        if current_period_start:
            current_period_start = datetime.fromtimestamp(current_period_start, tz=timezone.utc)
        if current_period_end:
            current_period_end = datetime.fromtimestamp(current_period_end, tz=timezone.utc)

        sub_dict = {
            "tier": current_tier_name,
            "status": status,
            "current_period_start": current_period_start,
            "current_period_end": current_period_end,
            "cancel_at_period_end": cancel_at_period_end,
        }

        # IMPORTANT: Return the CURRENT allowance, not the scheduled one
        # This is what the user has access to RIGHT NOW for this billing period
        return sub_dict, current_allowance

    except Exception as e:
        logger.error(f"Error fetching subscription info from Stripe: {e}")
        import traceback
        traceback.print_exc()
        return None, 0


# ========================================
# CUSTOMER MANAGEMENT
# ========================================

def get_or_create_stripe_customer(user: User) -> str:
    """
    Get or create a Stripe customer for a user.

    This replaces the previous approach of searching Stripe by metadata.
    Now we store the customer ID in MongoDB and create it only when needed.

    Args:
        user: User object from MongoDB

    Returns:
        Stripe customer ID
    """
    # If user already has a customer ID, return it
    stripe_customer_id = getattr(user, 'stripe_customer_id', None)
    if stripe_customer_id:
        logger.info(f"Found existing Stripe customer for user {user.email}: {stripe_customer_id}")
        return stripe_customer_id

    # Create new Stripe customer
    try:
        customer = client.v1.customers.create(
            params={
                "email": user.email,
                "name": user.name,
                "metadata": {
                    "user_id": str(user.id),
                    "auth0_sub": user.auth0_sub,
                }
            }
        )

        # Save customer ID to user
        user.stripe_customer_id = customer.id
        user.save()

        logger.info(f"Created new Stripe customer for user {user.email}: {customer.id}")
        return customer.id

    except Exception as e:
        logger.error(f"Error creating Stripe customer: {e}")
        raise


def create_portal_session(user: User) -> str:
    """
    Create a Stripe Customer Portal session for managing subscriptions and billing.

    Args:
        user: User object from MongoDB

    Returns:
        Customer portal URL
    """
    customer_id = get_or_create_stripe_customer(user)

    try:
        portal_session = client.v1.billing_portal.sessions.create(
            params={
                "customer": customer_id,
                "return_url": Config.PORTAL_RETURN_URL,
            }
        )
        return portal_session.url
    except Exception as e:
        logger.error(f"Error creating portal session: {e}")
        raise

# ========================================
# ONE-TIME PURCHASE MANAGEMENT
# ========================================

def create_pack_checkout(user: User, price_id: str, success_url: str, cancel_url: str) -> Optional[str]:
    """
    Create a Stripe Checkout session for one-time brushstroke pack purchase.

    Args:
        user: User object from MongoDB
        price_id: Stripe price ID for the brushstroke pack
        success_url: URL to redirect after successful payment
        cancel_url: URL to redirect if user cancels

    Returns:
        Checkout session URL, or None if error
    """
    customer_id = get_or_create_stripe_customer(user)

    try:
        # Validate price_id is a valid pack
        packs = Config.get_brushstroke_packs()
        if price_id not in packs:
            logger.error(f"Invalid pack price_id: {price_id}")
            return None

        amount_cents, brushstrokes = packs[price_id]

        session = client.v1.checkout.sessions.create(
            params={
                "customer": customer_id,
                "payment_method_types": ["card"],
                "line_items": [
                    {
                        "price": price_id,
                        "quantity": 1,
                    }
                ],
                "mode": "payment",
                "success_url": success_url,
                "cancel_url": cancel_url,
                "metadata": {
                    "user_id": str(user.id),
                    "brushstrokes": str(brushstrokes),
                    "purchase_type": "pack",
                }
            }
        )

        logger.info(f"Created pack checkout session for user {user.email}: {session.id}")
        return session.url

    except Exception as e:
        logger.error(f"Error creating pack checkout: {e}")
        return None


# ========================================
# CHECKOUT HANDLERS
# ========================================

def handle_checkout_completed(session_id: str) -> bool:
    """
    Handle checkout completion (both subscriptions and one-time purchases).

    This is called from the success page redirect after checkout.

    Args:
        session_id: Stripe checkout session ID

    Returns:
        True if handled successfully, False otherwise
    """
    try:
        session = client.v1.checkout.sessions.retrieve(session_id)

        if session.payment_status != "paid":
            logger.warning(f"Checkout session {session_id} not paid yet")
            return False

        # Get user
        user_id = session.metadata.get("user_id")
        if not user_id:
            logger.error(f"No user_id in checkout session metadata: {session_id}")
            return False

        from models import User
        user = User.objects(id=user_id).first()
        if not user:
            logger.error(f"User not found for checkout session: {session_id}")
            return False

        # Check if it's a subscription or one-time purchase
        if session.mode == "subscription":
            # Subscription checkout - set up the subscription
            subscription_id = session.subscription
            if not subscription_id:
                logger.error(f"No subscription ID in session: {session_id}")
                return False

            # Retrieve subscription with expand parameter to get all fields
            subscription = client.v1.subscriptions.retrieve(
                subscription_id,
                params={"expand": ["items.data.price"]}
            )

            # Get price ID and determine tier
            # In Stripe SDK v13+, we need to list subscription items separately
            subscription_items = client.v1.subscription_items.list(params={"subscription": subscription_id})
            # Convert to list to access first item
            items_list = list(subscription_items)
            price_id = items_list[0].price.id
            tiers = Config.get_subscription_tiers()

            if price_id not in tiers:
                logger.error(f"Unknown subscription price_id: {price_id}")
                return False

            tier_name, allowance = tiers[price_id]

            # Get period start
            current_period_start = getattr(subscription, 'current_period_start', None)
            if current_period_start:
                current_period_start = datetime.fromtimestamp(current_period_start, tz=timezone.utc)
            else:
                current_period_start = datetime.now(timezone.utc)

            # Set subscription ID in user record (simplified - no redundant data)
            user.set_subscription_id(subscription_id, current_period_start)
            user.save()

            # Note: We don't "grant" allowance - it's calculated on-demand from Stripe
            # Just log the subscription creation
            logger.info(f"Created subscription for user {user.email}: {tier_name} ({allowance} brushstrokes/month)")
            return True

        elif session.mode == "payment":
            # One-time pack purchase
            brushstrokes = int(session.metadata.get("brushstrokes", 0))
            if brushstrokes <= 0:
                logger.error(f"Invalid brushstrokes in checkout session: {session_id}")
                return False

            # Add brushstrokes to user
            user.add_purchased_brushstrokes(brushstrokes)

            # Get subscription allowance to calculate total balance
            subscription_info_tuple = get_subscription_info(user)
            allowance = subscription_info_tuple[1] if subscription_info_tuple else 0

            # Record transaction
            transaction = BrushstrokeTransaction(
                user=user,
                transaction_type=TransactionType.PURCHASE.value,
                amount=brushstrokes,
                balance_after=user.total_brushstrokes(allowance),
                stripe_payment_intent_id=session.payment_intent,
                amount_paid_cents=session.amount_total,
                description=f"Purchased {brushstrokes} brushstroke pack"
            )
            transaction.save()

            user.save()

            logger.info(f"Added {brushstrokes} brushstrokes to user {user.email} from checkout {session_id}")
            return True

        else:
            logger.warning(f"Unknown checkout mode: {session.mode}")
            return False

    except Exception as e:
        logger.error(f"Error handling checkout completed: {e}")
        import traceback
        traceback.print_exc()
        return False




# ========================================
# SUBSCRIPTION RENEWAL CHECK
# ========================================

def check_and_renew_subscription(user: User) -> bool:
    """
    Check if a user's subscription needs renewal and process it.

    This replaces the webhook-based renewal system. Called when:
    - User logs in
    - User generates an image
    - User checks their balance

    Args:
        user: User object from MongoDB

    Returns:
        True if subscription was renewed, False otherwise
    """
    if not user.subscription or not user.subscription.stripe_subscription_id:
        return False

    # Fetch subscription from Stripe to check if period has changed
    try:
        subscription = client.v1.subscriptions.retrieve(
            user.subscription.stripe_subscription_id,
            params={"expand": ["items.data.price"]}
        )

        # Check subscription status
        subscription_status = getattr(subscription, 'status', 'active')
        if subscription_status not in ["active", "trialing"]:
            # Subscription is no longer active - clear it
            logger.info(f"Subscription {subscription.id} is no longer active (status: {subscription_status})")
            user.clear_subscription()
            user.save()
            return False

        # Get current period start from Stripe
        stripe_period_start = getattr(subscription, 'current_period_start', None)
        if not stripe_period_start:
            return False

        stripe_period_start_dt = datetime.fromtimestamp(stripe_period_start, tz=timezone.utc)

        # Compare with stored period start
        stored_period_start = user.subscription.current_period_start
        if stored_period_start and stored_period_start.tzinfo is None:
            stored_period_start = stored_period_start.replace(tzinfo=timezone.utc)

        # If periods match, no renewal needed
        if stored_period_start and stored_period_start == stripe_period_start_dt:
            return False

        # Period has changed! Reset the allowance
        # Get the tier and allowance
        subscription_items = client.v1.subscription_items.list(params={"subscription": user.subscription.stripe_subscription_id})
        items_list = list(subscription_items)
        price_id = items_list[0].price.id
        tiers = Config.get_subscription_tiers()

        if price_id not in tiers:
            logger.error(f"Unknown subscription price_id: {price_id}")
            return False

        tier_name, allowance = tiers[price_id]

        # Reset the allowance for the new period
        user.subscription.reset_allowance(stripe_period_start_dt)
        user.save()

        logger.info(f"Renewed subscription for user {user.email}: {tier_name} ({allowance} brushstrokes/month)")
        return True

    except Exception as e:
        logger.error(f"Error checking subscription renewal: {e}")
        import traceback
        traceback.print_exc()
        return False


# ========================================
# USAGE TRACKING
# ========================================

def record_generation(user: User, brushstrokes_used: int, generation_id: str = None) -> bool:
    """
    Record image generation and deduct brushstrokes.

    Args:
        user: User object from MongoDB
        brushstrokes_used: Number of brushstrokes to deduct
        generation_id: Optional generation record ID

    Returns:
        True if successful, False if insufficient balance
    """
    # Get subscription allowance from Stripe
    subscription_info_tuple = get_subscription_info(user)
    allowance = subscription_info_tuple[1] if subscription_info_tuple else 0

    # Check if user has enough brushstrokes
    total_available = user.total_brushstrokes(allowance)
    if total_available < brushstrokes_used:
        logger.warning(f"Insufficient brushstrokes for user {user.email}: {total_available} < {brushstrokes_used}")
        return False

    # Deduct brushstrokes
    success = user.use_brushstrokes(brushstrokes_used, allowance)
    if not success:
        return False

    # Record transaction
    from models import Generation
    generation = Generation.objects(id=generation_id).first() if generation_id else None

    transaction = BrushstrokeTransaction(
        user=user,
        transaction_type=TransactionType.USAGE.value,
        amount=-brushstrokes_used,  # Negative for usage
        balance_after=user.total_brushstrokes(allowance),
        generation=generation,
        description=f"Image generation ({brushstrokes_used} brushstrokes)"
    )
    transaction.save()

    user.save()

    logger.info(f"Recorded generation for user {user.email}: {brushstrokes_used} brushstrokes used")
    return True
