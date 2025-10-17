#!/bin/bash
# Quick test runner script for Quickbrush

set -e

echo "🧪 Quickbrush Test Runner"
echo "========================="
echo ""

# Check if test dependencies are installed
if ! python -c "import pytest" 2>/dev/null; then
    echo "⚠️  Test dependencies not found. Installing..."
    pip install -r requirements-test.txt
    echo "✅ Test dependencies installed"
    echo ""
fi

# Parse command line arguments
COVERAGE=false
VERBOSE=false
SPECIFIC_TEST=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --coverage|-c)
            COVERAGE=true
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --test|-t)
            SPECIFIC_TEST="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: ./run_tests.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -c, --coverage     Run with coverage report"
            echo "  -v, --verbose      Verbose output"
            echo "  -t, --test FILE    Run specific test file"
            echo "  -h, --help         Show this help message"
            echo ""
            echo "Examples:"
            echo "  ./run_tests.sh                           # Run all tests"
            echo "  ./run_tests.sh --coverage                # Run with coverage"
            echo "  ./run_tests.sh -t tests/test_api_auth.py # Run specific file"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Build pytest command
PYTEST_CMD="pytest"

if [ "$VERBOSE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD -v"
fi

if [ "$COVERAGE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD --cov=. --cov-report=html --cov-report=term-missing"
fi

if [ -n "$SPECIFIC_TEST" ]; then
    PYTEST_CMD="$PYTEST_CMD $SPECIFIC_TEST"
fi

# Run tests
echo "Running: $PYTEST_CMD"
echo ""

$PYTEST_CMD

# Show coverage report location if coverage was run
if [ "$COVERAGE" = true ]; then
    echo ""
    echo "📊 Coverage report generated: htmlcov/index.html"
    echo "   Open with: open htmlcov/index.html (macOS) or xdg-open htmlcov/index.html (Linux)"
fi

echo ""
echo "✅ Tests completed!"
