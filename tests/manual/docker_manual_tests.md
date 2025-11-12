# Docker Manual Testing Guide

This guide provides step-by-step instructions for manual Docker testing and validation. Use this when automated tests cannot cover specific scenarios or for interactive verification.

## Phase 1: Docker Build Validation

### 1.1 Verify Dockerfile Syntax

```bash
# Check Dockerfile for syntax errors
docker build --dry-run -f Dockerfile .

# Expected output:
# Dry-run succeeded (if using BuildKit)
# OR errors if syntax is incorrect
```

### 1.2 Build Docker Image

```bash
# Build image with clear naming
docker build -t orchestrator-worker:test .

# Expected output:
# Successfully built [image-id]
# [NOTICE] ...
# No errors

# Check build time
time docker build -t orchestrator-worker:test .

# Expected time: 1-3 minutes
```

### 1.3 Verify Image was Created

```bash
# List images
docker images orchestrator-worker:test

# Expected output:
# REPOSITORY              TAG     IMAGE ID       CREATED              SIZE
# orchestrator-worker     test    abc123def456   less than a minute   ~300MB
```

### 1.4 Check Image Size

```bash
# Get exact size
docker images orchestrator-worker:test --format "Size: {{.Size}}"

# Expected: < 500MB (target: 300-400MB)

# Compare with other images
docker images | head -10

# Verify our image is reasonable compared to others
```

### 1.5 Inspect Image Configuration

```bash
# See full image config
docker inspect orchestrator-worker:test

# Key fields to check:
# - Config.Image: python:3.12-slim
# - Config.ExposedPorts.8000/tcp
# - Config.Env: Contains PYTHONUNBUFFERED and PYTHONDONTWRITEBYTECODE
# - Config.WorkingDir: /app
# - Config.User: appuser (or empty for 1000)
# - Config.Healthcheck: Present and configured

# Pretty print with jq (if installed)
docker inspect orchestrator-worker:test | jq '.[] | {Image: .Config.Image, User: .Config.User, Env: .Config.Env}'
```

### 1.6 View Image History

```bash
# See all layers
docker history orchestrator-worker:test

# Check for secrets
docker history orchestrator-worker:test --no-trunc | grep -i "key\|secret\|password"

# Expected: No matches (secrets should not be in layers)

# View layer sizes
docker history orchestrator-worker:test --human --quiet

# Multi-stage build should show:
# - Builder stage (discarded after build)
# - Final stage with only runtime dependencies
```

## Phase 2: Container Startup Validation

### 2.1 Create .env File

```bash
# Copy example
cp .env.example .env

# Edit with your values
nano .env

# Required values:
# ANTHROPIC_API_KEY=sk-ant-v4-... (or your test key)
# JWT_SECRET_KEY=generated_secret_with_32_chars_minimum

# Generate secure JWT key
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2.2 Validate docker-compose.yml

```bash
# Validate YAML syntax
docker-compose config

# Expected output:
# Prints validated YAML without errors

# Or check specific service
docker-compose config --services

# Expected output:
# orchestrator-worker
```

### 2.3 Start Container

```bash
# Start container in background
docker-compose up -d

# Expected output:
# Creating orchestrator-worker-api ... done

# Check logs immediately
docker-compose logs orchestrator-worker

# Expected output:
# Should see startup messages
# No "ERROR" or "failed" in logs
```

### 2.4 Verify Container is Running

```bash
# Check container status
docker-compose ps

# Expected output:
# NAME                          STATUS
# orchestrator-worker-api       Up (healthy) or Up

# If not healthy, wait a bit
sleep 5
docker-compose ps

# Should show (healthy) within 30 seconds
```

### 2.5 Check Health Status

```bash
# Get more details
docker inspect orchestrator-worker-api --format="{{json .State.Health.Status}}"

# Expected output:
# "healthy"

# If unhealthy, check logs
docker-compose logs orchestrator-worker | tail -20

# Look for errors related to ANTHROPIC_API_KEY or startup
```

## Phase 3: API Endpoint Testing

### 3.1 Generate Bearer Token

```bash
# Generate token inside running container
docker-compose exec orchestrator-worker python scripts/generate_jwt.py

