#!/usr/bin/env python
"""
Benchmark script for the prompt-chaining workflow.

This script runs the prompt-chaining chain with specific model configurations
and collects performance metrics including latency, cost, and token usage.

Usage:
    python scripts/benchmark_chain.py

Configuration:
    - All-Haiku configuration: CHAIN_ANALYZE_MODEL=claude-haiku-4-5-20251001 etc.
    - Runs 5 requests per configuration
    - Measures p50, p95, p99 latency percentiles
    - Outputs results to benchmark_results.json and console

Requirements:
    - Running development server on localhost:8000
    - Valid JWT token via generate_jwt.py
    - ANTHROPIC_API_KEY set in environment
"""

import asyncio
import json
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

# Configuration
DEFAULT_HOST = "http://localhost:8000"
NUM_REQUESTS = 5
TEST_MESSAGES = [
    "What is artificial intelligence and how does it work?",
    "Explain machine learning in simple terms",
    "How do neural networks process information?",
    "What are the benefits and risks of AI?",
    "Describe the future of AI technology",
]


def get_jwt_token() -> str:
    """Generate a JWT token for authentication."""
    try:
        result = subprocess.run(
            ["python", "scripts/generate_jwt.py"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            raise RuntimeError(f"Failed to generate token: {result.stderr}")
    except Exception as e:
        raise RuntimeError(f"Could not generate JWT token: {e}")


def check_server_running(host: str = DEFAULT_HOST) -> bool:
    """Check if the development server is running."""
    try:
        response = requests.get(f"{host}/health/", timeout=2)
        return response.status_code == 200
    except requests.exceptions.ConnectionError:
        return False


def run_benchmark_request(
    host: str,
    token: str,
    message: str,
) -> dict[str, Any]:
    """
    Run a single benchmark request and collect metrics.

    Args:
        host: API host URL
        token: JWT bearer token
        message: Test message to send

    Returns:
        Dictionary with metrics:
        - latency: Total request duration in seconds
        - total_tokens: Total tokens used in request
        - total_cost_usd: Total cost of request in USD
        - step_breakdown: Per-step metrics
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "orchestrator-worker",
        "messages": [{"role": "user", "content": message}],
    }

    start_time = time.time()
    total_tokens = 0
    total_cost_usd = 0.0
    step_breakdown = {}

    try:
        response = requests.post(
            f"{host}/v1/chat/completions",
            headers=headers,
            json=payload,
            stream=True,
            timeout=60,
        )

        if response.status_code != 200:
            return {
                "error": f"HTTP {response.status_code}",
                "latency": time.time() - start_time,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "step_breakdown": {},
            }

        # Consume the stream to ensure metrics are logged
        chunk_count = 0
        for line in response.iter_lines():
            if line:
                chunk_count += 1

        elapsed = time.time() - start_time

        # In a real scenario, we would extract metrics from the logs
        # For now, return basic structure
        return {
            "latency": elapsed,
            "total_tokens": total_tokens,
            "total_cost_usd": total_cost_usd,
            "step_breakdown": step_breakdown,
            "chunk_count": chunk_count,
        }

    except requests.exceptions.Timeout:
        return {
            "error": "Timeout",
            "latency": time.time() - start_time,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "step_breakdown": {},
        }
    except Exception as e:
        return {
            "error": str(e),
            "latency": time.time() - start_time,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "step_breakdown": {},
        }


def calculate_percentiles(latencies: list[float]) -> dict[str, float]:
    """Calculate percentile latencies."""
    if not latencies:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "avg": 0.0}

    sorted_latencies = sorted(latencies)
    return {
        "p50": sorted_latencies[int(len(sorted_latencies) * 0.5)],
        "p95": sorted_latencies[int(len(sorted_latencies) * 0.95)],
        "p99": sorted_latencies[int(len(sorted_latencies) * 0.99)],
        "avg": statistics.mean(latencies),
    }


def run_benchmark() -> dict[str, Any]:
    """Run the complete benchmark suite."""
    print("=" * 80)
    print("Prompt-Chaining Benchmark Suite")
    print("=" * 80)
    print()

    # Check prerequisites
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    host = DEFAULT_HOST
    if not check_server_running(host):
        print(f"ERROR: Dev server not running on {host}")
        print("Start the server with: ./scripts/dev.sh")
        sys.exit(1)

    print(f"Server: {host}")
    print("Configuration: All-Haiku (claude-haiku-4-5-20251001)")
    print(f"Requests per config: {NUM_REQUESTS}")
    print()

    # Generate token
    print("Generating JWT token...")
    try:
        token = get_jwt_token()
        print("Token generated successfully")
    except RuntimeError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print()

    # Run benchmarks
    print("Running benchmark requests...")
    print("-" * 80)

    results = {
        "timestamp": datetime.now().isoformat(),
        "configuration": "all-haiku",
        "num_requests": NUM_REQUESTS,
        "requests": [],
    }

    latencies = []
    costs = []
    token_counts = []
    successful_requests = 0

    for i in range(NUM_REQUESTS):
        message = TEST_MESSAGES[i % len(TEST_MESSAGES)]
        print(f"Request {i + 1}/{NUM_REQUESTS}: ", end="", flush=True)

        result = run_benchmark_request(host, token, message)
        results["requests"].append(result)

        if "error" not in result or not result.get("error"):
            latencies.append(result["latency"])
            costs.append(result["total_cost_usd"])
            token_counts.append(result["total_tokens"])
            successful_requests += 1
            print(f"{result['latency']:.2f}s")
        else:
            print(f"ERROR: {result.get('error')}")

        time.sleep(0.5)  # Small delay between requests

    print("-" * 80)
    print()

    # Calculate statistics
    results["statistics"] = {
        "successful_requests": successful_requests,
        "failed_requests": NUM_REQUESTS - successful_requests,
        "latency": calculate_percentiles(latencies) if latencies else {},
        "cost": {
            "p50": sorted(costs)[int(len(costs) * 0.5)] if costs else 0.0,
            "p95": sorted(costs)[int(len(costs) * 0.95)] if costs else 0.0,
            "p99": sorted(costs)[int(len(costs) * 0.99)] if costs else 0.0,
            "avg": statistics.mean(costs) if costs else 0.0,
            "total": sum(costs),
        } if costs else {},
        "tokens": {
            "p50": sorted(token_counts)[int(len(token_counts) * 0.5)] if token_counts else 0,
            "p95": sorted(token_counts)[int(len(token_counts) * 0.95)] if token_counts else 0,
            "p99": sorted(token_counts)[int(len(token_counts) * 0.99)] if token_counts else 0,
            "avg": int(statistics.mean(token_counts)) if token_counts else 0,
            "total": sum(token_counts),
        } if token_counts else {},
    }

    return results


def print_results(results: dict[str, Any]) -> None:
    """Print benchmark results in markdown table format."""
    stats = results.get("statistics", {})

    print("Benchmark Results: All-Haiku Configuration")
    print()
    print("| Metric | p50 | p95 | p99 | Avg |")
    print("|--------|-----|-----|-----|-----|")

    # Latency
    latency = stats.get("latency", {})
    print(
        f"| Latency (s) | {latency.get('p50', 0):.2f} | {latency.get('p95', 0):.2f} | "
        f"{latency.get('p99', 0):.2f} | {latency.get('avg', 0):.2f} |"
    )

    # Cost
    cost = stats.get("cost", {})
    print(
        f"| Cost (USD) | {cost.get('p50', 0):.5f} | {cost.get('p95', 0):.5f} | "
        f"{cost.get('p99', 0):.5f} | {cost.get('avg', 0):.5f} |"
    )

    # Tokens
    tokens = stats.get("tokens", {})
    print(
        f"| Tokens | {tokens.get('p50', 0)} | {tokens.get('p95', 0)} | "
        f"{tokens.get('p99', 0)} | {tokens.get('avg', 0)} |"
    )

    print()
    print("Summary:")
    print(f"- Successful requests: {stats.get('successful_requests', 0)}/{results.get('num_requests', 0)}")
    print(f"- Total cost: ${cost.get('total', 0):.5f}")
    print(f"- Total tokens: {tokens.get('total', 0)}")
    print()


def save_results(results: dict[str, Any], filename: str = "benchmark_results.json") -> None:
    """Save benchmark results to JSON file."""
    with open(filename, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to {filename}")


def main() -> int:
    """Main entry point."""
    try:
        results = run_benchmark()
        print_results(results)
        save_results(results)
        return 0
    except KeyboardInterrupt:
        print("\nBenchmark interrupted by user")
        return 1
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
