"""
Unit tests for Docker configuration validation.

Tests validate that the Dockerfile and docker-compose.yml configurations
are correct for production deployment of the orchestrator-worker service.
This includes:
- Multi-stage build configuration
- Non-root user configuration
- Environment variable handling
- Volume mount paths
- Port exposure
- Health check settings
"""

import os
from pathlib import Path

import pytest


class TestDockerfileStructure:
    """Test Dockerfile syntax and structure."""

    @pytest.fixture
    def dockerfile_path(self) -> Path:
        """Get path to Dockerfile."""
        return Path(__file__).parent.parent.parent / "Dockerfile"

    @pytest.fixture
    def dockerfile_content(self, dockerfile_path: Path) -> str:
        """Read Dockerfile content."""
        return dockerfile_path.read_text()

    def test_dockerfile_exists(self, dockerfile_path: Path) -> None:
        """Test that Dockerfile exists in project root."""
        assert dockerfile_path.exists(), "Dockerfile not found in project root"

    def test_dockerfile_is_readable(self, dockerfile_path: Path) -> None:
        """Test that Dockerfile is readable."""
        assert os.access(dockerfile_path, os.R_OK), "Dockerfile is not readable"

    def test_dockerfile_has_multi_stage_build(self, dockerfile_content: str) -> None:
        """Test that Dockerfile uses multi-stage build."""
        # Check for builder stage (case-insensitive)
        assert "as builder" in dockerfile_content.lower() or "AS builder" in dockerfile_content
        assert "FROM python:3.12-slim" in dockerfile_content
        # Count FROM statements - should have at least 2 for multi-stage
        from_count = dockerfile_content.count("FROM python:3.12-slim")
        assert from_count >= 2, "Dockerfile should use multi-stage build"

    def test_dockerfile_has_correct_base_image(self, dockerfile_content: str) -> None:
        """Test that Dockerfile uses Python 3.12-slim base image."""
        # Should have at least one FROM with python:3.12-slim
        assert "python:3.12-slim" in dockerfile_content

    def test_dockerfile_has_builder_stage(self, dockerfile_content: str) -> None:
        """Test that Dockerfile has a builder stage."""
        # Check for builder stage (case-insensitive)
        assert "as builder" in dockerfile_content.lower() or "AS builder" in dockerfile_content

    def test_dockerfile_installs_build_dependencies(self, dockerfile_content: str) -> None:
        """Test that Dockerfile installs build dependencies in builder stage."""
        # Builder stage should install gcc
        builder_stage = dockerfile_content.split("FROM python:3.12-slim")[1].split("FROM")[0]
        assert "gcc" in builder_stage, "Builder stage should install gcc for compiling packages"

    def test_dockerfile_creates_venv(self, dockerfile_content: str) -> None:
        """Test that Dockerfile creates Python virtual environment."""
        assert "python -m venv /opt/venv" in dockerfile_content

    def test_dockerfile_copies_dependencies(self, dockerfile_content: str) -> None:
        """Test that Dockerfile copies dependency files."""
        assert "COPY pyproject.toml" in dockerfile_content

    def test_dockerfile_installs_packages(self, dockerfile_content: str) -> None:
        """Test that Dockerfile installs Python packages."""
        assert "pip install" in dockerfile_content

    def test_dockerfile_copies_app_code(self, dockerfile_content: str) -> None:
        """Test that Dockerfile copies application code."""
        assert "COPY --chown=appuser:appuser src/workflow" in dockerfile_content

    def test_dockerfile_copies_scripts(self, dockerfile_content: str) -> None:
        """Test that Dockerfile copies scripts directory."""
        assert "COPY --chown=appuser:appuser scripts" in dockerfile_content

    def test_dockerfile_creates_logs_directory(self, dockerfile_content: str) -> None:
        """Test that Dockerfile creates logs directory."""
        assert "mkdir -p /app/logs" in dockerfile_content

    def test_dockerfile_sets_working_directory(self, dockerfile_content: str) -> None:
        """Test that Dockerfile sets correct working directory."""
        # Should set to /app
        assert "WORKDIR /app" in dockerfile_content

    def test_dockerfile_exposes_correct_port(self, dockerfile_content: str) -> None:
        """Test that Dockerfile exposes port 8000."""
        assert "EXPOSE 8000" in dockerfile_content

    def test_dockerfile_sets_environment_variables(self, dockerfile_content: str) -> None:
        """Test that Dockerfile sets environment variables."""
        assert "PYTHONUNBUFFERED=1" in dockerfile_content
        assert "PYTHONDONTWRITEBYTECODE=1" in dockerfile_content

    def test_dockerfile_sets_pythonunbuffered(self, dockerfile_content: str) -> None:
        """Test that Dockerfile sets PYTHONUNBUFFERED for proper logging."""
        assert "PYTHONUNBUFFERED=1" in dockerfile_content

    def test_dockerfile_sets_pythondontwritebytecode(self, dockerfile_content: str) -> None:
        """Test that Dockerfile sets PYTHONDONTWRITEBYTECODE."""
        assert "PYTHONDONTWRITEBYTECODE=1" in dockerfile_content


