"""
Unit tests for token tracking and cost calculation utilities.

Tests the token usage calculation, cost estimation, and aggregation functions.
"""

import pytest

from workflow.models.internal import (
    AggregatedTokenMetrics,
    CostMetrics,
    TaskResult,
    TokenUsage,
)
from workflow.utils.token_tracking import (
    aggregate_step_metrics,
    aggregate_token_metrics,
    calculate_cost,
    get_model_pricing,
)


class TestTokenUsageModel:
    """Test TokenUsage Pydantic model."""

    def test_token_usage_creation(self):
        """Test creating a TokenUsage instance."""
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.total_tokens == 150

    def test_token_usage_validation(self):
        """Test TokenUsage validation with negative values."""
        with pytest.raises(ValueError):
            TokenUsage(input_tokens=-1, output_tokens=50)

        with pytest.raises(ValueError):
            TokenUsage(input_tokens=100, output_tokens=-10)

    def test_token_usage_zero_values(self):
        """Test TokenUsage with zero values."""
        usage = TokenUsage(input_tokens=0, output_tokens=0)
        assert usage.total_tokens == 0

    def test_token_usage_large_values(self):
        """Test TokenUsage with large token counts."""
        usage = TokenUsage(input_tokens=1_000_000, output_tokens=500_000)
        assert usage.total_tokens == 1_500_000


class TestCostMetricsModel:
    """Test CostMetrics Pydantic model."""

    def test_cost_metrics_creation(self):
        """Test creating a CostMetrics instance."""
        cost = CostMetrics(input_cost_usd=0.003, output_cost_usd=0.015)
        assert cost.input_cost_usd == 0.003
        assert cost.output_cost_usd == 0.015
        assert cost.total_cost_usd == pytest.approx(0.018)

    def test_cost_metrics_zero_costs(self):
        """Test CostMetrics with zero costs."""
        cost = CostMetrics(input_cost_usd=0.0, output_cost_usd=0.0)
        assert cost.total_cost_usd == 0.0

    def test_cost_metrics_negative_validation(self):
        """Test CostMetrics rejects negative costs."""
        with pytest.raises(ValueError):
            CostMetrics(input_cost_usd=-0.01, output_cost_usd=0.01)

    def test_cost_metrics_precision(self):
        """Test CostMetrics maintains precision."""
        cost = CostMetrics(input_cost_usd=0.0001234, output_cost_usd=0.0005678)
        assert cost.total_cost_usd == pytest.approx(0.0006912)


class TestAggregatedTokenMetricsModel:
    """Test AggregatedTokenMetrics Pydantic model."""

    def test_aggregated_metrics_creation(self):
        """Test creating AggregatedTokenMetrics."""
        metrics = AggregatedTokenMetrics(
            orchestrator_tokens=100,
            worker_tokens=500,
            synthesizer_tokens=200,
        )
        assert metrics.orchestrator_tokens == 100
        assert metrics.worker_tokens == 500
        assert metrics.synthesizer_tokens == 200
        assert metrics.total_tokens == 800

    def test_aggregated_metrics_with_costs(self):
        """Test AggregatedTokenMetrics with cost data."""
        metrics = AggregatedTokenMetrics(
            orchestrator_tokens=100,
            worker_tokens=500,
            synthesizer_tokens=200,
            orchestrator_cost_usd=0.005,
            worker_cost_usd=0.010,
            synthesizer_cost_usd=0.008,
        )
        assert metrics.total_tokens == 800
        assert metrics.total_cost_usd == pytest.approx(0.023)

    def test_aggregated_metrics_defaults(self):
        """Test AggregatedTokenMetrics default values."""
        metrics = AggregatedTokenMetrics()
        assert metrics.orchestrator_tokens == 0
        assert metrics.worker_tokens == 0
        assert metrics.synthesizer_tokens == 0
        assert metrics.total_tokens == 0
        assert metrics.total_cost_usd == 0.0


