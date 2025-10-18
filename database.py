"""
MongoDB database connection and initialization.

This module handles connection to MongoDB (hosted on Digital Ocean)
and provides initialization utilities.
"""

from mongoengine import connect, disconnect
from config import Config
import logging

logger = logging.getLogger(__name__)

# Global flag to track if database is available
_db_available = False


def init_db():
    """
    Initialize MongoDB connection.

    Connects to MongoDB using the connection string from config.
    Returns True if connection successful, False otherwise.
    """
    global _db_available

    # Check if MONGODB_URI is configured
    if not Config.MONGODB_URI or Config.MONGODB_URI == "":
        logger.error("MONGODB_URI environment variable is not set!")
        logger.error("Please set the MONGODB_URI secret in Kubernetes")
        _db_available = False
        return False

    # Check if it's the default localhost (not configured properly)
    if "localhost" in Config.MONGODB_URI or "127.0.0.1" in Config.MONGODB_URI:
        logger.error("MONGODB_URI is set to localhost - please configure MongoDB Atlas URI")
        _db_available = False
        return False

    try:
        connect(
            db=Config.MONGODB_DB_NAME,
            host=Config.MONGODB_URI,
            uuidRepresentation='standard',
            serverSelectionTimeoutMS=5000,  # Fail fast - 5 second timeout
            connectTimeoutMS=5000,
        )
        logger.info(f"Successfully connected to MongoDB: {Config.MONGODB_DB_NAME}")
        _db_available = True
        return True
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        logger.error("Application will run in limited mode without database")
        _db_available = False
        return False


def is_db_available():
    """Check if database connection is available."""
    return _db_available


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
