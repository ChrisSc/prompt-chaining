#!/bin/bash
# Development server startup script

set -e

# Change to project root
cd "$(dirname "$0")/.."

# Check if .env exists, if not copy from .env.example
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "Please update .env with your configuration!"
fi

# Check if virtual environment is active
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Activating virtual environment..."
    source .venv/bin/activate
fi

# Install dependencies if needed
echo "Installing dependencies..."
pip install -e ".[dev]" -q

# Note: Pydantic Settings reads .env file directly
# Extract API_HOST and API_PORT from .env for script usage
if [ -f .env ]; then
    export API_PORT=$(grep '^API_PORT=' .env | cut -d '=' -f 2)
    export API_HOST=$(grep '^API_HOST=' .env | cut -d '=' -f 2)
fi

# Set defaults if not found in .env
API_HOST=${API_HOST:-0.0.0.0}
API_PORT=${API_PORT:-8000}

# Run the development server
echo "Starting development server..."
echo "API will be available at: http://localhost:${API_PORT}"
echo "Documentation at: http://localhost:${API_PORT}/docs"
echo ""

fastapi dev src/orchestrator_worker/main.py --host ${API_HOST} --port ${API_PORT}
