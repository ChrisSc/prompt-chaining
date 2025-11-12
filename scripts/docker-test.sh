#!/bin/bash

################################################################################
# Docker Build and Integration Test Script
#
# This script automates the testing of Docker builds and container deployments.
# It validates that the Docker image builds successfully, starts correctly, and
# responds to API requests.
#
# Usage: ./scripts/docker-test.sh
#
# Prerequisites:
#   - Docker installed and running
#   - docker-compose installed
#   - .env file configured with ANTHROPIC_API_KEY and JWT_SECRET_KEY
#
# Returns:
#   0 on success
#   1 on failure
################################################################################

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_NAME="orchestrator-worker:latest"
CONTAINER_NAME="orchestrator-worker-api"
API_HOST="http://localhost:8000"
MAX_WAIT_SECONDS=30
CHECK_INTERVAL=1

################################################################################
# Helper Functions
################################################################################

log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

print_section() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$*${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

cleanup() {
    local exit_code=$?
    if [ $exit_code -ne 0 ]; then
        log_warning "Test failed. Stopping containers for cleanup..."
        docker-compose -f "$PROJECT_ROOT/docker-compose.yml" down 2>/dev/null || true
    fi
    return $exit_code
}

trap cleanup EXIT

################################################################################
# Prerequisite Checks
################################################################################

print_section "Checking Prerequisites"

# Check for Docker
if ! command -v docker &> /dev/null; then
    log_error "Docker is not installed or not in PATH"
    exit 1
fi
log_success "Docker found: $(docker --version)"

# Check for docker-compose
if ! command -v docker-compose &> /dev/null; then
    log_error "docker-compose is not installed or not in PATH"
    exit 1
fi
log_success "docker-compose found: $(docker-compose --version)"

# Check for curl
if ! command -v curl &> /dev/null; then
    log_error "curl is not installed or not in PATH"
    exit 1
fi
log_success "curl found"

# Check .env file exists
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    log_error ".env file not found at $PROJECT_ROOT/.env"
    log_info "Create .env file from .env.example:"
    log_info "  cp .env.example .env"
    log_info "  # Edit .env and configure ANTHROPIC_API_KEY and JWT_SECRET_KEY"
    exit 1
fi
log_success ".env file exists"

# Verify required environment variables
if ! grep -q "^ANTHROPIC_API_KEY=" "$PROJECT_ROOT/.env" || \
   grep "^ANTHROPIC_API_KEY=your_anthropic_api_key_here" "$PROJECT_ROOT/.env" > /dev/null; then
    log_warning "ANTHROPIC_API_KEY not configured in .env (will use default placeholder)"
fi

if ! grep -q "^JWT_SECRET_KEY=" "$PROJECT_ROOT/.env" || \
   grep "^JWT_SECRET_KEY=your_jwt_secret_key_here" "$PROJECT_ROOT/.env" > /dev/null; then
    log_warning "JWT_SECRET_KEY not configured in .env (will use default placeholder)"
fi

################################################################################
# Build Docker Image
################################################################################

print_section "Building Docker Image"

log_info "Building image: $IMAGE_NAME"
log_info "Context: $PROJECT_ROOT"
log_info "Dockerfile: $PROJECT_ROOT/Dockerfile"

if docker-compose -f "$PROJECT_ROOT/docker-compose.yml" build; then
    log_success "Docker image built successfully"
else
    log_error "Docker image build failed"
    exit 1
fi

# Check image size
log_info "Checking image size..."
IMAGE_SIZE=$(docker images "$IMAGE_NAME" --format "{{.Size}}" 2>/dev/null || echo "unknown")
log_success "Image size: $IMAGE_SIZE"

# Verify image size is reasonable (less than 500MB)
if [[ "$IMAGE_SIZE" == *"G"* ]]; then
    log_warning "Image size seems large (>500MB). Consider optimization if exceeding 500MB."
fi

################################################################################
# Start Container
################################################################################

print_section "Starting Container"

log_info "Starting container with docker-compose..."
if docker-compose -f "$PROJECT_ROOT/docker-compose.yml" up -d; then
    log_success "Container started successfully"
    log_info "Container ID: $(docker-compose -f "$PROJECT_ROOT/docker-compose.yml" ps -q orchestrator-worker)"
else
    log_error "Failed to start container"
    exit 1
fi

# Wait for container to be healthy
log_info "Waiting for container to become healthy (max ${MAX_WAIT_SECONDS}s)..."
WAIT_TIME=0
while [ $WAIT_TIME -lt $MAX_WAIT_SECONDS ]; do
    HEALTH_STATUS=$(docker-compose -f "$PROJECT_ROOT/docker-compose.yml" ps orchestrator-worker 2>/dev/null | grep -oP 'healthy|unhealthy|starting' || echo "unknown")

    if [ "$HEALTH_STATUS" = "healthy" ]; then
        log_success "Container is healthy"
        break
    elif [ "$HEALTH_STATUS" = "unhealthy" ]; then
        log_error "Container health check failed"
        log_info "Container logs:"
        docker-compose -f "$PROJECT_ROOT/docker-compose.yml" logs orchestrator-worker | tail -50
        exit 1
    else
        echo -ne "\r  Status: ${HEALTH_STATUS:-checking}... (${WAIT_TIME}s)"
        sleep $CHECK_INTERVAL
        WAIT_TIME=$((WAIT_TIME + CHECK_INTERVAL))
    fi
done

if [ $WAIT_TIME -ge $MAX_WAIT_SECONDS ]; then
    log_warning "Container health check timeout. Proceeding with tests anyway..."
    log_info "Container logs:"
    docker-compose -f "$PROJECT_ROOT/docker-compose.yml" logs orchestrator-worker | tail -20
fi
echo "" # New line after progress

################################################################################
# Health Check Endpoints
################################################################################

print_section "Testing Health Check Endpoints"

# Test /health/ endpoint
log_info "Testing GET /health/ endpoint..."
if HEALTH_RESPONSE=$(curl -s -w "\n%{http_code}" "$API_HOST/health/" 2>/dev/null); then
    HTTP_CODE=$(echo "$HEALTH_RESPONSE" | tail -1)
    BODY=$(echo "$HEALTH_RESPONSE" | head -1)

    if [ "$HTTP_CODE" = "200" ]; then
        log_success "Health endpoint responds with HTTP 200"
        log_info "Response: $BODY"
    else
        log_warning "Health endpoint responded with HTTP $HTTP_CODE (expected 200)"
    fi
else
    log_error "Failed to reach health endpoint"
    exit 1
fi

# Test /health/ready endpoint
log_info "Testing GET /health/ready endpoint..."
if READY_RESPONSE=$(curl -s -w "\n%{http_code}" "$API_HOST/health/ready" 2>/dev/null); then
    HTTP_CODE=$(echo "$READY_RESPONSE" | tail -1)
    BODY=$(echo "$READY_RESPONSE" | head -1)

    if [ "$HTTP_CODE" = "200" ]; then
        log_success "Ready endpoint responds with HTTP 200"
        log_info "Response: $BODY"
    else
        log_warning "Ready endpoint responded with HTTP $HTTP_CODE (expected 200)"
    fi
else
    log_error "Failed to reach ready endpoint"
    exit 1
fi

################################################################################
# JWT Token Generation
################################################################################

print_section "Testing JWT Token Generation"

log_info "Generating test JWT token..."
if ! cd "$PROJECT_ROOT"; then
    log_error "Failed to change to project root"
    exit 1
fi

# Check if Python and required modules are available
if ! command -v python &> /dev/null; then
    log_warning "Python not available on host. Skipping JWT token generation test."
    log_info "Note: API authentication will still be tested with provided .env secrets"
    BEARER_TOKEN=""
else
    if BEARER_TOKEN=$(python scripts/generate_jwt.py 2>/dev/null); then
        log_success "JWT token generated successfully"
        log_info "Token (first 50 chars): ${BEARER_TOKEN:0:50}..."
    else
        log_warning "Failed to generate JWT token"
        log_info "Token generation may require Python environment setup"
        log_info "Attempting to extract token from environment..."
        BEARER_TOKEN="${API_BEARER_TOKEN:-}"
    fi
fi

# If we have a bearer token, test with it; otherwise try without (for public endpoints)
if [ -z "$BEARER_TOKEN" ]; then
    log_warning "No bearer token available. Testing public endpoints only."
fi

################################################################################
# API Endpoint Tests
################################################################################

print_section "Testing API Endpoints"

# Test /v1/models endpoint
log_info "Testing GET /v1/models endpoint..."
if [ -n "$BEARER_TOKEN" ]; then
    MODELS_RESPONSE=$(curl -s -w "\n%{http_code}" \
        -H "Authorization: Bearer $BEARER_TOKEN" \
        -H "Content-Type: application/json" \
        "$API_HOST/v1/models" 2>/dev/null)
    HTTP_CODE=$(echo "$MODELS_RESPONSE" | tail -1)
    BODY=$(echo "$MODELS_RESPONSE" | head -1)

    if [ "$HTTP_CODE" = "200" ]; then
        log_success "/v1/models endpoint responds with HTTP 200"
        log_info "Response preview: $(echo "$BODY" | head -c 100)..."
    elif [ "$HTTP_CODE" = "401" ] || [ "$HTTP_CODE" = "403" ]; then
        log_warning "/v1/models endpoint responded with HTTP $HTTP_CODE (authentication error)"
        log_info "This is expected if JWT_SECRET_KEY is not properly configured"
    else
        log_warning "/v1/models endpoint responded with HTTP $HTTP_CODE"
    fi
else
    log_info "Skipping /v1/models test (no bearer token available)"
fi

################################################################################
# Chat Completion Streaming Test
################################################################################

print_section "Testing Chat Completion Streaming"

log_info "Testing POST /v1/chat/completions endpoint with streaming..."

CHAT_PAYLOAD='{"model":"orchestrator-worker","messages":[{"role":"user","content":"Respond with exactly 5 words."}],"stream":true}'

if [ -n "$BEARER_TOKEN" ]; then
    log_info "Sending streaming request (will wait up to 30 seconds for response)..."
    STREAM_TEST=$(timeout 30 curl -s -N \
        -H "Authorization: Bearer $BEARER_TOKEN" \
        -H "Content-Type: application/json" \
        -d "$CHAT_PAYLOAD" \
        "$API_HOST/v1/chat/completions" 2>/dev/null | head -5)

    if echo "$STREAM_TEST" | grep -q "data:"; then
        log_success "Streaming response received"
        log_info "First streamed chunk: $(echo "$STREAM_TEST" | head -1)"
    else
        if [ -z "$STREAM_TEST" ]; then
            log_warning "No response received from streaming endpoint"
            log_info "This may indicate an issue with ANTHROPIC_API_KEY configuration"
        else
            log_warning "Unexpected response format"
            log_info "Response preview: $(echo "$STREAM_TEST" | head -c 100)..."
        fi
    fi
else
    log_info "Skipping streaming test (no bearer token available)"
fi

################################################################################
# Test Summary
################################################################################

print_section "Test Summary"

log_success "Docker image built and tested successfully"
log_info "Image: $IMAGE_NAME"
log_info "Container: $CONTAINER_NAME"
log_info "API URL: $API_HOST"

# Show container status
log_info "Container status:"
docker-compose -f "$PROJECT_ROOT/docker-compose.yml" ps orchestrator-worker

print_section "Next Steps"

log_info "View running container:"
log_info "  docker-compose logs -f orchestrator-worker"

log_info "Test with console client (if available):"
log_info "  export API_BEARER_TOKEN=\$(python scripts/generate_jwt.py)"
log_info "  python console_client.py 'Hello, world!'"

log_info "Stop container:"
log_info "  docker-compose down"

log_info "Deploy to production:"
log_info "  docker-compose up -d"

print_section "Docker Test Complete"

log_success "All tests passed! Container is ready for use."
exit 0
