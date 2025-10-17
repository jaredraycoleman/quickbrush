"""
Tests for API authentication.
"""

import pytest
from fastapi import status


class TestAuthentication:
    """Test API authentication and authorization."""

    def test_health_check_no_auth(self, api_client):
        """Health check endpoint should not require authentication."""
        response = api_client.get("/api/health")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "quickbrush-api"

    def test_missing_authorization_header(self, api_client):
        """Requests without Authorization header should be rejected."""
        response = api_client.get("/api/user")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        data = response.json()
        assert "authorization" in data["detail"].lower()

    def test_invalid_api_key_format(self, api_client):
        """Invalid API key format should be rejected."""
        response = api_client.get(
            "/api/user",
            headers={"Authorization": "Bearer invalid_key"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_nonexistent_api_key(self, api_client, mock_mongo):
        """Non-existent API key should be rejected."""
        response = api_client.get(
            "/api/user",
            headers={"Authorization": "Bearer qb_fake:fake_secret"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_inactive_api_key(self, api_client, test_user, mock_mongo):
        """Inactive API key should be rejected."""
        from models import APIKey

        # Create inactive API key
        key_id = "qb_inactive"
        secret = "inactive_secret"
        api_key = APIKey(
            user=test_user,
            key_id=key_id,
            key_hash=APIKey.hash_key(secret),
            key_prefix=secret[:8],
            name="Inactive Key",
            is_active=False,
        )
        api_key.save()

        response = api_client.get(
            "/api/user",
            headers={"Authorization": f"Bearer {key_id}:{secret}"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_valid_api_key(self, api_client, auth_headers, test_user, mock_stripe):
        """Valid API key should authenticate successfully."""
        response = api_client.get("/api/user", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["email"] == test_user.email

    def test_api_key_usage_tracking(self, api_client, auth_headers, test_api_key, mock_stripe):
        """API key usage should be tracked."""
        api_key_obj = test_api_key["api_key"]
        initial_requests = api_key_obj.total_requests

        response = api_client.get("/api/user", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK

        # Reload from database
        api_key_obj.reload()
        assert api_key_obj.total_requests == initial_requests + 1
        assert api_key_obj.last_used_at is not None