class TestGetModelPricing:
    """Test get_model_pricing function."""

    def test_get_model_pricing_structure(self):
        """Test pricing dictionary structure."""
        pricing = get_model_pricing()

        assert isinstance(pricing, dict)
        assert len(pricing) > 0

        # Check required models are present
        assert "claude-haiku-4-5-20251001" in pricing
        assert "claude-sonnet-4-5-20250929" in pricing

        # Check each model has required fields
        for model, rates in pricing.items():
            assert "input_price_per_mtok" in rates
            assert "output_price_per_mtok" in rates
            assert isinstance(rates["input_price_per_mtok"], (int, float))
            assert isinstance(rates["output_price_per_mtok"], (int, float))
            assert rates["input_price_per_mtok"] >= 0
            assert rates["output_price_per_mtok"] >= 0

    def test_get_model_pricing_haiku_pricing(self):
        """Test Haiku model pricing values."""
        pricing = get_model_pricing()
        haiku_price = pricing["claude-haiku-4-5-20251001"]

        # Verify Haiku pricing matches Anthropic's published rates
        assert haiku_price["input_price_per_mtok"] == 1.0
        assert haiku_price["output_price_per_mtok"] == 5.0

    def test_get_model_pricing_sonnet_pricing(self):
        """Test Sonnet model pricing values."""
        pricing = get_model_pricing()
        sonnet_price = pricing["claude-sonnet-4-5-20250929"]

        # Sonnet should be more expensive than Haiku
        assert sonnet_price["input_price_per_mtok"] >= 1.0
        assert sonnet_price["output_price_per_mtok"] >= 10.0


class TestCalculateCost:
    """Test calculate_cost function."""

    def test_calculate_cost_haiku_basic(self):
        """Test cost calculation for Haiku model."""
        cost = calculate_cost(
            model="claude-haiku-4-5-20251001",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )

        # At $1.00 per 1M input and $5.00 per 1M output
        assert cost.input_cost_usd == pytest.approx(1.00)
        assert cost.output_cost_usd == pytest.approx(5.00)
        assert cost.total_cost_usd == pytest.approx(6.00)

    def test_calculate_cost_sonnet_basic(self):
        """Test cost calculation for Sonnet model."""
        cost = calculate_cost(
            model="claude-sonnet-4-5-20250929",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )

        # At $3.00 per 1M input and $15.00 per 1M output
        assert cost.input_cost_usd == pytest.approx(3.00)
        assert cost.output_cost_usd == pytest.approx(15.00)
        assert cost.total_cost_usd == pytest.approx(18.00)

    def test_calculate_cost_zero_tokens(self):
        """Test cost calculation with zero tokens."""
        cost = calculate_cost(
            model="claude-haiku-4-5-20251001",
            input_tokens=0,
            output_tokens=0,
        )

        assert cost.input_cost_usd == 0.0
        assert cost.output_cost_usd == 0.0
        assert cost.total_cost_usd == 0.0

    def test_calculate_cost_small_numbers(self):
        """Test cost calculation with small token counts."""
        cost = calculate_cost(
            model="claude-haiku-4-5-20251001",
            input_tokens=100,
            output_tokens=50,
        )

        # 100 tokens * $1.00 / 1M = $0.0001
        # 50 tokens * $5.00 / 1M = $0.00025
        assert cost.input_cost_usd == pytest.approx(0.0001)
        assert cost.output_cost_usd == pytest.approx(0.00025)
        assert cost.total_cost_usd == pytest.approx(0.00035)

    def test_calculate_cost_unknown_model(self):
        """Test cost calculation with unknown model raises error."""
        with pytest.raises(ValueError) as exc_info:
            calculate_cost(
                model="unknown-model-999",
                input_tokens=100,
                output_tokens=50,
            )

        assert "Unknown model" in str(exc_info.value)
        assert "unknown-model-999" in str(exc_info.value)

    def test_calculate_cost_realistic_usage(self):
        """Test cost calculation with realistic token usage."""
        # Typical request: 500 input tokens, 200 output tokens
        cost = calculate_cost(
            model="claude-haiku-4-5-20251001",
            input_tokens=500,
            output_tokens=200,
        )

        expected_input = (500 / 1_000_000) * 1.00
        expected_output = (200 / 1_000_000) * 5.00
        assert cost.input_cost_usd == pytest.approx(expected_input)
        assert cost.output_cost_usd == pytest.approx(expected_output)


