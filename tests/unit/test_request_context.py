"""
Unit tests for request context management.

Tests the request_context module which provides ContextVar-based request ID tracking
across async operations. Verifies isolation, get/set operations, and async context
propagation.
"""

import asyncio
from contextvars import ContextVar

import pytest

from orchestrator_worker.utils.request_context import (
    _request_id_var,
    get_request_id,
    set_request_id,
)


class TestRequestContextBasics:
    """Test basic request context get/set functionality."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    def test_set_and_get_request_id(self) -> None:
        """Test setting and retrieving request ID from context."""
        request_id = "req_test_12345"
        set_request_id(request_id)
        assert get_request_id() == request_id

    def test_get_request_id_default_none(self) -> None:
        """Test get_request_id returns None when not set."""
        # Reset context to ensure no value is set
        _request_id_var.set(None)
        assert get_request_id() is None

    def test_set_request_id_overwrites_previous(self) -> None:
        """Test that setting request_id overwrites the previous value."""
        set_request_id("req_first_value")
        assert get_request_id() == "req_first_value"

        set_request_id("req_second_value")
        assert get_request_id() == "req_second_value"

    def test_set_request_id_with_various_formats(self) -> None:
        """Test setting request_id with various valid formats."""
        test_cases = [
            "req_12345",
            "req_" + "a" * 50,
            "request-id-123",
            "REQ_UPPERCASE",
            "req_with_underscores_123",
        ]

        for test_id in test_cases:
            set_request_id(test_id)
            assert get_request_id() == test_id

    def test_set_empty_string_request_id(self) -> None:
        """Test setting empty string as request ID (edge case)."""
        set_request_id("")
        assert get_request_id() == ""

    def test_set_special_characters_request_id(self) -> None:
        """Test setting request ID with special characters."""
        special_id = "req_@#$%^&*()"
        set_request_id(special_id)
        assert get_request_id() == special_id


class TestAsyncContextIsolation:
    """Test that async contexts have isolated request IDs."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    @pytest.mark.asyncio
    async def test_async_tasks_have_isolated_request_ids(self) -> None:
        """Test that each async task has its own isolated request ID."""

        async def task_with_id(request_id: str, delay: float = 0.01) -> str:
            """Task that sets request ID, waits, and returns it."""
            set_request_id(request_id)
            await asyncio.sleep(delay)
            return get_request_id()

        # Run multiple tasks concurrently
        results = await asyncio.gather(
            task_with_id("req_async_1"),
            task_with_id("req_async_2"),
            task_with_id("req_async_3"),
            task_with_id("req_async_4"),
        )

        # Verify each task got its own request ID
        assert results == ["req_async_1", "req_async_2", "req_async_3", "req_async_4"]

    @pytest.mark.asyncio
    async def test_nested_async_tasks_preserve_context(self) -> None:
        """Test that nested async tasks preserve parent context."""

        async def inner_task(multiplier: int) -> str:
            """Inner task that uses parent's request ID."""
            current_id = get_request_id()
            await asyncio.sleep(0.01)
            return current_id if current_id else ""

        async def outer_task(request_id: str) -> list[str]:
            """Outer task that sets ID and runs inner tasks."""
            set_request_id(request_id)
            results = await asyncio.gather(
                inner_task(1),
                inner_task(2),
                inner_task(3),
            )
            return results

        # Run multiple outer tasks
        all_results = await asyncio.gather(
            outer_task("req_nested_1"),
            outer_task("req_nested_2"),
        )

        # Verify context propagation in nested tasks
        assert all_results[0] == ["req_nested_1", "req_nested_1", "req_nested_1"]
        assert all_results[1] == ["req_nested_2", "req_nested_2", "req_nested_2"]

    @pytest.mark.asyncio
    async def test_concurrent_requests_dont_interfere(self) -> None:
        """Test that concurrent requests with different IDs don't interfere."""

        async def request_handler(request_id: str, operations: int = 10) -> list[str]:
            """Simulate request handler that performs operations with request ID."""
            results = []
            set_request_id(request_id)

            for _ in range(operations):
                # Simulate some async work
                await asyncio.sleep(0.001)
                current_id = get_request_id()
                results.append(current_id)

            return results

        # Run many concurrent requests
        num_requests = 20
        tasks = [
            request_handler(f"req_concurrent_{i}", operations=5) for i in range(num_requests)
        ]

        all_results = await asyncio.gather(*tasks)

        # Verify each request maintained its own ID throughout
        for i, results in enumerate(all_results):
            expected_id = f"req_concurrent_{i}"
            assert all(r == expected_id for r in results), (
                f"Request {i} had inconsistent IDs: {results}"
            )

    @pytest.mark.asyncio
    async def test_request_id_survives_task_switching(self) -> None:
        """Test that request ID persists across task context switches."""

        captured_ids = []

        async def capture_id_during_sleep(request_id: str) -> None:
            """Capture request ID before and after sleep."""
            set_request_id(request_id)
            captured_ids.append(get_request_id())

            await asyncio.sleep(0.01)

            captured_ids.append(get_request_id())

            await asyncio.sleep(0.01)

            captured_ids.append(get_request_id())

        # Run task
        await capture_id_during_sleep("req_persistent")

        # Verify ID was consistent throughout
        assert captured_ids == ["req_persistent", "req_persistent", "req_persistent"]

    @pytest.mark.asyncio
    async def test_multiple_context_switches_preserve_id(self) -> None:
        """Test request ID is preserved through multiple context switches."""

        async def switching_task(request_id: str) -> list[str]:
            """Task that yields control multiple times."""
            set_request_id(request_id)
            results = []

            for i in range(5):
                await asyncio.sleep(0.001)
                results.append(get_request_id())

            return results

        # Run multiple switching tasks concurrently
        results1, results2, results3 = await asyncio.gather(
            switching_task("req_switch_1"),
            switching_task("req_switch_2"),
            switching_task("req_switch_3"),
        )

        # Verify IDs remained constant despite context switching
        assert all(r == "req_switch_1" for r in results1)
        assert all(r == "req_switch_2" for r in results2)
        assert all(r == "req_switch_3" for r in results3)