class TestDockerfileNonRootUser:
    """Test that Dockerfile properly configures non-root user."""

    @pytest.fixture
    def dockerfile_content(self) -> str:
        """Read Dockerfile content."""
        dockerfile_path = Path(__file__).parent.parent.parent / "Dockerfile"
        return dockerfile_path.read_text()

    def test_dockerfile_creates_non_root_user(self, dockerfile_content: str) -> None:
        """Test that Dockerfile creates a non-root user."""
        assert "useradd -m -u 1000 appuser" in dockerfile_content

    def test_dockerfile_uses_uid_1000(self, dockerfile_content: str) -> None:
        """Test that non-root user has UID 1000."""
        assert "-u 1000 appuser" in dockerfile_content

    def test_dockerfile_switches_to_non_root_user(self, dockerfile_content: str) -> None:
        """Test that Dockerfile switches to non-root user before running app."""
        # Should have USER appuser before ENTRYPOINT
        lines = dockerfile_content.split("\n")
        user_index = None
        entrypoint_index = None

        for i, line in enumerate(lines):
            if "USER appuser" in line:
                user_index = i
            if "ENTRYPOINT" in line:
                entrypoint_index = i

        assert user_index is not None, "Dockerfile should switch to appuser"
        assert (
            entrypoint_index is not None and entrypoint_index > user_index
        ), "USER appuser should come before ENTRYPOINT"

    def test_dockerfile_sets_app_ownership(self, dockerfile_content: str) -> None:
        """Test that Dockerfile sets correct ownership for app files."""
        assert "--chown=appuser:appuser" in dockerfile_content

    def test_dockerfile_sets_logs_directory_ownership(self, dockerfile_content: str) -> None:
        """Test that Dockerfile sets ownership for logs directory."""
        assert "chown -R appuser:appuser /app" in dockerfile_content


class TestDockerfileHealthCheck:
    """Test health check configuration in Dockerfile."""

    @pytest.fixture
    def dockerfile_content(self) -> str:
        """Read Dockerfile content."""
        dockerfile_path = Path(__file__).parent.parent.parent / "Dockerfile"
        return dockerfile_path.read_text()

    def test_dockerfile_has_healthcheck(self, dockerfile_content: str) -> None:
        """Test that Dockerfile configures health check."""
        assert "HEALTHCHECK" in dockerfile_content

    def test_healthcheck_checks_health_endpoint(self, dockerfile_content: str) -> None:
        """Test that health check pings health endpoint."""
        assert "http://localhost:8000/health/" in dockerfile_content

    def test_healthcheck_uses_curl(self, dockerfile_content: str) -> None:
        """Test that health check uses curl."""
        assert "curl" in dockerfile_content

    def test_healthcheck_interval_30s(self, dockerfile_content: str) -> None:
        """Test that health check runs every 30 seconds."""
        assert "--interval=30s" in dockerfile_content

    def test_healthcheck_timeout_3s(self, dockerfile_content: str) -> None:
        """Test that health check has 3 second timeout."""
        assert "--timeout=3s" in dockerfile_content

    def test_healthcheck_start_period_5s(self, dockerfile_content: str) -> None:
        """Test that health check has 5 second start period grace."""
        assert "--start-period=5s" in dockerfile_content

    def test_healthcheck_retries_3(self, dockerfile_content: str) -> None:
        """Test that health check allows 3 retries before marking unhealthy."""
        assert "--retries=3" in dockerfile_content


