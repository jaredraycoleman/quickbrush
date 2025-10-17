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

client = StripeClient(api_key=Config.STRIPE_SECRET_KEY)


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
    if user.stripe_customer_id:
        logger.info(f"Found existing Stripe customer for user {user.email}: {user.stripe_customer_id}")
        return user.stripe_customer_id

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
# SUBSCRIPTION MANAGEMENT
# ========================================

def create_subscription_checkout(user: User, price_id: str, success_url: str, cancel_url: str) -> Optional[str]:
    """
    Create a Stripe Checkout session for subscription signup.

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
                    "user_id": str(user.id),
                    "tier": tier_name,
                }
            }
        )

        logger.info(f"Created subscription checkout session for user {user.email}: {session.id}")
        return session.url

    except Exception as e:
        logger.error(f"Error creating subscription checkout: {e}")
        return None


def cancel_subscription(user: User) -> bool:
    """
    Cancel a user's subscription at period end.

    Args:
        user: User object from MongoDB

    Returns:
        True if successful, False otherwise
    """
    if not user.subscription or not user.subscription.stripe_subscription_id:
        logger.warning(f"User {user.email} has no active subscription to cancel")
        return False

    try:
        # Cancel at period end (so they keep access until end of billing period)
        client.v1.subscriptions.update(
            user.subscription.stripe_subscription_id,
            params={
                "cancel_at_period_end": True,
            }
        )

        # Update user record
        user.cancel_subscription()
        user.save()

        logger.info(f"Canceled subscription for user {user.email}: {user.subscription.stripe_subscription_id}")
        return True

    except Exception as e:
        logger.error(f"Error canceling subscription: {e}")
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
# WEBHOOK HANDLERS
# ========================================

def handle_checkout_completed(session_id: str) -> bool:
    """
    Handle checkout.session.completed webhook.

    This is called for both subscription signups and one-time pack purchases.

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
            # Subscription checkout - will be handled by subscription webhook
            logger.info(f"Subscription checkout completed for user {user.email}: {session_id}")
            return True

        elif session.mode == "payment":
            # One-time pack purchase
            brushstrokes = int(session.metadata.get("brushstrokes", 0))
            if brushstrokes <= 0:
                logger.error(f"Invalid brushstrokes in checkout session: {session_id}")
                return False

            # Add brushstrokes to user
            user.add_purchased_brushstrokes(brushstrokes)

            # Record transaction
            transaction = BrushstrokeTransaction(
                user=user,
                transaction_type=TransactionType.PURCHASE.value,
                amount=brushstrokes,
                balance_after=user.total_brushstrokes(),
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


def handle_subscription_created(subscription_id: str) -> bool:
    """
    Handle customer.subscription.created webhook.

    Args:
        subscription_id: Stripe subscription ID

    Returns:
        True if handled successfully, False otherwise
    """
    try:
        subscription = client.v1.subscriptions.retrieve(subscription_id)

        # Get user by customer ID
        customer_id = subscription.customer
        user = get_user_by_stripe_customer_id(customer_id)
        if not user:
            logger.error(f"User not found for subscription: {subscription_id}")
            return False

        # Get price ID and determine tier
        price_id = subscription.items.data[0].price.id
        tiers = Config.get_subscription_tiers()

        if price_id not in tiers:
            logger.error(f"Unknown subscription price_id: {price_id}")
            return False

        tier_name, allowance = tiers[price_id]
        tier = SubscriptionTier(tier_name)

        # Update user subscription
        user.update_subscription(
            tier=tier,
            stripe_subscription_id=subscription_id,
            stripe_price_id=price_id,
            current_period_start=datetime.fromtimestamp(subscription.current_period_start, tz=timezone.utc),
            current_period_end=datetime.fromtimestamp(subscription.current_period_end, tz=timezone.utc),
            status=SubscriptionStatus(subscription.status)
        )

        # Grant initial allowance
        transaction = BrushstrokeTransaction(
            user=user,
            transaction_type=TransactionType.SUBSCRIPTION_RENEWAL.value,
            amount=allowance,
            balance_after=user.total_brushstrokes(),
            stripe_subscription_id=subscription_id,
            subscription_period_start=user.subscription.current_period_start,
            subscription_period_end=user.subscription.current_period_end,
            description=f"Subscription created: {tier_name} ({allowance} brushstrokes/month)"
        )
        transaction.save()

        user.save()

        logger.info(f"Created subscription for user {user.email}: {tier_name}")
        return True

    except Exception as e:
        logger.error(f"Error handling subscription created: {e}")
        import traceback
        traceback.print_exc()
        return False


def handle_subscription_updated(subscription_id: str) -> bool:
    """
    Handle customer.subscription.updated webhook.

    This handles subscription changes (upgrades, downgrades, cancellations).

    Args:
        subscription_id: Stripe subscription ID

    Returns:
        True if handled successfully, False otherwise
    """
    try:
        subscription = client.v1.subscriptions.retrieve(subscription_id)

        # Get user by customer ID
        customer_id = subscription.customer
        user = get_user_by_stripe_customer_id(customer_id)
        if not user:
            logger.error(f"User not found for subscription: {subscription_id}")
            return False

        # Get price ID and determine tier
        price_id = subscription.items.data[0].price.id
        tiers = Config.get_subscription_tiers()

        if price_id not in tiers:
            logger.error(f"Unknown subscription price_id: {price_id}")
            return False

        tier_name, allowance = tiers[price_id]
        tier = SubscriptionTier(tier_name)

        # Update user subscription
        user.update_subscription(
            tier=tier,
            stripe_subscription_id=subscription_id,
            stripe_price_id=price_id,
            current_period_start=datetime.fromtimestamp(subscription.current_period_start, tz=timezone.utc),
            current_period_end=datetime.fromtimestamp(subscription.current_period_end, tz=timezone.utc),
            status=SubscriptionStatus(subscription.status)
        )

        if subscription.cancel_at_period_end:
            user.subscription.cancel_at_period_end = True

        user.save()

        logger.info(f"Updated subscription for user {user.email}: {tier_name} (status: {subscription.status})")
        return True

    except Exception as e:
        logger.error(f"Error handling subscription updated: {e}")
        import traceback
        traceback.print_exc()
        return False


def handle_subscription_deleted(subscription_id: str) -> bool:
    """
    Handle customer.subscription.deleted webhook.

    This is called when a subscription is canceled/expires.

    Args:
        subscription_id: Stripe subscription ID

    Returns:
        True if handled successfully, False otherwise
    """
    try:
        subscription = client.v1.subscriptions.retrieve(subscription_id)

        # Get user by customer ID
        customer_id = subscription.customer
        user = get_user_by_stripe_customer_id(customer_id)
        if not user:
            logger.error(f"User not found for subscription: {subscription_id}")
            return False

        # Cancel subscription
        user.cancel_subscription()
        user.save()

        logger.info(f"Deleted subscription for user {user.email}: {subscription_id}")
        return True

    except Exception as e:
        logger.error(f"Error handling subscription deleted: {e}")
        import traceback
        traceback.print_exc()
        return False


def handle_invoice_paid(invoice_id: str) -> bool:
    """
    Handle invoice.paid webhook.

    This is called when a subscription invoice is paid successfully.
    We use this to grant the monthly brushstroke allowance.

    Args:
        invoice_id: Stripe invoice ID

    Returns:
        True if handled successfully, False otherwise
    """
    try:
        invoice = client.v1.invoices.retrieve(invoice_id)

        # Skip if this is the first invoice (subscription creation handles that)
        if invoice.billing_reason == "subscription_create":
            logger.info(f"Skipping initial subscription invoice: {invoice_id}")
            return True

        # Only handle subscription renewals
        if invoice.billing_reason != "subscription_cycle":
            logger.info(f"Skipping non-renewal invoice: {invoice_id} (reason: {invoice.billing_reason})")
            return True

        # Get user by customer ID
        customer_id = invoice.customer
        user = get_user_by_stripe_customer_id(customer_id)
        if not user:
            logger.error(f"User not found for invoice: {invoice_id}")
            return False

        # Get subscription
        subscription_id = invoice.subscription
        if not subscription_id:
            logger.error(f"No subscription ID in invoice: {invoice_id}")
            return False

        subscription = client.v1.subscriptions.retrieve(subscription_id)

        # Get price ID and determine tier
        price_id = subscription.items.data[0].price.id
        tiers = Config.get_subscription_tiers()

        if price_id not in tiers:
            logger.error(f"Unknown subscription price_id: {price_id}")
            return False

        tier_name, allowance = tiers[price_id]

        # Reset subscription allowance
        if user.subscription:
            user.subscription.reset_allowance()
            user.subscription.current_period_start = datetime.fromtimestamp(subscription.current_period_start, tz=timezone.utc)
            user.subscription.current_period_end = datetime.fromtimestamp(subscription.current_period_end, tz=timezone.utc)

            # Record transaction
            transaction = BrushstrokeTransaction(
                user=user,
                transaction_type=TransactionType.SUBSCRIPTION_RENEWAL.value,
                amount=allowance,
                balance_after=user.total_brushstrokes(),
                stripe_subscription_id=subscription_id,
                subscription_period_start=user.subscription.current_period_start,
                subscription_period_end=user.subscription.current_period_end,
                description=f"Subscription renewed: {tier_name} ({allowance} brushstrokes/month)"
            )
            transaction.save()

            user.save()

            logger.info(f"Renewed subscription allowance for user {user.email}: {allowance} brushstrokes")
            return True
        else:
            logger.error(f"User {user.email} has no subscription record")
            return False

    except Exception as e:
        logger.error(f"Error handling invoice paid: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """
    Verify Stripe webhook signature.

    Args:
        payload: Raw request body
        signature: Stripe-Signature header value

    Returns:
        True if signature is valid, False otherwise
    """
    if not Config.STRIPE_WEBHOOK_SECRET:
        logger.warning("Stripe webhook secret not configured - skipping signature verification")
        return True

    try:
        import stripe
        stripe.Webhook.construct_event(
            payload, signature, Config.STRIPE_WEBHOOK_SECRET
        )
        return True
    except Exception as e:
        logger.error(f"Webhook signature verification failed: {e}")
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
    # Check if user has enough brushstrokes
    if user.total_brushstrokes() < brushstrokes_used:
        logger.warning(f"Insufficient brushstrokes for user {user.email}: {user.total_brushstrokes()} < {brushstrokes_used}")
        return False

    # Deduct brushstrokes
    success = user.use_brushstrokes(brushstrokes_used)
    if not success:
        return False

    # Record transaction
    from models import Generation
    generation = Generation.objects(id=generation_id).first() if generation_id else None

    transaction = BrushstrokeTransaction(
        user=user,
        transaction_type=TransactionType.USAGE.value,
        amount=-brushstrokes_used,  # Negative for usage
        balance_after=user.total_brushstrokes(),
        generation=generation,
        description=f"Image generation ({brushstrokes_used} brushstrokes)"
    )
    transaction.save()

    user.save()

    logger.info(f"Recorded generation for user {user.email}: {brushstrokes_used} brushstrokes used")
    return True
