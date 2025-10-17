"""
Account management service.

This module handles account deletion and cleanup operations.
"""

from models import User, APIKey, Generation, BrushstrokeTransaction, Log
from stripe import StripeClient
from config import Config
import logging
import pathlib

logger = logging.getLogger(__name__)

client = StripeClient(api_key=Config.STRIPE_SECRET_KEY)


def delete_user_account(user: User, delete_stripe_customer: bool = True) -> tuple[bool, str]:
    """
    Delete a user account and all associated data.

    This performs the following cleanup:
    1. Deletes all API keys
    2. Deletes all generation records
    3. Deletes all transaction records
    4. Deletes all log entries
    5. Cancels Stripe subscription (if exists)
    6. Deletes Stripe customer (optional)
    7. Deletes generated images from disk
    8. Deletes the user record

    Args:
        user: User object to delete
        delete_stripe_customer: Whether to delete the Stripe customer (default True)

    Returns:
        tuple: (success: bool, message: str)
    """
    user_email = user.email
    user_id = str(user.id) # type: ignore

    logger.info(f"Starting account deletion for user: {user_email}")

    try:
        # Step 1: Handle Stripe subscription and customer
        if user.stripe_customer_id:
            try:
                # Cancel active subscription if exists
                if user.subscription and user.subscription.stripe_subscription_id: # type: ignore
                    logger.info(f"Canceling subscription: {user.subscription.stripe_subscription_id}") # type: ignore
                    try:
                        client.v1.subscriptions.cancel(user.subscription.stripe_subscription_id) # type: ignore
                        logger.info(f"Successfully canceled subscription")
                    except Exception as e:
                        logger.warning(f"Failed to cancel subscription: {e}")
                        # Continue with deletion even if cancellation fails

                # Delete Stripe customer if requested
                if delete_stripe_customer:
                    logger.info(f"Deleting Stripe customer: {user.stripe_customer_id}")
                    try:
                        client.v1.customers.delete(user.stripe_customer_id) # type: ignore
                        logger.info(f"Successfully deleted Stripe customer")
                    except Exception as e:
                        logger.warning(f"Failed to delete Stripe customer: {e}")
                        # Continue with deletion even if Stripe deletion fails

            except Exception as e:
                logger.error(f"Error handling Stripe cleanup: {e}")
                # Continue with deletion even if Stripe operations fail

        # Step 2: Count images (stored in MongoDB, will be deleted with generations)
        try:
            images_count = Generation.objects(user=user, image_data__ne=None).count() # type: ignore
            logger.info(f"User has {images_count} images stored in MongoDB")
        except Exception as e:
            logger.error(f"Error counting images: {e}")
            images_count = 0

        # Step 3: Delete API keys
        try:
            api_keys_count = APIKey.objects(user=user).count() # type: ignore
            APIKey.objects(user=user).delete() # type: ignore
            logger.info(f"Deleted {api_keys_count} API keys")
        except Exception as e:
            logger.error(f"Error deleting API keys: {e}")
            return False, f"Failed to delete API keys: {str(e)}"

        # Step 4: Delete generation records
        try:
            generations_count = Generation.objects(user=user).count() # type: ignore
            Generation.objects(user=user).delete() # type: ignore
            logger.info(f"Deleted {generations_count} generation records")
        except Exception as e:
            logger.error(f"Error deleting generations: {e}")
            return False, f"Failed to delete generation records: {str(e)}"

        # Step 5: Delete transaction records
        try:
            transactions_count = BrushstrokeTransaction.objects(user=user).count() # type: ignore
            BrushstrokeTransaction.objects(user=user).delete() # type: ignore
            logger.info(f"Deleted {transactions_count} transaction records")
        except Exception as e:
            logger.error(f"Error deleting transactions: {e}")
            return False, f"Failed to delete transaction records: {str(e)}"

        # Step 6: Delete log entries
        logs_count = 0
        try:
            logs_count = Log.objects(user=user).count() # type: ignore
            Log.objects(user=user).delete() # type: ignore
            logger.info(f"Deleted {logs_count} log entries")
        except Exception as e:
            logger.warning(f"Error deleting logs: {e}")
            # Continue even if log deletion fails

        # Step 7: Delete the user record itself
        try:
            user.delete()
            logger.info(f"Successfully deleted user account: {user_email}")
        except Exception as e:
            logger.error(f"Error deleting user record: {e}")
            return False, f"Failed to delete user account: {str(e)}"

        # Success!
        summary = (
            f"Account deleted successfully. "
            f"Removed {api_keys_count} API keys, {generations_count} generations ({images_count} with images), "
            f"{transactions_count} transactions, and {logs_count} log entries."
        )
        logger.info(summary)
        return True, summary

    except Exception as e:
        logger.error(f"Unexpected error during account deletion: {e}")
        import traceback
        traceback.print_exc()
        return False, f"Unexpected error during account deletion: {str(e)}"


def get_account_deletion_summary(user: User) -> dict:
    """
    Get a summary of what will be deleted when account is deleted.

    Args:
        user: User object

    Returns:
        dict with counts of all data that will be deleted
    """
    try:
        summary = {
            "api_keys": APIKey.objects(user=user).count(), # type: ignore
            "generations": Generation.objects(user=user).count(), # type: ignore
            "transactions": BrushstrokeTransaction.objects(user=user).count(), # type: ignore
            "logs": Log.objects(user=user).count(), # type: ignore
            "has_subscription": bool(user.subscription and user.subscription.stripe_subscription_id), # type: ignore
            "has_stripe_customer": bool(user.stripe_customer_id),
            "purchased_brushstrokes": user.purchased_brushstrokes,
        }
        return summary
    except Exception as e:
        logger.error(f"Error getting account deletion summary: {e}")
        return {
            "api_keys": 0,
            "generations": 0,
            "transactions": 0,
            "logs": 0,
            "has_subscription": False,
            "has_stripe_customer": False,
            "purchased_brushstrokes": 0,
        }
