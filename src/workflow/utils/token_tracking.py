"""
Token tracking and cost calculation utilities.

Provides functions for calculating token costs based on model pricing
and aggregating token metrics across multiple API calls.
"""

from workflow.models.internal import CostMetrics
from workflow.utils.logging import get_logger

logger = get_logger(__name__)


def get_model_pricing() -> dict[str, dict[str, float]]:
    """
    Get Anthropic model pricing in USD per token.

    Returns a dictionary mapping model names to their input and output token prices.

    Returns:
        Dictionary with model names as keys and pricing info (input_price, output_price) as values.
        Prices are in USD per 1M tokens.

    Note:
        These prices are current as of the implementation date.
        Update these values as Anthropic's pricing changes.
    """
    # Prices in USD per 1M tokens (as of Claude 3.5)
    return {
        # Claude 3.5 Sonnet (OpenAI-compatible, latest version)
        "claude-sonnet-4-5-20250929": {
            "input_price_per_mtok": 3.00,  # $3 per 1M input tokens
            "output_price_per_mtok": 15.00,  # $15 per 1M output tokens
        },
        # Claude 3.5 Haiku (OpenAI-compatible, latest version)
        "claude-haiku-4-5-20251001": {
            "input_price_per_mtok": 1.00,  # $1.00 per 1M input tokens
            "output_price_per_mtok": 5.00,  # $5.00 per 1M output tokens
        },
        # Legacy model fallbacks
        "claude-3-5-sonnet-20241022": {
            "input_price_per_mtok": 3.00,
            "output_price_per_mtok": 15.00,
        },
        "claude-3-5-haiku-20241022": {
            "input_price_per_mtok": 1.00,
            "output_price_per_mtok": 5.00,
        },
    }


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> CostMetrics:
    """
    Calculate USD cost for API usage based on model and token counts.

    Args:
        model: Model identifier (e.g., "claude-haiku-4-5-20251001")
        input_tokens: Number of input tokens used
        output_tokens: Number of output tokens used

    Returns:
        CostMetrics object with calculated costs in USD

    Raises:
        ValueError: If model pricing is not found for the specified model

    Example:
        >>> cost = calculate_cost("claude-haiku-4-5-20251001", 100, 50)
        >>> print(f"Total cost: ${cost.total_cost_usd}")
    """
    pricing = get_model_pricing()

    if model not in pricing:
        logger.warning(
            f"Unknown model pricing requested: {model}",
            extra={
                "model": model,
                "available_models": list(pricing.keys()),
            },
        )
        raise ValueError(f"Unknown model: {model}. Available models: {list(pricing.keys())}")

    model_pricing = pricing[model]
    input_price_per_mtok = model_pricing["input_price_per_mtok"]
    output_price_per_mtok = model_pricing["output_price_per_mtok"]

    # Calculate costs: (tokens / 1,000,000) * price_per_mtok
    input_cost_usd = (input_tokens / 1_000_000) * input_price_per_mtok
    output_cost_usd = (output_tokens / 1_000_000) * output_price_per_mtok

    cost_metrics = CostMetrics(
        input_cost_usd=input_cost_usd,
        output_cost_usd=output_cost_usd,
    )

    logger.debug(
        "Token cost calculated",
        extra={
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "input_cost_usd": input_cost_usd,
            "output_cost_usd": output_cost_usd,
            "total_cost_usd": cost_metrics.total_cost_usd,
        },
    )

    return cost_metrics


def aggregate_token_metrics(
    usage_list: list[dict[str, int]],
    model_list: list[str],
) -> tuple[int, float]:
    """
    Aggregate token usage and costs from multiple API calls.

    Args:
        usage_list: List of dictionaries with 'input_tokens' and 'output_tokens' keys
        model_list: List of model identifiers corresponding to each usage entry

    Returns:
        Tuple of (total_tokens, total_cost_usd)

    Raises:
        ValueError: If usage_list and model_list have different lengths

    Example:
        >>> usages = [
        ...     {"input_tokens": 100, "output_tokens": 50},
        ...     {"input_tokens": 150, "output_tokens": 75},
        ... ]
        >>> models = ["claude-haiku-4-5-20251001", "claude-haiku-4-5-20251001"]
        >>> total_tokens, total_cost = aggregate_token_metrics(usages, models)
        >>> print(f"Total: {total_tokens} tokens, ${total_cost:.6f}")
    """
    if len(usage_list) != len(model_list):
        raise ValueError(f"Length mismatch: {len(usage_list)} usages but {len(model_list)} models")

    total_tokens = 0
    total_cost_usd = 0.0

    for usage, model in zip(usage_list, model_list, strict=True):
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)

        # Add to token total
        total_tokens += input_tokens + output_tokens

        # Calculate and add cost
        cost_metrics = calculate_cost(model, input_tokens, output_tokens)
        total_cost_usd += cost_metrics.total_cost_usd

    logger.debug(
        "Token metrics aggregated",
        extra={
            "call_count": len(usage_list),
            "total_tokens": total_tokens,
            "total_cost_usd": total_cost_usd,
        },
    )

    return total_tokens, total_cost_usd
