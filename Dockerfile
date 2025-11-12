# Multi-stage Dockerfile for Orchestrator Worker Service
# Stage 1: Builder - compile dependencies with cache optimization
FROM python:3.12-slim AS builder

# Install build dependencies needed to compile Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment in builder
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy dependency file and source for package building
COPY pyproject.toml /tmp/
COPY src /tmp/src
WORKDIR /tmp

# Install Python dependencies with BuildKit cache optimization
# The cache mount reduces build time on subsequent rebuilds
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir .

# Stage 2: Production - minimal runtime image
FROM python:3.12-slim

# Install only runtime dependencies (curl for health checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user with UID 1000 for security and volume permission compatibility
RUN useradd -m -u 1000 appuser

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Set working directory
WORKDIR /app

# Copy application code with proper ownership
# Copy main application package
COPY --chown=appuser:appuser src/orchestrator_worker /app/src/orchestrator_worker

# Copy scripts directory for utilities like generate_jwt.py
COPY --chown=appuser:appuser scripts /app/scripts

# Create necessary directories with proper permissions
RUN mkdir -p /app/logs && chown -R appuser:appuser /app

# Switch to non-root user for security
USER appuser

# Expose the API port
EXPOSE 8000

# Health check configuration
# Checks if the service is responding to health requests every 30 seconds
# timeout: 3 seconds for each check
# start-period: 5 seconds before first check (startup grace period)
# retries: 3 failed checks before marking unhealthy
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

# Use exec-form ENTRYPOINT and CMD for proper signal handling (SIGTERM, SIGINT)
# This ensures the Python process receives signals correctly for graceful shutdown
ENTRYPOINT ["python", "-m", "uvicorn"]
CMD ["orchestrator_worker.main:app", "--host", "0.0.0.0", "--port", "8000"]