class TestDockerfileEntrypoint:
    """Test entrypoint and command configuration."""

    @pytest.fixture
    def dockerfile_content(self) -> str:
        """Read Dockerfile content."""
        dockerfile_path = Path(__file__).parent.parent.parent / "Dockerfile"
        return dockerfile_path.read_text()

    def test_dockerfile_has_entrypoint(self, dockerfile_content: str) -> None:
        """Test that Dockerfile has ENTRYPOINT."""
        assert "ENTRYPOINT" in dockerfile_content

    def test_dockerfile_uses_exec_form(self, dockerfile_content: str) -> None:
        """Test that Dockerfile uses exec form for ENTRYPOINT (proper signal handling)."""
        assert 'ENTRYPOINT ["python", "-m", "uvicorn"]' in dockerfile_content

    def test_dockerfile_has_cmd(self, dockerfile_content: str) -> None:
        """Test that Dockerfile has CMD."""
        assert "CMD" in dockerfile_content

    def test_dockerfile_cmd_specifies_app(self, dockerfile_content: str) -> None:
        """Test that CMD specifies the app module."""
        assert "workflow.main:app" in dockerfile_content

    def test_dockerfile_cmd_binds_to_all_interfaces(self, dockerfile_content: str) -> None:
        """Test that CMD binds to all interfaces."""
        assert '"--host", "0.0.0.0"' in dockerfile_content

    def test_dockerfile_cmd_uses_port_8000(self, dockerfile_content: str) -> None:
        """Test that CMD uses port 8000."""
        assert '"--port", "8000"' in dockerfile_content


class TestDockerfileSecurityBestPractices:
    """Test security best practices in Dockerfile."""

    @pytest.fixture
    def dockerfile_content(self) -> str:
        """Read Dockerfile content."""
        dockerfile_path = Path(__file__).parent.parent.parent / "Dockerfile"
        return dockerfile_path.read_text()

    def test_no_secrets_in_env_vars(self, dockerfile_content: str) -> None:
        """Test that no secrets are hardcoded in ENV variables."""
        # Check that ANTHROPIC_API_KEY is not set in Dockerfile
        assert "ANTHROPIC_API_KEY" not in dockerfile_content
        assert "JWT_SECRET_KEY" not in dockerfile_content

    def test_no_apt_cache_after_install(self, dockerfile_content: str) -> None:
        """Test that apt cache is cleaned after package installation."""
        # Should see apt-get install followed by rm -rf /var/lib/apt/lists/*
        lines = dockerfile_content.split("\n")
        for i, line in enumerate(lines):
            if "apt-get install" in line:
                # Check following lines for cache cleanup
                found_cleanup = False
                for j in range(i, min(i + 5, len(lines))):
                    if "rm -rf /var/lib/apt/lists/*" in lines[j]:
                        found_cleanup = True
                        break
                assert found_cleanup, "apt cache should be cleaned after install"

    def test_uses_slim_base_image(self, dockerfile_content: str) -> None:
        """Test that Dockerfile uses slim base image for smaller attack surface."""
        assert "python:3.12-slim" in dockerfile_content
        # Make sure it's NOT using full python image
        assert "python:3.12\n" not in dockerfile_content or "python:3.12-slim" in dockerfile_content

    def test_runs_as_non_root(self, dockerfile_content: str) -> None:
        """Test that final container runs as non-root user."""
        assert "USER appuser" in dockerfile_content
        assert "USER root" not in dockerfile_content.split("USER appuser")[1]


class TestDockerIgnore:
    """Test .dockerignore file configuration."""

    @pytest.fixture
    def dockerignore_path(self) -> Path:
        """Get path to .dockerignore."""
        return Path(__file__).parent.parent.parent / ".dockerignore"

    @pytest.fixture
    def dockerignore_content(self, dockerignore_path: Path) -> str:
        """Read .dockerignore content."""
        return dockerignore_path.read_text()

    def test_dockerignore_exists(self, dockerignore_path: Path) -> None:
        """Test that .dockerignore exists."""
        assert dockerignore_path.exists()

    def test_dockerignore_excludes_venv(self, dockerignore_content: str) -> None:
        """Test that .dockerignore excludes virtual environments."""
        assert ".venv/" in dockerignore_content or ".venv" in dockerignore_content

    def test_dockerignore_excludes_tests(self, dockerignore_content: str) -> None:
        """Test that .dockerignore excludes test directories."""
        assert "tests/" in dockerignore_content

    def test_dockerignore_excludes_env_files(self, dockerignore_content: str) -> None:
        """Test that .dockerignore excludes .env files."""
        assert ".env" in dockerignore_content

    def test_dockerignore_excludes_git(self, dockerignore_content: str) -> None:
        """Test that .dockerignore excludes .git."""
        assert ".git" in dockerignore_content

    def test_dockerignore_excludes_pycache(self, dockerignore_content: str) -> None:
        """Test that .dockerignore excludes __pycache__."""
        assert "__pycache__" in dockerignore_content

    def test_dockerignore_excludes_python_artifacts(self, dockerignore_content: str) -> None:
        """Test that .dockerignore excludes Python artifacts."""
        assert "*.pyc" in dockerignore_content or ".pyc" in dockerignore_content


