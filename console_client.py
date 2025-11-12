#!/usr/bin/env python3
"""
Lightweight console client for Template Service streaming API.

Usage:
    python console_client.py "Your prompt here"
    python console_client.py "Tell me about AI" 1000
"""

import sys
import json
import os
import requests
import uuid

# Template Service API endpoint
API_URL = "http://localhost:8000/v1/chat/completions"

def stream_chat(prompt: str, max_tokens: int = 500, bearer_token: str | None = None, request_id: str | None = None):
    """Stream chat completion from Template Service and render to console."""

    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    # Add Bearer token to Authorization header if provided
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    # Add Request ID header for tracing (auto-generate if not provided)
    if request_id:
        headers["X-Request-ID"] = request_id
    else:
        headers["X-Request-ID"] = f"req_{int(uuid.uuid4().int % 1000000000)}"

    payload = {
        "model": "prompt-chaining",
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
    }

    print(f"\n{'='*80}")
    print(f"PROMPT: {prompt}")
    if "X-Request-ID" in headers:
        print(f"REQUEST ID: {headers['X-Request-ID']}")
    print(f"{'='*80}\n")

    try:
        with requests.post(API_URL, headers=headers, json=payload, stream=True, timeout=60) as response:
            response.raise_for_status()

            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')

                    if decoded_line.startswith("data:"):
                        event_data = decoded_line[6:].strip()  # Remove "data: " prefix

                        if event_data == "[DONE]":
                            break

                        try:
                            event_json = json.loads(event_data)

                            # Check for errors
                            if "error" in event_json:
                                print(f"\n❌ ERROR: {event_json['error']['message']}", file=sys.stderr)
                                return

                            # Extract content from OpenAI-compatible format
                            if "choices" in event_json and event_json["choices"]:
                                choice = event_json["choices"][0]
                                delta = choice.get("delta", {})
                                content = delta.get("content")

                                # Print content as it arrives
                                if content:
                                    print(content, end='', flush=True)

                                # Print usage stats when stream ends
                                finish_reason = choice.get("finish_reason")
                                if finish_reason and "usage" in event_json and event_json["usage"]:
                                    usage = event_json["usage"]
                                    print(f"\n\n{'='*80}")
                                    print(f"Tokens: {usage['total_tokens']} "
                                          f"(prompt: {usage['prompt_tokens']}, "
                                          f"completion: {usage['completion_tokens']})")
                                    print(f"Finish: {finish_reason}")
                                    print(f"{'='*80}\n")
                                elif finish_reason:
                                    # Show finish reason even if usage not available
                                    print(f"\n\n{'='*80}")
                                    print(f"Finish: {finish_reason}")
                                    print(f"{'='*80}\n")

                        except json.JSONDecodeError as e:
                            print(f"\n❌ JSON Parse Error: {e}", file=sys.stderr)
                            continue

    except requests.exceptions.RequestException as e:
        print(f"\n❌ Request failed: {e}", file=sys.stderr)
        return


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python console_client.py <prompt> [max_tokens] [request_id]")
        print("\nExamples:")
        print('  python console_client.py "Hello, world!"')
        print('  python console_client.py "Tell me about AI" 300')
        print('  python console_client.py "Hello" 500 "my-trace-123"')
        sys.exit(1)

    # Read JWT bearer token from environment
    bearer_token = os.getenv("API_BEARER_TOKEN")
    if not bearer_token:
        print("ERROR: API_BEARER_TOKEN environment variable not set", file=sys.stderr)
        print("Generate a token with: python scripts/generate_jwt.py", file=sys.stderr)
        sys.exit(1)

    prompt = sys.argv[1]
    max_tokens = int(sys.argv[2]) if len(sys.argv) > 2 else 500
    request_id = sys.argv[3] if len(sys.argv) > 3 else None

    stream_chat(prompt, max_tokens, bearer_token, request_id)
