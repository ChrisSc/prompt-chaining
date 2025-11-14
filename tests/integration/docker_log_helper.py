"""
Docker log parsing and verification utilities for integration testing.

Provides helpers to:
- Extract logs from running Docker containers
- Parse JSON-formatted logs
- Filter by log level
- Verify log structure and fields
"""

import json
import subprocess
from typing import Any


def get_docker_logs(container_name: str = "prompt-chaining-api") -> str:
    """
    Get logs from a running Docker container.

    Args:
        container_name: Name of the container to retrieve logs from

    Returns:
        Raw log output as string

    Raises:
        RuntimeError: If docker logs command fails
    """
    try:
        # First try docker logs command directly with container name
        result = subprocess.run(
            ["docker", "logs", container_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout

        # Fallback: try docker-compose logs from project directory
        result = subprocess.run(
            ["docker-compose", "logs"],
            cwd="/Users/chris/Projects/prompt-chaining",
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to get logs from {container_name}: {result.stderr}")
        return result.stdout

    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"Timeout retrieving logs: {e}")
    except Exception as e:
        raise RuntimeError(f"Error retrieving logs: {e}")


def parse_json_logs(log_output: str) -> list[dict[str, Any]]:
    """
    Parse JSON-formatted logs from raw output.

    Skips non-JSON lines (like Uvicorn access logs) and parses valid JSON objects.

    Args:
        log_output: Raw log output containing JSON lines and possibly other text

    Returns:
        List of parsed log dictionaries
    """
    logs = []
    skipped_lines = 0
    for line in log_output.strip().split("\n"):
        if not line.strip():
            continue
        try:
            logs.append(json.loads(line))
        except json.JSONDecodeError:
            # Skip non-JSON lines (e.g., Uvicorn access logs, startup messages)
            skipped_lines += 1
    return logs


def filter_logs_by_level(logs: list[dict[str, Any]], level: str) -> list[dict[str, Any]]:
    """
    Filter logs by level.

    Args:
        logs: List of parsed log dictionaries
        level: Log level to filter by (e.g., "CRITICAL", "ERROR", "WARNING", "INFO")

    Returns:
        Filtered list of logs matching the specified level
    """
    return [log for log in logs if log.get("level") == level.upper()]


def filter_logs_by_message(
    logs: list[dict[str, Any]], message_pattern: str
) -> list[dict[str, Any]]:
    """
    Filter logs by message content (substring match).

    Args:
        logs: List of parsed log dictionaries
        message_pattern: Substring to search for in log messages

    Returns:
        Filtered list of logs containing the pattern
    """
    return [log for log in logs if message_pattern in log.get("message", "")]


def verify_log_structure(
    log: dict[str, Any],
    required_fields: list[str] | None = None,
    optional_fields: list[str] | None = None,
) -> bool:
    """
    Verify that a log entry has required structure.

    Args:
        log: Log dictionary to verify
        required_fields: Fields that must be present (default: standard fields)
        optional_fields: Fields that may be present

    Returns:
        True if log structure is valid

    Raises:
        AssertionError: If required fields are missing
    """
    if required_fields is None:
        required_fields = ["timestamp", "level", "logger", "message"]

    # Check required fields
    for field in required_fields:
        assert field in log, f"Missing required field '{field}' in log: {log}"

    # Verify level is valid
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    assert log.get("level") in valid_levels, f"Invalid log level: {log.get('level')}"

    return True


def assert_log_contains_extra_fields(
    log: dict[str, Any],
    expected_fields: dict[str, Any],
) -> None:
    """
    Assert that a log contains expected extra fields and values.

    Args:
        log: Log dictionary to verify
        expected_fields: Dictionary of field_name -> expected_value

    Raises:
        AssertionError: If fields are missing or values don't match
    """
    for field, expected_value in expected_fields.items():
        assert field in log, (
            f"Missing extra field '{field}' in log. " f"Log keys: {list(log.keys())}"
        )
        actual_value = log.get(field)
        assert (
            actual_value == expected_value
        ), f"Field '{field}': expected {expected_value}, got {actual_value}"


def get_container_exit_code(container_name: str = "prompt-chaining-api") -> int:
    """
    Get the exit code of a Docker container.

    Args:
        container_name: Name of the container

    Returns:
        Exit code of the container (0 if running, non-zero if exited)

    Raises:
        RuntimeError: If command fails
    """
    try:
        result = subprocess.run(
            ["docker", "inspect", container_name, "--format={{.State.ExitCode}}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Container not found or inspect failed: {container_name}")
        return int(result.stdout.strip())
    except ValueError as e:
        raise RuntimeError(f"Failed to parse exit code: {e}")
    except Exception as e:
        raise RuntimeError(f"Error getting container exit code: {e}")


def container_is_running(container_name: str = "prompt-chaining-api") -> bool:
    """
    Check if a Docker container is currently running.

    Args:
        container_name: Name of the container

    Returns:
        True if container is running, False otherwise
    """
    try:
        result = subprocess.run(
            [
                "docker",
                "inspect",
                container_name,
                "--format={{.State.Running}}",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip().lower() == "true"
    except Exception:
        return False


def wait_for_container_exit(container_name: str = "prompt-chaining-api", timeout: int = 30) -> int:
    """
    Wait for a container to stop and return its exit code.

    Args:
        container_name: Name of the container
        timeout: Maximum time to wait in seconds

    Returns:
        Exit code of the container

    Raises:
        TimeoutError: If container doesn't exit within timeout
        RuntimeError: If command fails
    """
    import time

    start_time = time.time()
    while time.time() - start_time < timeout:
        if not container_is_running(container_name):
            return get_container_exit_code(container_name)
        time.sleep(0.5)

    raise TimeoutError(f"Container {container_name} did not exit within {timeout} seconds")