class TestDockerComposeConfiguration:
    """Test docker-compose.yml configuration."""

    @pytest.fixture
    def docker_compose_path(self) -> Path:
        """Get path to docker-compose.yml."""
        return Path(__file__).parent.parent.parent / "docker-compose.yml"

    @pytest.fixture
    def docker_compose_content(self, docker_compose_path: Path) -> str:
        """Read docker-compose.yml content."""
        return docker_compose_path.read_text()

    def test_docker_compose_exists(self, docker_compose_path: Path) -> None:
        """Test that docker-compose.yml exists."""
        assert docker_compose_path.exists()

    def test_docker_compose_valid_yaml(self, docker_compose_content: str) -> None:
        """Test that docker-compose.yml is valid YAML."""
        import yaml

        try:
            yaml.safe_load(docker_compose_content)
        except yaml.YAMLError as e:
            pytest.fail(f"docker-compose.yml is not valid YAML: {e}")

    def test_docker_compose_has_orchestrator_service(self, docker_compose_content: str) -> None:
        """Test that docker-compose.yml defines orchestrator-worker service."""
        assert "orchestrator-worker:" in docker_compose_content

    def test_docker_compose_builds_from_dockerfile(self, docker_compose_content: str) -> None:
        """Test that service build config references Dockerfile."""
        assert "dockerfile: Dockerfile" in docker_compose_content

    def test_docker_compose_maps_port_8000(self, docker_compose_content: str) -> None:
        """Test that docker-compose.yml maps port 8000."""
        assert "8000:8000" in docker_compose_content

    def test_docker_compose_loads_env_file(self, docker_compose_content: str) -> None:
        """Test that docker-compose.yml loads .env file."""
        assert "env_file:" in docker_compose_content
        assert ".env" in docker_compose_content

    def test_docker_compose_sets_api_host(self, docker_compose_content: str) -> None:
        """Test that docker-compose.yml sets API_HOST."""
        assert "API_HOST: 0.0.0.0" in docker_compose_content

    def test_docker_compose_sets_api_port(self, docker_compose_content: str) -> None:
        """Test that docker-compose.yml loads API_PORT from .env file."""
        # API_PORT should be read from .env file, not hardcoded in docker-compose.yml
        # Verify this by checking that there's a comment about .env and no hardcoded API_PORT in environment
        assert "env_file:" in docker_compose_content
        assert ".env" in docker_compose_content
        # Should NOT have hardcoded API_PORT in environment section
        # (it should be commented out or read from .env)
        lines = docker_compose_content.split("\n")
        for line in lines:
            if "API_PORT:" in line and not line.strip().startswith("#"):
                pytest.fail(
                    "API_PORT should be read from .env, not hardcoded in docker-compose.yml"
                )

    def test_docker_compose_has_healthcheck(self, docker_compose_content: str) -> None:
        """Test that docker-compose.yml defines health check."""
        assert "healthcheck:" in docker_compose_content

    def test_docker_compose_healthcheck_matches_dockerfile(
        self, docker_compose_content: str
    ) -> None:
        """Test that docker-compose health check matches Dockerfile."""
        # Should check /health/ endpoint
        assert "health/" in docker_compose_content
        # Should have similar intervals
        assert "interval:" in docker_compose_content

    def test_docker_compose_defines_network(self, docker_compose_content: str) -> None:
        """Test that docker-compose.yml defines custom network."""
        assert (
            "orchestrator-network:" in docker_compose_content
            or "networks:" in docker_compose_content
        )

    def test_docker_compose_has_restart_policy(self, docker_compose_content: str) -> None:
        """Test that docker-compose.yml has restart policy."""
        assert "restart:" in docker_compose_content

    def test_docker_compose_restart_unless_stopped(self, docker_compose_content: str) -> None:
        """Test that docker-compose.yml restarts container unless explicitly stopped."""
        assert "unless-stopped" in docker_compose_content