class TestAggregateTokenMetrics:
    """Test aggregate_token_metrics function."""

    def test_aggregate_single_usage(self):
        """Test aggregating a single usage entry."""
        usages = [{"input_tokens": 100, "output_tokens": 50}]
        models = ["claude-haiku-4-5-20251001"]

        total_tokens, total_cost = aggregate_token_metrics(usages, models)

        assert total_tokens == 150
        assert total_cost == pytest.approx((100 * 1.00 + 50 * 5.00) / 1_000_000)

    def test_aggregate_multiple_usages_same_model(self):
        """Test aggregating multiple usages from same model."""
        usages = [
            {"input_tokens": 100, "output_tokens": 50},
            {"input_tokens": 200, "output_tokens": 100},
            {"input_tokens": 150, "output_tokens": 75},
        ]
        models = [
            "claude-haiku-4-5-20251001",
            "claude-haiku-4-5-20251001",
            "claude-haiku-4-5-20251001",
        ]

        total_tokens, total_cost = aggregate_token_metrics(usages, models)

        assert total_tokens == 675  # 100+200+150 input, 50+100+75 output
        # Cost: (450 * 1.00 + 225 * 5.00) / 1M
        expected_cost = (450 * 1.00 + 225 * 5.00) / 1_000_000
        assert total_cost == pytest.approx(expected_cost)

    def test_aggregate_multiple_models(self):
        """Test aggregating usages from different models."""
        usages = [
            {"input_tokens": 1_000_000, "output_tokens": 500_000},  # Haiku
            {"input_tokens": 1_000_000, "output_tokens": 500_000},  # Sonnet
        ]
        models = [
            "claude-haiku-4-5-20251001",
            "claude-sonnet-4-5-20250929",
        ]

        total_tokens, total_cost = aggregate_token_metrics(usages, models)

        assert total_tokens == 3_000_000

        # Haiku: 1M * 1.00 + 0.5M * 5.00 = 3.50
        # Sonnet: 1M * 3.00 + 0.5M * 15.00 = 10.50
        expected_cost = 3.50 + 10.50
        assert total_cost == pytest.approx(expected_cost)

    def test_aggregate_empty_list(self):
        """Test aggregating empty usage list."""
        usages = []
        models = []

        total_tokens, total_cost = aggregate_token_metrics(usages, models)

        assert total_tokens == 0
        assert total_cost == 0.0

    def test_aggregate_mismatched_lengths(self):
        """Test aggregation with mismatched usage and model lists."""
        usages = [
            {"input_tokens": 100, "output_tokens": 50},
            {"input_tokens": 200, "output_tokens": 100},
        ]
        models = ["claude-haiku-4-5-20251001"]

        with pytest.raises(ValueError) as exc_info:
            aggregate_token_metrics(usages, models)

        assert "Length mismatch" in str(exc_info.value)

    def test_aggregate_missing_token_fields(self):
        """Test aggregation with missing token fields."""
        usages = [
            {"input_tokens": 100},  # Missing output_tokens
        ]
        models = ["claude-haiku-4-5-20251001"]

        # Should not raise, defaults to 0
        total_tokens, total_cost = aggregate_token_metrics(usages, models)
        assert total_tokens == 100


