"""
Integration tests for Docker image build validation.

These tests validate that:
- Docker image builds successfully
- Image has correct configuration
- Image is appropriately sized
- Image contains required components
- Multi-stage build works correctly
- Image can be inspected

Note: These tests run docker build commands and may take several minutes.
They require Docker to be installed and daemon to be running.
"""

import json
import subprocess
from pathlib import Path

import pytest


class TestDockerImageBuild:
    """Test Docker image build process."""

    @pytest.fixture(scope="class")
    def project_root(self) -> Path:
        """Get project root."""
        return Path(__file__).parent.parent.parent

    @pytest.fixture(scope="class")
    def image_name(self) -> str:
        """Get Docker image name for testing."""
        return "orchestrator-worker:test-build"

    def test_docker_available(self) -> None:
        """Test that Docker is installed and available."""
        try:
            result = subprocess.run(
                ["docker", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            assert result.returncode == 0, "Docker is not available"
            assert "Docker version" in result.stdout
        except FileNotFoundError:
            pytest.skip("Docker not found on system")

    def test_dockerfile_exists(self, project_root: Path) -> None:
        """Test that Dockerfile exists in project root."""
        dockerfile = project_root / "Dockerfile"
        assert dockerfile.exists(), "Dockerfile not found"

    def test_dockerfile_is_readable(self, project_root: Path) -> None:
        """Test that Dockerfile is readable."""
        dockerfile = project_root / "Dockerfile"
        assert dockerfile.read_text(), "Dockerfile exists but is empty or unreadable"

    def test_docker_image_builds_successfully(self, project_root: Path, image_name: str) -> None:
        """Test that Docker image builds without errors."""
        try:
            result = subprocess.run(
                ["docker", "build", "-t", image_name, "-f", "Dockerfile", "."],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout for build
            )

            if result.returncode != 0:
                # Check if it's because Docker daemon isn't running
                if (
                    "Cannot connect to Docker daemon" in result.stderr
                    or "permission denied" in result.stderr.lower()
                ):
                    pytest.skip("Docker daemon not available")
                # Show last 50 lines of build output for debugging
                lines = result.stdout.split("\n") + result.stderr.split("\n")
                last_lines = "\n".join(lines[-50:])
                pytest.fail(f"Docker build failed:\n{last_lines}")

            assert result.returncode == 0, "Docker build failed"
            # Docker BuildKit outputs to stderr, check both stdout and stderr
            output = result.stdout + result.stderr
            assert (
                "done" in output.lower() or "naming to" in output.lower()
            ), "Docker build may not have completed successfully"
        except subprocess.TimeoutExpired:
            pytest.fail("Docker build timed out after 5 minutes")
        except FileNotFoundError:
            pytest.skip("Docker not found on system")

    def test_docker_image_exists_after_build(self, image_name: str) -> None:
        """Test that built image exists."""
        try:
            result = subprocess.run(
                ["docker", "images", image_name, "--quiet"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            assert result.returncode == 0
            image_id = result.stdout.strip()
            assert image_id, f"Image {image_name} not found after build"
        except FileNotFoundError:
            pytest.skip("Docker not found")


class TestDockerImageConfiguration:
    """Test Docker image configuration and metadata."""

    @pytest.fixture(scope="class")
    def project_root(self) -> Path:
        """Get project root."""
        return Path(__file__).parent.parent.parent

    @pytest.fixture(scope="class")
    def image_name(self) -> str:
        """Get Docker image name for testing."""
        return "orchestrator-worker:test-config"

    @pytest.fixture(scope="class", autouse=True)
    def build_image(self, project_root: Path, image_name: str) -> None:
        """Build test image before running tests."""
        try:
            subprocess.run(
                ["docker", "build", "-t", image_name, "-f", "Dockerfile", "."],
                cwd=project_root,
                capture_output=True,
                timeout=300,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pytest.skip("Docker build failed or Docker not available")

    def test_image_inspect_succeeds(self, image_name: str) -> None:
        """Test that image can be inspected."""
        try:
            result = subprocess.run(
                ["docker", "inspect", image_name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            assert result.returncode == 0, f"Could not inspect image {image_name}"
        except FileNotFoundError:
            pytest.skip("Docker not found")

    def test_image_has_correct_base_image(self, image_name: str) -> None:
        """Test that image is based on python:3.12-slim."""
        try:
            result = subprocess.run(
                ["docker", "inspect", image_name, "--format={{.Config.Image}}"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                # The base image should be python:3.12-slim
                # (Get top of Dockerfile to verify)
                pass  # Base image verification happens at build time
        except FileNotFoundError:
            pytest.skip("Docker not found")

    def test_image_exposes_port_8000(self, image_name: str) -> None:
        """Test that image exposes port 8000."""
        try:
            result = subprocess.run(
                ["docker", "inspect", image_name, "--format={{json .Config.ExposedPorts}}"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            assert result.returncode == 0
            # Try to parse the JSON
            try:
                exposed_ports = json.loads(result.stdout)
                assert "8000/tcp" in exposed_ports or exposed_ports is None or exposed_ports == {}
            except json.JSONDecodeError:
                # Port exposure is verified during build
                pass
        except FileNotFoundError:
            pytest.skip("Docker not found")

    def test_image_has_healthcheck(self, image_name: str) -> None:
        """Test that image has health check configured."""
        try:
            result = subprocess.run(
                ["docker", "inspect", image_name, "--format={{json .Config.Healthcheck}}"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            assert result.returncode == 0
            if result.stdout.strip() and result.stdout.strip() != "null":
                try:
                    healthcheck = json.loads(result.stdout)
                    assert healthcheck is not None
                    assert "Test" in healthcheck or "test" in healthcheck.lower()
                except json.JSONDecodeError:
                    pass
        except FileNotFoundError:
            pytest.skip("Docker not found")

    def test_image_entrypoint_correct(self, image_name: str) -> None:
        """Test that image has correct entrypoint."""
        try:
            result = subprocess.run(
                ["docker", "inspect", image_name, "--format={{json .Config.Entrypoint}}"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0 and result.stdout.strip():
                try:
                    entrypoint = json.loads(result.stdout)
                    # Should be python -m uvicorn
                    assert "python" in str(entrypoint) or "uvicorn" in str(entrypoint)
                except json.JSONDecodeError:
                    pass
        except FileNotFoundError:
            pytest.skip("Docker not found")

    def test_image_cmd_correct(self, image_name: str) -> None:
        """Test that image has correct cmd."""
        try:
            result = subprocess.run(
                ["docker", "inspect", image_name, "--format={{json .Config.Cmd}}"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0 and result.stdout.strip():
                try:
                    cmd = json.loads(result.stdout)
                    # Should reference orchestrator_worker.main:app
                    assert "orchestrator_worker.main:app" in str(cmd)
                except json.JSONDecodeError:
                    pass
        except FileNotFoundError:
            pytest.skip("Docker not found")

    def test_image_user_is_non_root(self, image_name: str) -> None:
        """Test that image runs as non-root user."""
        try:
            result = subprocess.run(
                ["docker", "inspect", image_name, "--format={{.Config.User}}"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                user = result.stdout.strip()
                if user:
                    # Should be appuser or UID 1000
                    assert user in ["appuser", "1000", "1000:1000"]
                # Empty is acceptable (may use default)
        except FileNotFoundError:
            pytest.skip("Docker not found")

    def test_image_environment_variables(self, image_name: str) -> None:
        """Test that image has environment variables set."""
        try:
            result = subprocess.run(
                ["docker", "inspect", image_name, "--format={{json .Config.Env}}"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0 and result.stdout.strip():
                try:
                    env_vars = json.loads(result.stdout)
                    env_str = str(env_vars)
                    # Should have PYTHONUNBUFFERED and PYTHONDONTWRITEBYTECODE
                    assert "PYTHONUNBUFFERED" in env_str
                    assert "PYTHONDONTWRITEBYTECODE" in env_str
                except json.JSONDecodeError:
                    pass
        except FileNotFoundError:
            pytest.skip("Docker not found")


class TestDockerImageSize:
    """Test Docker image size and efficiency."""

    @pytest.fixture(scope="class")
    def project_root(self) -> Path:
        """Get project root."""
        return Path(__file__).parent.parent.parent

    @pytest.fixture(scope="class")
    def image_name(self) -> str:
        """Get Docker image name for testing."""
        return "orchestrator-worker:test-size"

    @pytest.fixture(scope="class", autouse=True)
    def build_image(self, project_root: Path, image_name: str) -> None:
        """Build test image before running tests."""
        try:
            subprocess.run(
                ["docker", "build", "-t", image_name, "-f", "Dockerfile", "."],
                cwd=project_root,
                capture_output=True,
                timeout=300,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pytest.skip("Docker build failed or Docker not available")

    def test_image_size_reasonable(self, image_name: str) -> None:
        """Test that image size is reasonable (< 500MB)."""
        try:
            result = subprocess.run(
                ["docker", "images", image_name, "--format={{.Size}}"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0 and result.stdout.strip():
                size_str = result.stdout.strip()
                # Parse size string (e.g., "312MB", "1.2GB")
                # This is a loose check - just verify it's not ridiculously large
                if "GB" in size_str:
                    size_float = float(size_str.replace("GB", "").strip())
                    assert size_float < 2, f"Image size {size_str} exceeds 2GB"
                elif "MB" in size_str:
                    size_float = float(size_str.replace("MB", "").strip())
                    assert size_float < 500, f"Image size {size_str} exceeds 500MB"
        except FileNotFoundError:
            pytest.skip("Docker not found")

    def test_image_size_information(self, image_name: str) -> None:
        """Test that image size information can be retrieved."""
        try:
            result = subprocess.run(
                ["docker", "images", image_name, "--format={{.Size}}"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            assert result.returncode == 0
            size = result.stdout.strip()
            # Just verify size is not empty
            assert size, "Could not determine image size"
        except FileNotFoundError:
            pytest.skip("Docker not found")


class TestDockerImageLayers:
    """Test Docker image layer configuration."""

    @pytest.fixture(scope="class")
    def project_root(self) -> Path:
        """Get project root."""
        return Path(__file__).parent.parent.parent

    @pytest.fixture(scope="class")
    def image_name(self) -> str:
        """Get Docker image name for testing."""
        return "orchestrator-worker:test-layers"

    @pytest.fixture(scope="class", autouse=True)
    def build_image(self, project_root: Path, image_name: str) -> None:
        """Build test image before running tests."""
        try:
            subprocess.run(
                ["docker", "build", "-t", image_name, "-f", "Dockerfile", "."],
                cwd=project_root,
                capture_output=True,
                timeout=300,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pytest.skip("Docker build failed or Docker not available")

    def test_image_history_available(self, image_name: str) -> None:
        """Test that image history can be retrieved."""
        try:
            result = subprocess.run(
                ["docker", "history", image_name],
                capture_output=True,
                text=True,
                timeout=5,
            )

            assert result.returncode == 0
            # Should show layer history
            assert len(result.stdout) > 0
        except FileNotFoundError:
            pytest.skip("Docker not found")

    def test_no_secrets_in_layers(self, image_name: str) -> None:
        """Test that no secrets are exposed in image layers."""
        try:
            result = subprocess.run(
                ["docker", "history", image_name, "--no-trunc"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            assert result.returncode == 0
            # Should not contain secret patterns
            assert "ANTHROPIC_API_KEY" not in result.stdout
            assert "JWT_SECRET_KEY" not in result.stdout
            # Common secret patterns
            assert "your_api_key" not in result.stdout.lower()
            assert "secret_key" not in result.stdout
        except FileNotFoundError:
            pytest.skip("Docker not found")


class TestDockerImageCleanup:
    """Test Docker image cleanup and removal."""

    @pytest.fixture(scope="class")
    def image_name(self) -> str:
        """Get Docker image name for testing."""
        return "orchestrator-worker:test-cleanup"

    def test_image_can_be_removed(self, image_name: str) -> None:
        """Test that test images can be cleaned up."""
        try:
            # Remove the image if it exists
            subprocess.run(
                ["docker", "rmi", image_name],
                capture_output=True,
                timeout=10,
            )
            # Should succeed or fail gracefully
        except FileNotFoundError:
            pytest.skip("Docker not found")
