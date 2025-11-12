#!/bin/bash
# Test execution script

set -e

# Change to project root
cd "$(dirname "$0")/.."

# Check if virtual environment is active
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Activating virtual environment..."
    source .venv/bin/activate
fi

# Install dependencies if needed
echo "Installing dependencies..."
pip install -e ".[dev]" -q

# Run tests with coverage
echo "Running tests with coverage..."
pytest tests/ -v --cov=src/orchestrator_worker --cov-report=html --cov-report=term-missing

echo ""
echo "Coverage report generated in htmlcov/index.html"
