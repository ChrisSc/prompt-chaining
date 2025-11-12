#!/bin/bash
# Code formatting and linting script

set -e

# Change to project root
cd "$(dirname "$0")/.."

# Check if virtual environment is active
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Activating virtual environment..."
    source .venv/bin/activate
fi

echo "Formatting code with black..."
black src/ tests/

echo "Linting code with ruff..."
ruff check src/ tests/ --fix

echo "Type checking with mypy..."
mypy src/orchestrator_worker --strict

echo "✅ All checks passed!"
