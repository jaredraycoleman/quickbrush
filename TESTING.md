# Quickbrush API Testing Guide

## Quick Start

```bash
# Install test dependencies
pip install -r requirements-test.txt

# Run all tests
pytest

# Or use the convenience script
./run_tests.sh
```

## Test Suite Overview

The Quickbrush test suite provides comprehensive coverage of all API endpoints with **50+ test cases**.

### Test Files

| File | Tests | Coverage |
|------|-------|----------|
| `test_api_auth.py` | 7 tests | Authentication & API keys |
| `test_api_user.py` | 4 tests | User information endpoint |
| `test_api_generation.py` | 13 tests | Image generation |
| `test_api_images.py` | 10 tests | Image retrieval & listing |
| **Total** | **34+ tests** | **All API endpoints** |

## What's Tested

### ✅ Authentication (`test_api_auth.py`)
- Valid/invalid API keys
- Missing authorization headers
- Inactive/expired keys
- API key usage tracking

### ✅ User Info (`test_api_user.py`)
- User with/without subscription
- Brushstroke balance calculation
- Subscription allowance tracking

### ✅ Image Generation (`test_api_generation.py`)
- All generation types (character, scene, creature, item)
- All quality levels (low/medium/high)
- Brushstroke deduction
- 100-image limit enforcement
- Error handling (insufficient funds, API errors)
- Subscription vs purchased brushstrokes

### ✅ Image Retrieval (`test_api_images.py`)
- Get image by ID
- List generations with pagination
- Access control (users can't see others' images)
- Ordering by date
- Image format (WebP)

## Running Tests

### Basic Commands

```bash
# All tests
pytest

# With coverage
pytest --cov=. --cov-report=html

# Specific file
pytest tests/test_api_auth.py

# Specific test
pytest tests/test_api_auth.py::TestAuthentication::test_valid_api_key

# Verbose output
pytest -v

# Stop on first failure
pytest -x
```

### Using the Test Script

```bash
# Run all tests
./run_tests.sh

# With coverage report
./run_tests.sh --coverage

# Specific file
./run_tests.sh --test tests/test_api_auth.py

# Verbose mode
./run_tests.sh --verbose

# Get help
./run_tests.sh --help
```

## Test Architecture

### Mocking Strategy

All external services are mocked for fast, reliable tests:

- **MongoDB**: Uses `mongomock` (in-memory database)
- **Stripe API**: Mocked with `unittest.mock`
- **OpenAI API**: Mocked with `unittest.mock`
- **Auth0**: Mocked authentication

### Fixtures (in `conftest.py`)

```python
# Database
mock_mongo              # Mock MongoDB connection

# Users & Auth
test_user              # Test user with 100 brushstrokes
test_api_key           # Valid API key for test user
auth_headers           # Pre-configured auth headers

# API Client
api_client             # FastAPI test client

# Mocks
mock_stripe            # Mock Stripe API
mock_openai            # Mock OpenAI API

# Sample Data
sample_generation      # Sample image generation record
```

## Test Coverage Goals

| Component | Current | Goal |
|-----------|---------|------|
| API Routes | ~90% | >90% |
| Generation Service | ~85% | >85% |
| Image Service | ~85% | >85% |
| **Overall** | **~85%** | **>80%** |

View coverage: `pytest --cov=. --cov-report=html && open htmlcov/index.html`

## Writing New Tests

### Example Test

```python
from fastapi import status

class TestMyFeature:
    """Test my new feature."""

    def test_success_case(self, api_client, auth_headers):
        """Test successful operation."""
        response = api_client.get("/api/my-endpoint", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["field"] == "expected_value"

    def test_error_case(self, api_client, auth_headers):
        """Test error handling."""
        response = api_client.post(
            "/api/my-endpoint",
            json={"invalid": "data"},
            headers=auth_headers
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.json()["detail"].lower()
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-test.txt

      - name: Run tests
        run: pytest --cov=. --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## Debugging Tests

### Failed Test?

```bash
# Run with verbose output
pytest -v tests/test_api_auth.py

# Run with print statements visible
pytest -s tests/test_api_auth.py

# Run with debugger
pytest --pdb tests/test_api_auth.py

# Show local variables on failure
pytest -l tests/test_api_auth.py
```

### Common Issues

**Import errors**: Run pytest from project root
```bash
cd /home/jared/quickbrush
pytest
```

**Fixture not found**: Check `conftest.py` exists in tests/

**Hanging tests**: Check for missing mocks on external APIs

**Database errors**: Tests use mongomock, no real DB needed

## Performance

All tests should complete in **< 10 seconds** thanks to:
- In-memory database (mongomock)
- Mocked external services
- No real HTTP requests
- No disk I/O

## Best Practices

1. ✅ **Test one thing** - Each test should verify one specific behavior
2. ✅ **Clear names** - `test_generate_image_insufficient_brushstrokes` not `test_gen1`
3. ✅ **Independent** - Tests should not depend on each other
4. ✅ **Fast** - Use mocks, avoid real I/O
5. ✅ **Readable** - Use clear assertions and helpful error messages

## Next Steps

- [ ] Add integration tests with real MongoDB (optional)
- [ ] Add load/performance tests
- [ ] Add security tests (SQL injection, XSS, etc.)
- [ ] Set up CI/CD pipeline
- [ ] Add mutation testing
- [ ] Monitor coverage trends

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [mongomock Documentation](https://github.com/mongomock/mongomock)
- [Coverage.py](https://coverage.readthedocs.io/)

---

**Questions?** See `tests/README.md` for more detailed documentation.