class TestTaskResultWithTokens:
    """Test TaskResult integration with token tracking."""

    def test_task_result_with_token_usage(self):
        """Test TaskResult with token usage."""
        token_usage = TokenUsage(input_tokens=100, output_tokens=50)
        cost_metrics = CostMetrics(input_cost_usd=0.00008, output_cost_usd=0.0002)

        result = TaskResult(
            task_id=1,
            output="Test output",
            token_usage=token_usage,
            cost_metrics=cost_metrics,
        )

        assert result.token_usage is not None
        assert result.token_usage.total_tokens == 150
        assert result.cost_metrics is not None
        assert result.cost_metrics.total_cost_usd == pytest.approx(0.00028)

    def test_task_result_without_token_usage(self):
        """Test TaskResult without token usage (backward compatibility)."""
        result = TaskResult(
            task_id=1,
            output="Test output",
        )

        assert result.token_usage is None
        assert result.cost_metrics is None

    def test_task_result_serialization(self):
        """Test TaskResult serialization with token data."""
        token_usage = TokenUsage(input_tokens=100, output_tokens=50)
        cost_metrics = CostMetrics(input_cost_usd=0.00008, output_cost_usd=0.0002)

        result = TaskResult(
            task_id=1,
            output="Test output",
            token_usage=token_usage,
            cost_metrics=cost_metrics,
        )

        # Test that it can be serialized to JSON
        json_data = result.model_dump_json()
        assert "token_usage" in json_data
        assert "cost_metrics" in json_data

        # Test deserialization
        result2 = TaskResult.model_validate_json(json_data)
        assert result2.task_id == result.task_id
        assert result2.token_usage == result.token_usage
        assert result2.cost_metrics == result.cost_metrics


class TestRealisticScenarios:
    """Test realistic token usage scenarios."""

    def test_single_worker_request(self):
        """Test token usage for a single worker request."""
        # Typical worker response
        cost = calculate_cost(
            model="claude-haiku-4-5-20251001",
            input_tokens=450,
            output_tokens=120,
        )

        # Cost should be minimal (cheap model)
        assert cost.total_cost_usd < 0.01

    def test_multi_worker_orchestration(self):
        """Test aggregated token usage for multi-worker request."""
        # 3 workers with Haiku, synthesizer call
        usages = [
            {"input_tokens": 450, "output_tokens": 120},
            {"input_tokens": 450, "output_tokens": 120},
            {"input_tokens": 450, "output_tokens": 120},
            {"input_tokens": 1200, "output_tokens": 300},  # Synthesizer
        ]
        models = [
            "claude-haiku-4-5-20251001",
            "claude-haiku-4-5-20251001",
            "claude-haiku-4-5-20251001",
            "claude-haiku-4-5-20251001",
        ]

        total_tokens, total_cost = aggregate_token_metrics(usages, models)

        assert total_tokens > 0
        assert total_cost > 0
        # Should still be relatively cheap with Haiku
        assert total_cost < 0.05

    def test_workflow_synthesizer_flow(self):
        """Test typical orchestrator-worker-synthesizer token flow."""
        # Orchestrator planning
        orchestrator_usage = calculate_cost(
            model="claude-sonnet-4-5-20250929",
            input_tokens=200,
            output_tokens=150,
        )

        # 2 workers
        worker_usages = [
            calculate_cost(
                model="claude-haiku-4-5-20251001",
                input_tokens=400,
                output_tokens=200,
            ),
            calculate_cost(
                model="claude-haiku-4-5-20251001",
                input_tokens=400,
                output_tokens=200,
            ),
        ]

        # Synthesizer
        synthesizer_usage = calculate_cost(
            model="claude-haiku-4-5-20251001",
            input_tokens=1000,
            output_tokens=300,
        )

        total_cost = (
            orchestrator_usage.total_cost_usd
            + sum(w.total_cost_usd for w in worker_usages)
            + synthesizer_usage.total_cost_usd
        )

        # Verify costs are reasonable
        assert total_cost > 0
        assert total_cost < 0.5  # Should be less than 50 cents