# Expected output:
# Prints JWT token (looks like: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI...)

# Export for later use
export TOKEN=$(docker-compose exec -T orchestrator-worker python scripts/generate_jwt.py)

# Verify
echo $TOKEN
```

### 3.2 Test Health Endpoint

```bash
# Basic health check
curl -v http://localhost:8000/health/

# Expected output:
# HTTP/1.1 200 OK
# JSON response with health status

# Test readiness
curl -v http://localhost:8000/health/ready

# Expected output:
# HTTP/1.1 200 OK
```

### 3.3 Test Protected Endpoint Without Auth

```bash
# Try to access without token
curl -v http://localhost:8000/v1/models

# Expected output:
# HTTP/1.1 401 Unauthorized
# {"detail": "..."}
```

### 3.4 Test Protected Endpoint With Auth

```bash
# Set token
TOKEN=$(docker-compose exec -T orchestrator-worker python scripts/generate_jwt.py)

# Test models endpoint
curl -v -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/v1/models

# Expected output:
# HTTP/1.1 200 OK
# JSON array of available models

# View formatted response
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/v1/models | jq .
```

### 3.5 Test Streaming Chat Endpoint

```bash
# Generate token
TOKEN=$(docker-compose exec -T orchestrator-worker python scripts/generate_jwt.py)

# Test streaming endpoint with curl -N (disable buffering)
curl -N -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model":"orchestrator-worker","messages":[{"role":"user","content":"Say hello"}]}' \
  http://localhost:8000/v1/chat/completions

# Expected output:
# SSE format data:
# data: {"type": "chunk", "delta": {"content": "..."}}
# ...
# data: [DONE]

# For better formatting, pipe to Python
curl -s -N -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model":"orchestrator-worker","messages":[{"role":"user","content":"Hello"}]}' \
  http://localhost:8000/v1/chat/completions | \
  python -c "
import sys
for line in sys.stdin:
    line = line.strip()
    if line.startswith('data: '):
        data = line[6:]
        if data != '[DONE]':
            print(data)
"
```

### 3.6 Test with Python Client

```bash
# Use console client if available
export API_BEARER_TOKEN=$(docker-compose exec -T orchestrator-worker python scripts/generate_jwt.py)

python console_client.py "Hello from Docker"

# Expected output:
# Streaming response showing the AI response
```

## Phase 4: Environment Variable Testing

### 4.1 Check Container Environment

```bash
# View all environment variables
docker-compose exec orchestrator-worker env | sort

# Expected to see:
# API_HOST=0.0.0.0
# API_PORT=8000
# LOG_LEVEL=INFO
# CHAIN_ANALYZE_MODEL=claude-haiku-4-5-20251001
# CHAIN_PROCESS_MODEL=claude-haiku-4-5-20251001
# CHAIN_SYNTHESIZE_MODEL=claude-haiku-4-5-20251001
# PYTHONUNBUFFERED=1
# PYTHONDONTWRITEBYTECODE=1
# PATH=/opt/venv/bin:... (includes venv)
```

### 4.2 Check Specific Variable

```bash
# Check API port
docker-compose exec orchestrator-worker env | grep API_PORT

# Expected output:
# API_PORT=8000

# Check Python settings
docker-compose exec orchestrator-worker env | grep PYTHON

# Expected output:
# PYTHONUNBUFFERED=1
# PYTHONDONTWRITEBYTECODE=1
```

### 4.3 Modify Environment and Restart

```bash
# Edit .env
nano .env

# Change LOG_LEVEL to DEBUG
# LOG_LEVEL=DEBUG

# Restart container
docker-compose restart orchestrator-worker

# Wait for restart
sleep 5

# Check logs have more detail
docker-compose logs orchestrator-worker | head -20

# Should see more DEBUG level logs
```

## Phase 5: Container Debugging

### 5.1 View Container Logs

```bash
# Stream logs in real-time
docker-compose logs -f orchestrator-worker

# Last 50 lines
docker-compose logs orchestrator-worker | tail -50

# Last 20 lines with timestamps
docker-compose logs orchestrator-worker | tail -20

# Search for errors
docker-compose logs orchestrator-worker | grep -i error

