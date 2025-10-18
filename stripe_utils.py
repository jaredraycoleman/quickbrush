"""
Stripe integration for subscriptions and one-time purchases.

This module handles:
- Subscription management (Basic, Pro, Premium, Ultimate tiers) using Subscription Schedules
- One-time brushstroke pack purchases
- Stripe customer creation and management
- Subscription plan changes (upgrades/downgrades) with proper prorating
- NO webhooks - all state is pulled from Stripe on-demand

Key Design Decisions:
- Uses Subscription Schedules for plan changes to ensure users get what they paid for
- When users change plans, a schedule is created with 2 phases:
  Phase 1: Current plan until end of billing period
  Phase 2: New plan starting next period
- This avoids complex invoice parsing and proration calculations
- Stripe as single source of truth - state is fetched when needed (login, generation, etc.)
"""

from stripe import StripeClient
from config import Config
from models import User, BrushstrokeTransaction, TransactionType
from datetime import datetime, timezone
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)

client = StripeClient(api_key=Config.STRIPE_SECRET_KEY)

# ========================================
# SUBSCRIPTION SCHEDULE HELPERS
# ========================================

def get_subscription_schedule(subscription_id: str) -> Optional[any]:
    """
    Get the subscription schedule for a subscription if it exists.

    Args:
        subscription_id: Stripe subscription ID

    Returns:
        Subscription schedule object or None if no schedule exists
    """
    try:
        # Retrieve the subscription to get its schedule ID
        subscription = client.v1.subscriptions.retrieve(subscription_id)
        schedule_id = getattr(subscription, 'schedule', None)

        if not schedule_id:
            return None

        # Retrieve the schedule
        schedule = client.v1.subscription_schedules.retrieve(str(schedule_id))
        return schedule
    except Exception as e:
        logger.warning(f"Error fetching subscription schedule: {e}")
        return None


