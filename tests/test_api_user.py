"""
Tests for user information endpoint.
"""

import pytest
from fastapi import status
from unittest.mock import patch


class TestUserInfo:
    """Test /api/user endpoint."""

    def test_get_user_info_no_subscription(self, api_client, auth_headers, test_user):
        """Get user info for user without subscription."""
        with patch("api_routes.get_subscription_info") as mock_sub_info:
            mock_sub_info.return_value = (None, 0)

            response = api_client.get("/api/user", headers=auth_headers)
            assert response.status_code == status.HTTP_200_OK

            data = response.json()
            assert data["email"] == test_user.email
            assert data["subscription_tier"] == "free"
            assert data["subscription_status"] == "none"
            assert data["total_brushstrokes"] == test_user.purchased_brushstrokes
            assert data["subscription_allowance_remaining"] == 0
            assert data["purchased_brushstrokes"] == test_user.purchased_brushstrokes
            assert data["current_period_end"] is None

    def test_get_user_info_with_subscription(self, api_client, auth_headers, test_user):
        """Get user info for user with active subscription."""
        from datetime import datetime, timezone, timedelta

        period_end = datetime.now(timezone.utc) + timedelta(days=30)

        with patch("api_routes.get_subscription_info") as mock_sub_info:
            sub_dict = {
                "tier": "pro",
                "status": "active",
                "current_period_start": datetime.now(timezone.utc),
                "current_period_end": period_end,
                "cancel_at_period_end": False,
            }
            mock_sub_info.return_value = (sub_dict, 500)  # Pro tier: 500 brushstrokes

            response = api_client.get("/api/user", headers=auth_headers)
            assert response.status_code == status.HTTP_200_OK

            data = response.json()
            assert data["email"] == test_user.email
            assert data["subscription_tier"] == "pro"
            assert data["subscription_status"] == "active"
            assert data["subscription_allowance_remaining"] == 500
            assert data["total_brushstrokes"] == 500 + test_user.purchased_brushstrokes

    def test_get_user_info_with_used_allowance(self, api_client, auth_headers, test_user):
        """Get user info with partially used subscription allowance."""
        from datetime import datetime, timezone, timedelta
        from models import SubscriptionInfo

        # Set up subscription with used allowance
        test_user.subscription = SubscriptionInfo(
            stripe_subscription_id="sub_test",
            current_period_start=datetime.now(timezone.utc),
            allowance_used_this_period=150,
        )
        test_user.save()

        period_end = datetime.now(timezone.utc) + timedelta(days=30)

        with patch("api_routes.get_subscription_info") as mock_sub_info:
            sub_dict = {
                "tier": "pro",
                "status": "active",
                "current_period_start": datetime.now(timezone.utc),
                "current_period_end": period_end,
                "cancel_at_period_end": False,
            }
            mock_sub_info.return_value = (sub_dict, 500)  # Pro tier: 500 brushstrokes

            response = api_client.get("/api/user", headers=auth_headers)
            assert response.status_code == status.HTTP_200_OK

            data = response.json()
            # 500 - 150 used = 350 remaining from subscription
            assert data["subscription_allowance_remaining"] == 350
            # 350 (subscription remaining) + 100 (purchased) = 450 total
            assert data["total_brushstrokes"] == 450

    def test_get_user_info_unauthorized(self, api_client):
        """Get user info without authentication should fail."""
        response = api_client.get("/api/user")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
