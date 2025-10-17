"""
Tests for image retrieval endpoints.
"""

import pytest
from fastapi import status


class TestImageRetrieval:
    """Test /api/image/{id} and /api/generations endpoints."""

    def test_get_image_success(self, api_client, auth_headers, sample_generation):
        """Successfully retrieve an image."""
        generation_id = str(sample_generation.id)

        response = api_client.get(f"/api/image/{generation_id}", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.headers["content-type"] == "image/webp"
        assert len(response.content) > 0  # Image data is present

    def test_get_image_not_found(self, api_client, auth_headers):
        """Request for non-existent image should return 404."""
        fake_id = "000000000000000000000000"

        response = api_client.get(f"/api/image/{fake_id}", headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert "not found" in data["detail"].lower()

    def test_get_image_unauthorized(self, api_client, sample_generation):
        """Get image without authentication should fail."""
        generation_id = str(sample_generation.id)

        response = api_client.get(f"/api/image/{generation_id}")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_image_wrong_user(self, api_client, auth_headers, sample_generation, mock_mongo):
        """User cannot access another user's image."""
        from models import User, Generation

        # Create another user
        other_user = User(
            auth0_sub="other_user_123",
            email="other@example.com",
            name="Other User",
        )
        other_user.save()

        # Create generation for other user
        webp_data = b'RIFF$\x00\x00\x00WEBPVP8'
        other_generation = Generation(
            user=other_user,
            generation_type="character",
            quality="medium",
            user_text="Test",
            image_data=webp_data,
            image_size="1024x1024",
            brushstrokes_used=3,
            status="completed",
            source="api",
        )
        other_generation.save()

        generation_id = str(other_generation.id)

        # Try to access with current user's credentials
        response = api_client.get(f"/api/image/{generation_id}", headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_list_generations_empty(self, api_client, auth_headers, test_user):
        """List generations when user has none."""
        response = api_client.get("/api/generations", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["generations"] == []
        assert data["total"] == 0
        assert data["limit"] == 10
        assert data["offset"] == 0

    def test_list_generations_with_data(self, api_client, auth_headers, test_user):
        """List generations with sample data."""
        from models import Generation

        # Create multiple generations
        for i in range(5):
            Generation(
                user=test_user,
                generation_type="character",
                quality="medium",
                user_text=f"Test {i}",
                image_data=b"fake_data",
                image_size="1024x1024",
                brushstrokes_used=3,
                status="completed",
                source="api",
            ).save()

        response = api_client.get("/api/generations", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert len(data["generations"]) == 5
        assert data["total"] == 5

        # Verify generation structure
        gen = data["generations"][0]
        assert "id" in gen
        assert "generation_type" in gen
        assert "quality" in gen
        assert "user_text" in gen
        assert "image_url" in gen
        assert gen["image_url"].startswith("/api/image/")
        assert "brushstrokes_used" in gen
        assert "status" in gen
        assert "created_at" in gen

    def test_list_generations_pagination(self, api_client, auth_headers, test_user):
        """Test pagination of generations list."""
        from models import Generation

        # Create 15 generations
        for i in range(15):
            Generation(
                user=test_user,
                generation_type="character",
                quality="low",
                user_text=f"Test {i}",
                image_data=b"fake_data",
                image_size="1024x1024",
                brushstrokes_used=1,
                status="completed",
                source="api",
            ).save()

        # Test first page
        response = api_client.get("/api/generations?limit=10&offset=0", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["generations"]) == 10
        assert data["total"] == 15

        # Test second page
        response = api_client.get("/api/generations?limit=10&offset=10", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["generations"]) == 5
        assert data["total"] == 15

    def test_list_generations_limit_max(self, api_client, auth_headers, test_user):
        """Test that limit is capped at 100."""
        from models import Generation

        # Create 150 generations
        for i in range(150):
            Generation(
                user=test_user,
                generation_type="character",
                quality="low",
                user_text=f"Test {i}",
                image_data=b"fake_data",
                image_size="1024x1024",
                brushstrokes_used=1,
                status="completed",
                source="api",
            ).save()

        response = api_client.get("/api/generations?limit=200", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Should return only 100 (the max with images stored)
        assert len(data["generations"]) <= 100

    def test_list_generations_only_with_images(self, api_client, auth_headers, test_user):
        """List should only include generations with image data."""
        from models import Generation

        # Create generations with images
        for i in range(3):
            Generation(
                user=test_user,
                generation_type="character",
                quality="low",
                user_text=f"With image {i}",
                image_data=b"fake_data",
                image_size="1024x1024",
                brushstrokes_used=1,
                status="completed",
                source="api",
            ).save()

        # Create generations without images (old/deleted)
        for i in range(2):
            Generation(
                user=test_user,
                generation_type="character",
                quality="low",
                user_text=f"No image {i}",
                image_data=None,  # No image data
                image_size="1024x1024",
                brushstrokes_used=1,
                status="completed",
                source="api",
            ).save()

        response = api_client.get("/api/generations", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Should only return the 3 with images
        assert len(data["generations"]) == 3
        assert data["total"] == 3

    def test_list_generations_ordered_by_date(self, api_client, auth_headers, test_user):
        """Generations should be ordered by most recent first."""
        from models import Generation
        from datetime import datetime, timezone, timedelta

        # Create generations with different timestamps
        base_time = datetime.now(timezone.utc)

        generations = []
        for i in range(3):
            gen = Generation(
                user=test_user,
                generation_type="character",
                quality="low",
                user_text=f"Test {i}",
                image_data=b"fake_data",
                image_size="1024x1024",
                brushstrokes_used=1,
                status="completed",
                source="api",
                created_at=base_time - timedelta(hours=i),
            )
            gen.save()
            generations.append(gen)

        response = api_client.get("/api/generations", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Most recent should be first
        assert len(data["generations"]) == 3

        # Verify ordering (newest first)
        timestamps = [gen["created_at"] for gen in data["generations"]]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_list_generations_unauthorized(self, api_client):
        """List generations without authentication should fail."""
        response = api_client.get("/api/generations")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
