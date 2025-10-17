"""
MongoDB database connection and initialization.

This module handles connection to MongoDB (hosted on Digital Ocean)
and provides initialization utilities.
"""

from mongoengine import connect, disconnect
from config import Config
import logging

logger = logging.getLogger(__name__)


def init_db():
    """
    Initialize MongoDB connection.

    Connects to MongoDB using the connection string from config.
    """
    try:
        connect(
            db=Config.MONGODB_DB_NAME,
            host=Config.MONGODB_URI,
            uuidRepresentation='standard',
        )
        logger.info(f"Successfully connected to MongoDB: {Config.MONGODB_DB_NAME}")
        return True
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise


def close_db():
    """Close MongoDB connection."""
    try:
        disconnect()
        logger.info("MongoDB connection closed")
    except Exception as e:
        logger.error(f"Error closing MongoDB connection: {e}")


def test_connection():
    """
    Test MongoDB connection by attempting a simple query.

    Returns True if connection is successful, False otherwise.
    """
    try:
        from models import User
        # Try to count users (will work even if collection is empty)
        User.objects.count() # type: ignore
        logger.info("MongoDB connection test successful")
        return True
    except Exception as e:
        logger.error(f"MongoDB connection test failed: {e}")
        return False
