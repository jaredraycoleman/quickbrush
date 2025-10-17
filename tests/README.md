# Quickbrush API Tests

Comprehensive test suite for the Quickbrush API endpoints.

## Setup

### 1. Install Test Dependencies

```bash
pip install -r requirements-test.txt
```

### 2. Environment Setup

The tests use a separate test database and mock external services (Stripe, OpenAI, Auth0).

Environment variables are automatically set in `conftest.py` for testing.

## Running Tests

### Run All Tests

```bash
pytest
```

### Run Specific Test File

```bash
pytest tests/test_api_auth.py
pytest tests/test_api_generation.py
pytest tests/test_api_images.py
pytest tests/test_api_user.py
```

### Run Specific Test Class

```bash
pytest tests/test_api_auth.py::TestAuthentication
```

### Run Specific Test

```bash
pytest tests/test_api_auth.py::TestAuthentication::test_valid_api_key
```

### Run with Coverage

```bash
pytest --cov=. --cov-report=html --cov-report=term-missing
```

View coverage report: `open htmlcov/index.html`

### Run with Verbose Output

```bash
pytest -v
```

### Run Only Fast Tests (exclude slow tests)

```bash
pytest -m "not slow"
```

## Test Structure

```
tests/
├── __init__.py
├── conftest.py              # Shared fixtures and configuration
├── test_api_auth.py         # Authentication tests
├── test_api_user.py         # User info endpoint tests
├── test_api_generation.py   # Image generation tests
├── test_api_images.py       # Image retrieval tests
└── README.md                # This file
```

## Test Categories

### Authentication Tests (`test_api_auth.py`)

- ✅ Health check (no auth required)
- ✅ Missing authorization header
- ✅ Invalid API key format
- ✅ Non-existent API key
- ✅ Inactive API key
- ✅ Valid API key authentication
- ✅ API key usage tracking

### User Info Tests (`test_api_user.py`)

- ✅ Get user info without subscription
- ✅ Get user info with active subscription
- ✅ Get user info with partially used allowance
- ✅ Unauthorized access

### Image Generation Tests (`test_api_generation.py`)

- ✅ Successful image generation
- ✅ Insufficient brushstrokes error
- ✅ All generation types (character, scene, creature, item)
- ✅ All quality levels (low, medium, high) and costs
- ✅ Generation with subscription allowance
- ✅ Invalid generation type
- ✅ Missing required fields
- ✅ Generation with additional prompt
- ✅ 100-image limit enforcement
- ✅ Unauthorized access
- ✅ OpenAI API error handling

### Image Retrieval Tests (`test_api_images.py`)

- ✅ Successfully retrieve an image
- ✅ Image not found error
- ✅ Unauthorized access
- ✅ Access control (users can't access other users' images)
- ✅ List generations (empty)
- ✅ List generations with data
- ✅ Pagination
- ✅ Maximum limit enforcement
- ✅ Only show generations with images
- ✅ Ordered by date (newest first)
- ✅ Unauthorized list access

## Fixtures

### Core Fixtures

- `mock_mongo` - Mocks MongoDB using mongomock
- `test_user` - Creates a test user with 100 brushstrokes
- `test_api_key` - Creates a test API key for the test user
- `api_client` - FastAPI test client
- `auth_headers` - Pre-configured authorization headers

### Mock Fixtures

- `mock_stripe` - Mocks Stripe API calls
- `mock_openai` - Mocks OpenAI API calls (image generation)

### Data Fixtures

- `sample_generation` - Creates a sample image generation record

## Writing New Tests

### Basic Test Structure

```python
from fastapi import status

class TestMyFeature:
    """Test description."""

    def test_something(self, api_client, auth_headers):
        """Test something specific."""
        response = api_client.get("/api/endpoint", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["field"] == "expected_value"
```

### Using Mocks

```python
from unittest.mock import patch

def test_with_mock(self, api_client, auth_headers):
    """Test with mocked external service."""
    with patch("module.function") as mock_fn:
        mock_fn.return_value = "mocked_value"

        response = api_client.get("/api/endpoint", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        mock_fn.assert_called_once()
```

### Testing Error Cases

```python
def test_error_case(self, api_client, auth_headers):
    """Test error handling."""
    response = api_client.post("/api/endpoint", json={"invalid": "data"}, headers=auth_headers)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert "error" in data["detail"].lower()
```

## Continuous Integration

To run tests in CI/CD pipeline:

```yaml
# Example GitHub Actions workflow
- name: Run tests
  run: |
    pip install -r requirements.txt
    pip install -r requirements-test.txt
    pytest --cov=. --cov-report=xml

- name: Upload coverage
  uses: codecov/codecov-action@v3
```

## Best Practices

1. **Isolation** - Each test should be independent
2. **Clarity** - Test names should describe what they test
3. **Mocking** - Mock external services (Stripe, OpenAI, etc.)
4. **Coverage** - Aim for >80% code coverage
5. **Speed** - Keep tests fast; mark slow tests with `@pytest.mark.slow`
6. **Assertions** - Use specific assertions, not just `assert True`

## Troubleshooting

### MongoDB Connection Errors

Tests use mongomock, so no real MongoDB connection is needed.

### Import Errors

Make sure you're running pytest from the project root:

```bash
cd /path/to/quickbrush
pytest
```

### Fixture Not Found

Ensure `conftest.py` is in the tests directory and contains the fixture.

### Test Hangs

Check for infinite loops or missing mocks for external API calls.

## Coverage Goals

| Module | Target Coverage |
|--------|----------------|
| api_routes.py | >90% |
| generation_service.py | >85% |
| image_service.py | >85% |
| models.py | >70% |
| Overall | >80% |

## Future Improvements

- [ ] Add performance/load tests
- [ ] Add integration tests with real MongoDB (optional)
- [ ] Add E2E tests using Playwright
- [ ] Add mutation testing
- [ ] Add security/penetration tests