def get_current_phase_price(subscription_id: str) -> Optional[str]:
    """
    Get the current phase's price ID from subscription schedule.

    This is used to determine what tier the user is currently on,
    especially important when they've scheduled a plan change.

    Args:
        subscription_id: Stripe subscription ID

    Returns:
        Price ID for the current phase, or None if no schedule
    """
    schedule = get_subscription_schedule(subscription_id)
    if not schedule:
        return None

    try:
        # Get phases from schedule
        phases = getattr(schedule, 'phases', None)
        if not phases:
            return None

        # Find the current phase (first phase that hasn't ended yet)
        import time
        current_time = int(time.time())

        for phase in phases:
            start_date = getattr(phase, 'start_date', 0)
            end_date = getattr(phase, 'end_date', None)

            # Check if we're in this phase
            if start_date <= current_time and (end_date is None or current_time < end_date):
                # Get the first item's price from this phase
                items = getattr(phase, 'items', None)
                if items and len(items) > 0:
                    price = getattr(items[0], 'price', None)
                    return str(price) if price else None

        return None
    except Exception as e:
        logger.warning(f"Error extracting current phase price: {e}")
        return None


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
            "scheduled_change": None,  # Not used with simple proration model
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

        # Get current subscription items
        subscription_items = client.v1.subscription_items.list(params={"subscription": sub_id})
        price_id = str(subscription_items.data[0].price.id)

        # Get tier and allowance from config
        tiers = Config.get_subscription_tiers()
        if price_id not in tiers:
            logger.error(f"Unknown subscription price_id: {price_id}")
            return None, 0

        current_tier_name, current_allowance = tiers[price_id]

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
            "scheduled_change": None,  # We use immediate proration, not scheduled changes
        }

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
                "email": str(user.email),
                "name": str(user.name),
                "metadata": {
                    "user_id": str(user.id), # type: ignore
                    "auth0_sub": str(user.auth0_sub),
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
# SUBSCRIPTION PLAN CHANGES
# ========================================

def change_subscription_plan(user: User, new_price_id: str) -> bool:
    """
    Change a user's subscription plan immediately with prorated billing.

    This updates the subscription in Stripe with proration enabled.
    - Upgrades: Customer is charged prorated amount immediately
    - Downgrades: Customer receives credit applied to next invoice

    Args:
        user: User object from MongoDB
        new_price_id: Stripe price ID for the new plan

    Returns:
        True if successful, False otherwise
    """
    subscription_id = getattr(user.subscription, 'stripe_subscription_id', None)
    if not subscription_id:
        logger.error(f"No subscription found for user {user.email}")
        return False

    # Validate new price_id
    tiers = Config.get_subscription_tiers()
    if new_price_id not in tiers:
        logger.error(f"Invalid subscription price_id: {new_price_id}")
        return False

    try:
        sub_id = str(subscription_id)

        # Get current subscription items
        subscription_items = client.v1.subscription_items.list(params={"subscription": sub_id})
        current_price_id = str(subscription_items.data[0].price.id)
        subscription_item_id = str(subscription_items.data[0].id)

        # Check if they're trying to change to the same plan
        if current_price_id == new_price_id:
            logger.info(f"User {user.email} already on plan {new_price_id}")
            return True

        # Update the subscription item with the new price
        # This will prorate automatically
        client.v1.subscription_items.update(
            subscription_item_id,
            params={"price": new_price_id}
        )

        # Reset the user's allowance usage since they're changing plans
        # They'll get the new plan's allowance immediately
        user.subscription.allowance_used_this_period = 0  # type: ignore
        user.save()

        logger.info(f"Updated plan for user {user.email}: {current_price_id} -> {new_price_id}")
        return True

    except Exception as e:
        logger.error(f"Error changing subscription plan: {e}")
        import traceback
        traceback.print_exc()
        return False


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
                    "user_id": str(user.id), # type: ignore
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


def create_subscription_checkout(user: User, price_id: str, success_url: str, cancel_url: str) -> Optional[str]:
    """
    Create a Stripe Checkout session for subscription purchase.

    Args:
        user: User object from MongoDB
        price_id: Stripe price ID for the subscription tier
        success_url: URL to redirect after successful payment
        cancel_url: URL to redirect if user cancels

    Returns:
        Checkout session URL, or None if error
    """
    customer_id = get_or_create_stripe_customer(user)

    try:
        # Validate price_id is a valid subscription tier
        tiers = Config.get_subscription_tiers()
        if price_id not in tiers:
            logger.error(f"Invalid subscription price_id: {price_id}")
            return None

        tier_name, allowance = tiers[price_id]

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
                "mode": "subscription",
                "success_url": success_url,
                "cancel_url": cancel_url,
                "metadata": {
                    "user_id": str(user.id), # type: ignore
                    "tier": tier_name,
                    "allowance": str(allowance),
                    "purchase_type": "subscription",
                }
            }
        )

        logger.info(f"Created subscription checkout session for user {user.email}: {tier_name}")
        return session.url

    except Exception as e:
        logger.error(f"Error creating subscription checkout: {e}")
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

        if not session.metadata:
            logger.error(f"No metadata in checkout session: {session_id}")
            return False

        # Get user
        user_id = session.metadata.get("user_id")
        if not user_id:
            logger.error(f"No user_id in checkout session metadata: {session_id}")
            return False

        from models import User
        user = User.objects(id=user_id).first() # type: ignore
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
                str(subscription_id),
                params={"expand": ["items.data.price"]}
            )

            # Get price ID and determine tier
            # In Stripe SDK v13+, we need to list subscription items separately
            subscription_items = client.v1.subscription_items.list(params={"subscription": str(subscription_id)})
            # Convert to list to access first item
            items_list = subscription_items
            price_id = items_list.data[0].price.id
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
    if not user.subscription or not user.subscription.stripe_subscription_id: # type: ignore
        return False

    # Fetch subscription from Stripe to check if period has changed
    try:
        sub_id = str(user.subscription.stripe_subscription_id) # type: ignore
        subscription = client.v1.subscriptions.retrieve(
            sub_id,
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
        stored_period_start = user.subscription.current_period_start # type: ignore
        if stored_period_start and stored_period_start.tzinfo is None: # type: ignore
            stored_period_start = stored_period_start.replace(tzinfo=timezone.utc) # type: ignore

        # If periods match, no renewal needed
        if stored_period_start and stored_period_start == stripe_period_start_dt:
            return False

        # Period has changed! Reset the allowance
        subscription_items = client.v1.subscription_items.list(params={"subscription": sub_id})
        price_id = str(subscription_items.data[0].price.id)

        tiers = Config.get_subscription_tiers()
        if price_id not in tiers:
            logger.error(f"Unknown subscription price_id: {price_id}")
            return False

        tier_name, allowance = tiers[price_id]

        # Reset the allowance for the new period
        user.subscription.reset_allowance(stripe_period_start_dt) # type: ignore
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

def record_generation(user: User, brushstrokes_used: int, generation_id: str | None = None) -> bool:
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
    generation = Generation.objects(id=generation_id).first() if generation_id else None # type: ignore

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
