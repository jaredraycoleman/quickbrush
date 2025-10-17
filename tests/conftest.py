"""
Pytest configuration and fixtures for Quickbrush API tests.
"""

import pytest
import mongomock
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
import os

# Set test environment variables before importing app modules
os.environ["TESTING"] = "1"
os.environ["MONGODB_URI"] = "mongodb://localhost:27017/quickbrush_test"
os.environ["STRIPE_SECRET_KEY"] = "sk_test_mock"
os.environ["OPENAI_API_KEY"] = "sk-test-mock"
os.environ["AUTH0_DOMAIN"] = "test.auth0.com"
os.environ["AUTH0_CLIENT_ID"] = "test_client_id"
os.environ["AUTH0_CLIENT_SECRET"] = "test_client_secret"


@pytest.fixture(scope="function")
def mock_mongo():
    """Mock MongoDB connection using mongomock."""
    with patch("mongoengine.connect") as mock_connect:
        mock_connect.return_value = mongomock.MongoClient()
        yield mock_connect


@pytest.fixture(scope="function")
def test_user(mock_mongo):
    """Create a test user."""
    from models import User

    user = User(
        auth0_sub="test_user_123",
        email="test@example.com",
        name="Test User",
        purchased_brushstrokes=100,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    user.save()
    return user


@pytest.fixture(scope="function")
def test_api_key(test_user):
    """Create a test API key."""
    from models import APIKey
    from datetime import timedelta

    key_id = "qb_test_key_123"
    secret = "test_secret_456"

    api_key = APIKey(
        user=test_user,
        key_id=key_id,
        key_hash=APIKey.hash_key(secret),
        key_prefix=secret[:8],
        name="Test API Key",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    api_key.save()

    # Return both the API key object and the full key string
    return {
        "api_key": api_key,
        "full_key": f"{key_id}:{secret}",
        "key_id": key_id,
        "secret": secret,
    }


@pytest.fixture(scope="function")
def api_client(mock_mongo):
    """Create FastAPI test client."""
    from api_routes import api

    return TestClient(api)


@pytest.fixture(scope="function")
def auth_headers(test_api_key):
    """Get authorization headers for API requests."""
    return {"Authorization": f"Bearer {test_api_key['full_key']}"}


@pytest.fixture(scope="function")
def mock_stripe():
    """Mock Stripe API calls."""
    with patch("stripe_utils.client") as mock_client:
        # Mock subscription retrieval
        mock_subscription = Mock()
        mock_subscription.status = "active"
        mock_subscription.current_period_start = int(datetime.now(timezone.utc).timestamp())
        mock_subscription.current_period_end = int(datetime.now(timezone.utc).timestamp()) + 2592000  # 30 days
        mock_subscription.cancel_at_period_end = False

        mock_price = Mock()
        mock_price.id = "price_basic"

        mock_item = Mock()
        mock_item.price = mock_price

        mock_subscription.items = Mock()
        mock_subscription.items.data = [mock_item]

        mock_client.v1.subscriptions.retrieve.return_value = mock_subscription

        yield mock_client


@pytest.fixture(scope="function")
def mock_openai():
    """Mock OpenAI API calls."""
    with patch("maker.client") as mock_client:
        # Mock chat completion for description generation
        mock_chat_response = Mock()
        mock_chat_response.choices = [Mock()]
        mock_chat_response.choices[0].message = Mock()
        mock_chat_response.choices[0].message.content = "A detailed test description"

        mock_client.chat.completions.create.return_value = mock_chat_response

        # Mock image generation
        mock_image_response = Mock()
        mock_image_response.data = [Mock()]

        # Create a simple 1x1 PNG image in base64
        import base64
        simple_png = base64.b64encode(
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x00\x01'
            b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        ).decode()

        mock_image_response.data[0].b64_json = simple_png

        mock_client.images.generate.return_value = mock_image_response
        mock_client.images.edit.return_value = mock_image_response

        yield mock_client


@pytest.fixture(scope="function")
def sample_generation(test_user):
    """Create a sample generation record."""
    from models import Generation

    # Simple WebP image data (1x1 pixel)
    webp_data = (
        b'RIFF$\x00\x00\x00WEBPVP8 \x18\x00\x00\x000\x01\x00'
        b'\x9d\x01*\x01\x00\x01\x00\x01@%\xa4\x00\x03p\x00\xfe\xfb\x94\x00\x00'
    )

    generation = Generation(
        user=test_user,
        generation_type="character",
        quality="medium",
        user_text="A brave knight",
        user_prompt="",
        refined_description="A detailed description of a brave knight",
        image_size="1024x1024",
        image_data=webp_data,
        image_format="webp",
        brushstrokes_used=3,
        status="completed",
        source="api",
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    generation.save()
    return generation


@pytest.fixture(autouse=True)
def cleanup_db(mock_mongo):
    """Clean up database after each test."""
    yield
    # Cleanup code here if needed
    from mongoengine import connection
    try:
        connection.disconnect()
    except:
        pass