# Search for specific pattern
docker-compose logs orchestrator-worker | grep "health"
```

### 5.2 Run Command Inside Container

```bash
# List Python packages
docker-compose exec orchestrator-worker pip list

# Check Python version
docker-compose exec orchestrator-worker python --version

# Check who is running the app
docker-compose exec orchestrator-worker whoami

# Expected output: appuser (non-root)

# List app files
docker-compose exec orchestrator-worker ls -la /app

# Expected output:
# src/workflow
# scripts/
# logs/ (owned by appuser)
```

### 5.3 Test Health Check Manually

```bash
# Run health check command directly
docker-compose exec orchestrator-worker curl -f http://localhost:8000/health/

# Expected output:
# JSON health response
# Exit code 0

# Time the health check
docker-compose exec orchestrator-worker \
  time curl -f http://localhost:8000/health/

# Expected time: < 1 second
```

### 5.4 Inspect Process Inside Container

```bash
# See running processes
docker-compose exec orchestrator-worker ps aux

# Expected output:
# appuser    1 ... python -m uvicorn workflow.main:app

# Check port listening
docker-compose exec orchestrator-worker netstat -tlnp

# Expected output:
# tcp  0  0  0.0.0.0:8000  0.0.0.0:*  LISTEN  1/python
```

## Phase 6: Network and Port Testing

### 6.1 Verify Port Mapping

```bash
# Check docker-compose port mapping
docker-compose ps

# Should show:
# Ports: 0.0.0.0:8000->8000/tcp

# Test port accessibility
nc -zv localhost 8000

# Expected output:
# Connection to localhost port 8000 [tcp/*] succeeded!
```

### 6.2 Test from Different Interfaces

```bash
# Test localhost
curl -s http://127.0.0.1:8000/health/ | jq .

# Test from host IP (if applicable)
curl -s http://[YOUR_IP]:8000/health/ | jq .

# Test DNS name
curl -s http://docker.local:8000/health/ 2>&1 || echo "DNS not configured"
```

## Phase 7: Security Validation

### 7.1 Verify Non-Root User

```bash
# Check running user
docker-compose exec orchestrator-worker id

# Expected output:
# uid=1000(appuser) gid=1000(appuser) groups=1000(appuser)

# Try to become root (should fail or require password)
docker-compose exec orchestrator-worker sudo su

# Expected output:
# sudo: not found or permission denied
```

### 7.2 Check File Permissions

```bash
# List app directory permissions
docker-compose exec orchestrator-worker ls -la /app

# Expected output:
# All files owned by appuser:appuser
# No world-writable files

# Check logs directory
docker-compose exec orchestrator-worker ls -la /app/logs

# Expected output:
# drwxr-xr-x appuser:appuser logs
```

### 7.3 Verify No Secrets in Image

```bash
# Check image history for secrets
docker history orchestrator-worker:test --no-trunc | grep -i "api.key\|secret"

# Expected: No results

# Inspect image environment (from outside)
docker inspect orchestrator-worker:test | grep -i "anthropic\|secret"

# Expected: No matches (secrets injected at runtime via .env)
```

## Phase 8: Container Lifecycle

### 8.1 Graceful Shutdown

```bash
# Stop container gracefully
docker-compose stop orchestrator-worker

# Check it stopped
docker-compose ps

# Expected output:
# Status: Exited (0)

# Check logs for shutdown messages
docker-compose logs orchestrator-worker | tail -10

# Should not show errors
```

### 8.2 Container Restart

```bash
# Start again
docker-compose start orchestrator-worker

# Wait for health check
sleep 10

# Verify healthy
docker-compose ps

# Expected output:
# Status: Up (healthy)

# Check it's accepting requests
curl -s http://localhost:8000/health/ | jq .
```

### 8.3 Full Teardown and Rebuild

```bash
# Stop and remove containers
docker-compose down

# Expected output:
# Removing orchestrator-worker-api ... done
# Removing orchestrator-network ... done

# Rebuild image
docker-compose build

# Expected output:
# Building orchestrator-worker
# Successfully built ...

# Start fresh
docker-compose up -d

# Verify
docker-compose ps
curl http://localhost:8000/health/
```

## Phase 9: Performance Testing

### 9.1 Measure Build Time

```bash
# Time complete build
time docker-compose build

