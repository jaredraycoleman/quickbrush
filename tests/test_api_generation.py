"""
Tests for image generation endpoint.
"""

import pytest
from fastapi import status
from unittest.mock import patch, Mock


class TestImageGeneration:
    """Test /api/generate endpoint."""

    def test_generate_image_success(self, api_client, auth_headers, test_user, mock_openai):
        """Successfully generate an image."""
        with patch("generation_service.get_subscription_info") as mock_sub_info, \
             patch("generation_service.record_generation") as mock_record:

            mock_sub_info.return_value = (None, 0)
            mock_record.return_value = True

            request_data = {
                "text": "A brave knight with silver armor",
                "prompt": "Fantasy RPG character",
                "generation_type": "character",
                "quality": "medium",
                "size": "1024x1024"
            }

            response = api_client.post("/api/generate", json=request_data, headers=auth_headers)

            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            assert data["success"] is True
            assert "generation_id" in data
            assert data["image_url"].startswith("/api/image/")
            assert data["refined_description"]
            assert data["brushstrokes_used"] == 3  # medium quality
            assert data["brushstrokes_remaining"] == test_user.purchased_brushstrokes - 3
            assert "remaining_image_slots" in data
            assert data["message"] == "Image generated successfully"

    def test_generate_image_insufficient_brushstrokes(self, api_client, auth_headers, test_user):
        """Generation should fail with insufficient brushstrokes."""
        # Set user to have 0 brushstrokes
        test_user.purchased_brushstrokes = 0
        test_user.save()

        with patch("generation_service.get_subscription_info") as mock_sub_info:
            mock_sub_info.return_value = (None, 0)

            request_data = {
                "text": "A brave knight",
                "generation_type": "character",
                "quality": "medium",
                "size": "1024x1024"
            }

            response = api_client.post("/api/generate", json=request_data, headers=auth_headers)

            assert response.status_code == status.HTTP_402_PAYMENT_REQUIRED
            data = response.json()
            assert "insufficient" in data["detail"].lower()

    def test_generate_image_all_generation_types(self, api_client, auth_headers, test_user, mock_openai):
        """Test all generation types (character, scene, creature, item)."""
        generation_types = ["character", "scene", "creature", "item"]

        with patch("generation_service.get_subscription_info") as mock_sub_info, \
             patch("generation_service.record_generation") as mock_record:

            mock_sub_info.return_value = (None, 0)
            mock_record.return_value = True

            for gen_type in generation_types:
                request_data = {
                    "text": f"A test {gen_type}",
                    "generation_type": gen_type,
                    "quality": "low",
                    "size": "1024x1024"
                }

                response = api_client.post("/api/generate", json=request_data, headers=auth_headers)
                assert response.status_code == status.HTTP_200_OK, f"Failed for {gen_type}"
                data = response.json()
                assert data["success"] is True

    def test_generate_image_all_quality_levels(self, api_client, auth_headers, test_user, mock_openai):
        """Test all quality levels and their costs."""
        quality_costs = {
            "low": 1,
            "medium": 3,
            "high": 5
        }

        with patch("generation_service.get_subscription_info") as mock_sub_info, \
             patch("generation_service.record_generation") as mock_record:

            mock_sub_info.return_value = (None, 0)
            mock_record.return_value = True

            for quality, expected_cost in quality_costs.items():
                request_data = {
                    "text": "A brave knight",
                    "generation_type": "character",
                    "quality": quality,
                    "size": "1024x1024"
                }

                response = api_client.post("/api/generate", json=request_data, headers=auth_headers)
                assert response.status_code == status.HTTP_200_OK, f"Failed for {quality}"
                data = response.json()
                assert data["brushstrokes_used"] == expected_cost

    def test_generate_image_with_subscription(self, api_client, auth_headers, test_user, mock_openai):
        """Generate image using subscription allowance."""
        from datetime import datetime, timezone
        from models import SubscriptionInfo

        # Set up subscription
        test_user.subscription = SubscriptionInfo(
            stripe_subscription_id="sub_test",
            current_period_start=datetime.now(timezone.utc),
            allowance_used_this_period=0,
        )
        test_user.save()

        with patch("generation_service.get_subscription_info") as mock_sub_info, \
             patch("generation_service.record_generation") as mock_record:

            sub_dict = {
                "tier": "pro",
                "status": "active",
                "current_period_start": datetime.now(timezone.utc),
                "current_period_end": datetime.now(timezone.utc),
                "cancel_at_period_end": False,
            }
            mock_sub_info.return_value = (sub_dict, 500)  # 500 brushstrokes
            mock_record.return_value = True

            request_data = {
                "text": "A brave knight",
                "generation_type": "character",
                "quality": "high",  # 5 brushstrokes
                "size": "1024x1024"
            }

            response = api_client.post("/api/generate", json=request_data, headers=auth_headers)
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            # Should have 495 from subscription + 100 purchased = 595 remaining
            assert data["brushstrokes_remaining"] > 500

    def test_generate_image_invalid_generation_type(self, api_client, auth_headers):
        """Invalid generation type should be rejected."""
        request_data = {
            "text": "A brave knight",
            "generation_type": "invalid_type",
            "quality": "medium",
            "size": "1024x1024"
        }

        response = api_client.post("/api/generate", json=request_data, headers=auth_headers)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_generate_image_missing_required_fields(self, api_client, auth_headers):
        """Request missing required fields should be rejected."""
        request_data = {
            "generation_type": "character",
            "quality": "medium"
            # Missing 'text' field
        }

        response = api_client.post("/api/generate", json=request_data, headers=auth_headers)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_generate_image_with_prompt(self, api_client, auth_headers, test_user, mock_openai):
        """Generate image with additional prompt."""
        with patch("generation_service.get_subscription_info") as mock_sub_info, \
             patch("generation_service.record_generation") as mock_record:

            mock_sub_info.return_value = (None, 0)
            mock_record.return_value = True

            request_data = {
                "text": "A brave knight",
                "prompt": "wearing golden armor in sunset light",
                "generation_type": "character",
                "quality": "medium",
                "size": "1024x1024"
            }

            response = api_client.post("/api/generate", json=request_data, headers=auth_headers)
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["success"] is True

    def test_generate_image_unauthorized(self, api_client):
        """Generation without authentication should fail."""
        request_data = {
            "text": "A brave knight",
            "generation_type": "character",
            "quality": "medium",
            "size": "1024x1024"
        }

        response = api_client.post("/api/generate", json=request_data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_generate_image_openai_error(self, api_client, auth_headers, test_user):
        """Handle OpenAI API errors gracefully."""
        with patch("generation_service.get_subscription_info") as mock_sub_info, \
             patch("maker.client") as mock_openai:

            mock_sub_info.return_value = (None, 0)

            # Mock OpenAI error
            mock_openai.chat.completions.create.side_effect = Exception("OpenAI API error")

            request_data = {
                "text": "A brave knight",
                "generation_type": "character",
                "quality": "medium",
                "size": "1024x1024"
            }

            response = api_client.post("/api/generate", json=request_data, headers=auth_headers)
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            data = response.json()
            assert "error" in data["detail"].lower() or "failed" in data["detail"].lower()