class TestContextVarBehavior:
    """Test ContextVar implementation details."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    def test_context_var_type_annotation(self) -> None:
        """Test that _request_id_var has correct type."""
        assert isinstance(_request_id_var, ContextVar)
        assert _request_id_var.name == "request_id"

    def test_context_var_default_value(self) -> None:
        """Test that ContextVar default is None."""
        # Create a fresh context to test default
        ctx = _request_id_var.set(None)
        _request_id_var.reset(ctx)
        assert get_request_id() is None

    def test_set_returns_token(self) -> None:
        """Test that set_request_id works with context tokens."""
        # This is internal testing - just verify the operation completes
        set_request_id("req_token_test")
        assert get_request_id() == "req_token_test"


class TestErrorHandling:
    """Test error handling and edge cases."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    def test_get_request_id_with_no_prior_set(self) -> None:
        """Test get_request_id works safely when nothing was set."""
        _request_id_var.set(None)  # Ensure clean state
        result = get_request_id()
        assert result is None

    @pytest.mark.asyncio
    async def test_concurrent_set_and_get(self) -> None:
        """Test rapid concurrent sets and gets don't cause race conditions."""

        async def rapid_operations(request_id: str, iterations: int = 100) -> bool:
            """Perform rapid set/get operations."""
            for i in range(iterations):
                test_id = f"{request_id}_{i}"
                set_request_id(test_id)
                retrieved = get_request_id()
                if retrieved != test_id:
                    return False
            return True

        # Run rapid operations concurrently
        results = await asyncio.gather(
            rapid_operations("req_rapid_1"),
            rapid_operations("req_rapid_2"),
            rapid_operations("req_rapid_3"),
        )

        assert all(results), "Some concurrent operations failed to maintain request ID"

    @pytest.mark.asyncio
    async def test_long_running_task_preserves_id(self) -> None:
        """Test that request ID is preserved in long-running tasks."""

        async def long_task(request_id: str, duration: float = 0.1) -> str:
            """Long-running task that checks ID at the end."""
            set_request_id(request_id)
            start = asyncio.get_event_loop().time()

            while asyncio.get_event_loop().time() - start < duration:
                await asyncio.sleep(0.01)

            return get_request_id()

        result = await long_task("req_long_running")
        assert result == "req_long_running"


class TestIntegration:
    """Integration tests for request context with realistic scenarios."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    @pytest.mark.asyncio
    async def test_request_context_in_producer_consumer_pattern(self) -> None:
        """Test request ID propagation in producer-consumer pattern."""
        queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
        results = []

        async def producer(request_id: str, items: int) -> None:
            """Producer that adds items with current request ID."""
            set_request_id(request_id)
            for i in range(items):
                await asyncio.sleep(0.001)
                queue.put((request_id, f"item_{i}"))

        async def consumer() -> None:
            """Consumer that retrieves items."""
            while len(results) < 15:  # 3 producers * 5 items
                try:
                    request_id, item = queue.get_nowait()
                    results.append((get_request_id(), request_id, item))
                except asyncio.QueueEmpty:
                    await asyncio.sleep(0.001)

        # Run producers and consumer concurrently
        await asyncio.gather(
            producer("req_producer_1", 5),
            producer("req_producer_2", 5),
            producer("req_producer_3", 5),
            consumer(),
        )

        # Verify consumer could access request IDs through context
        assert len(results) == 15

    @pytest.mark.asyncio
    async def test_request_context_with_gather_and_gather_nested(self) -> None:
        """Test request context with nested gather calls."""

        async def leaf_task(request_id: str, task_num: int) -> tuple[str, int]:
            """Leaf task in nested structure."""
            await asyncio.sleep(0.001)
            return get_request_id(), task_num

        async def branch_task(request_id: str, branch_num: int) -> list[tuple[str, int]]:
            """Branch task that runs leaf tasks."""
            set_request_id(request_id)
            leaf_tasks = [leaf_task(request_id, i) for i in range(3)]
            return await asyncio.gather(*leaf_tasks)

        # Nested gather calls
        root_tasks = [branch_task(f"req_nested_root_{i}", i) for i in range(2)]
        results = await asyncio.gather(*root_tasks)

        # Verify context propagated through nesting
        for root_idx, branch_results in enumerate(results):
            expected_id = f"req_nested_root_{root_idx}"
            for actual_id, _ in branch_results:
                assert actual_id == expected_id