# Expected output:
# real: 1m00s - 3m00s (depending on system and cache)

# Without cache (fresh build)
docker-compose build --no-cache

# Expected output:
# Takes longer, usually 2-5 minutes
```

### 9.2 Measure Startup Time

```bash
# Remove and rebuild
docker-compose down
docker-compose build

# Time startup
time docker-compose up -d

# Check health status
docker-compose exec orchestrator-worker curl -f http://localhost:8000/health/

# Measure time to first successful health check
```

### 9.3 Monitor Resource Usage

```bash
# Watch container resource usage
docker stats orchestrator-worker-api

# Expected output:
# CPU: ~0-2% (idle)
# Memory: ~100-200MB
# Network I/O: depends on activity

# Stop monitoring with Ctrl+C
```

## Phase 10: Troubleshooting Scenarios

### Scenario: Container fails to start

```bash
# Check logs for errors
docker-compose logs orchestrator-worker

# Look for:
# - Missing ANTHROPIC_API_KEY
# - Missing JWT_SECRET_KEY
# - Port already in use
# - Python import errors

# Common fixes:
# 1. Add missing env vars to .env
# 2. Kill process using port: lsof -i :8000 | grep LISTEN | awk '{print $2}' | xargs kill -9
# 3. Rebuild image: docker-compose build --no-cache
```

### Scenario: Health check fails

```bash
# Check health endpoint directly
curl -v http://localhost:8000/health/

# If fails, check:
# 1. Application logs: docker-compose logs
# 2. Port accessible: nc -zv localhost 8000
# 3. API_PORT env var: docker-compose exec orchestrator-worker env | grep API_PORT
# 4. Try without bearer token (health is public)
```

### Scenario: API authentication fails

```bash
# Check token generation
docker-compose exec orchestrator-worker python scripts/generate_jwt.py

# If fails, check:
# 1. JWT_SECRET_KEY is set in .env
# 2. JWT_SECRET_KEY is at least 32 characters
# 3. Scripts directory is in image

# Generate token manually
TOKEN=$(docker-compose exec -T orchestrator-worker python scripts/generate_jwt.py)

# Test with generated token
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/v1/models
```

### Scenario: Image is too large

```bash
# Check layer sizes
docker history orchestrator-worker:test --human

# Look for:
# 1. Large dependency layers (should be in builder)
# 2. Apt cache not cleaned (look for apt-get install)
# 3. Build tools in final image (should be in builder only)

# Solutions:
# 1. Verify multi-stage build in Dockerfile
# 2. Check RUN statements clean up cache
# 3. Rebuild: docker-compose build --no-cache
```

## Quick Reference Commands

```bash
# Start all services
docker-compose up -d

# View service status
docker-compose ps

# View logs
docker-compose logs -f

# Execute command in container
docker-compose exec orchestrator-worker [COMMAND]

# Stop services
docker-compose stop

# Remove services
docker-compose down

# Rebuild image
docker-compose build

# Rebuild without cache
docker-compose build --no-cache

# View image info
docker inspect orchestrator-worker:test

# View image history
docker history orchestrator-worker:test

# Get image size
docker images orchestrator-worker:test --format "{{.Size}}"

# Test API endpoint
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/v1/models

# Stream from API
curl -N -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/v1/chat/completions \
  -d '{...}'
```

## Testing Checklist

Use this checklist to verify all manual tests pass:

- [ ] Docker image builds successfully
- [ ] Image size is reasonable (<500MB)
- [ ] Container starts and becomes healthy
- [ ] Health endpoint returns 200
- [ ] Readiness endpoint returns 200
- [ ] Protected endpoints require auth
- [ ] Bearer token generation works
- [ ] Protected endpoints work with valid token
- [ ] Streaming endpoint returns SSE format
- [ ] Environment variables are loaded
- [ ] Container runs as non-root user
- [ ] No secrets in image layers
- [ ] Logs are captured and readable
- [ ] Container stops gracefully
- [ ] Container can be restarted

## When Manual Testing Is Complete

1. Document any issues found
2. Update automated tests if needed
3. Commit changes with clear message
4. Prepare for deployment