class TestAggregateStepMetrics:
    """Test aggregate_step_metrics function for prompt-chaining workflow."""

    def test_aggregate_step_metrics_single_step(self):
        """Test aggregating metrics from a single step."""
        step_metadata = {
            "analyze": {
                "elapsed_seconds": 1.5,
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
                "cost_usd": 0.00015,
            }
        }

        total_tokens, total_cost, total_elapsed = aggregate_step_metrics(step_metadata)

        assert total_tokens == 150
        assert total_cost == 0.00015
        assert total_elapsed == 1.5

    def test_aggregate_step_metrics_all_steps(self):
        """Test aggregating metrics from all three steps."""
        step_metadata = {
            "analyze": {
                "elapsed_seconds": 1.5,
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
                "cost_usd": 0.00015,
            },
            "process": {
                "elapsed_seconds": 2.0,
                "input_tokens": 200,
                "output_tokens": 300,
                "total_tokens": 500,
                "cost_usd": 0.00050,
            },
            "synthesize": {
                "elapsed_seconds": 1.5,
                "input_tokens": 150,
                "output_tokens": 200,
                "total_tokens": 350,
                "cost_usd": 0.00035,
            },
        }

        total_tokens, total_cost, total_elapsed = aggregate_step_metrics(step_metadata)

        assert total_tokens == 1000
        assert total_cost == 0.00100
        assert total_elapsed == 5.0

    def test_aggregate_step_metrics_empty(self):
        """Test aggregating empty metrics."""
        step_metadata = {}

        total_tokens, total_cost, total_elapsed = aggregate_step_metrics(step_metadata)

        assert total_tokens == 0
        assert total_cost == 0.0
        assert total_elapsed == 0.0

    def test_aggregate_step_metrics_with_error_entry(self):
        """Test aggregating metrics with error entry (should be skipped)."""
        step_metadata = {
            "analyze": {
                "elapsed_seconds": 1.5,
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
                "cost_usd": 0.00015,
            },
            "error": {
                "occurred": True,
                "message": "Some error",
            }
        }

        total_tokens, total_cost, total_elapsed = aggregate_step_metrics(step_metadata)

        # Error entry should be skipped
        assert total_tokens == 150
        assert total_cost == 0.00015
        assert total_elapsed == 1.5

    def test_aggregate_step_metrics_missing_fields(self):
        """Test aggregating metrics with missing optional fields."""
        step_metadata = {
            "analyze": {
                "elapsed_seconds": 1.5,
                "total_tokens": 150,
                "cost_usd": 0.00015,
            },
            "process": {
                "elapsed_seconds": 2.0,
                "total_tokens": 500,
                "cost_usd": 0.00050,
            },
        }

        total_tokens, total_cost, total_elapsed = aggregate_step_metrics(step_metadata)

        assert total_tokens == 650
        assert total_cost == 0.00065
        assert total_elapsed == 3.5

    def test_aggregate_step_metrics_realistic_haiku_scenario(self):
        """Test realistic scenario with All-Haiku configuration."""
        step_metadata = {
            "analyze": {
                "elapsed_seconds": 1.2,
                "input_tokens": 250,
                "output_tokens": 150,
                "total_tokens": 400,
                "cost_usd": (250 / 1_000_000) * 1.0 + (150 / 1_000_000) * 5.0,
            },
            "process": {
                "elapsed_seconds": 2.3,
                "input_tokens": 400,
                "output_tokens": 450,
                "total_tokens": 850,
                "cost_usd": (400 / 1_000_000) * 1.0 + (450 / 1_000_000) * 5.0,
            },
            "synthesize": {
                "elapsed_seconds": 1.5,
                "input_tokens": 500,
                "output_tokens": 300,
                "total_tokens": 800,
                "cost_usd": (500 / 1_000_000) * 1.0 + (300 / 1_000_000) * 5.0,
            },
        }

        total_tokens, total_cost, total_elapsed = aggregate_step_metrics(step_metadata)

        assert total_tokens == 2050
        assert total_cost > 0
        assert total_cost < 0.01  # Haiku should be cheap
        assert total_elapsed == 5.0  # 1.2 + 2.3 + 1.5
