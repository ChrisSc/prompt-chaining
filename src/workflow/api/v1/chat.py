"""Chat completions endpoint for OpenAI-compatible API."""

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from workflow.agents.orchestrator import Orchestrator
from workflow.api.dependencies import verify_bearer_token
from workflow.api.limiter import limiter
from workflow.chains.graph import stream_chain
from workflow.models.openai import ChatCompletionRequest
from workflow.utils.errors import ExternalServiceError, StreamingTimeoutError
from workflow.utils.logging import get_logger
from workflow.utils.message_conversion import (
    convert_langchain_chunk_to_openai,
    convert_openai_to_langchain_messages,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["chat"])


async def get_orchestrator(request: Request) -> Orchestrator:
    """
    Dependency to get the Orchestrator agent from app state.

    Args:
        request: FastAPI request object

    Returns:
        Orchestrator agent instance

    Raises:
        HTTPException: If agent is not available or not initialized
    """
    agent = request.app.state.orchestrator
    if not agent:
        logger.error("Orchestrator agent not available")
        raise HTTPException(
            status_code=503,
            detail="Orchestrator agent not available",
        )

    # Check if agent is initialized (client must be ready)
    if not agent.client:
        logger.error("Orchestrator agent not initialized yet")
        raise HTTPException(
            status_code=503,
            detail="Service is starting up, please retry in a moment",
        )

    return agent


async def get_chain_graph(request: Request) -> Any:
    """
    Dependency to get the compiled LangGraph chain graph from app state.

    Returns the chain graph if available and initialized, otherwise None
    to allow fallback to orchestrator mode.

    Args:
        request: FastAPI request object

    Returns:
        Compiled LangGraph StateGraph or None if not available

    Raises:
        HTTPException: If service is not ready
    """
    # Check if chain graph is available
    chain_graph = getattr(request.app.state, "chain_graph", None)

    if chain_graph is None:
        logger.debug("Chain graph not available, will fall back to orchestrator mode")

    return chain_graph


@router.post("/chat/completions")
@limiter.limit("10/minute")
async def create_chat_completion(
    request: Request,
    request_data: ChatCompletionRequest,
    orchestrator: Orchestrator = Depends(get_orchestrator),
    chain_graph: Any = Depends(get_chain_graph),
    token: dict = Depends(verify_bearer_token),
):
    """
    Stream chat completions using multi-agent orchestration with phase-specific timeouts.

    Processes chat messages through the Orchestrator agent and returns a streaming response
    using Server-Sent Events (SSE). Enforces separate timeouts for worker coordination and
    synthesis phases to prevent runaway requests.

    Request Processing Phases:
    1. Worker Coordination Phase: Orchestrator decomposes task, spawns workers, and collects
       results in parallel. Maximum duration controlled by WORKER_COORDINATION_TIMEOUT
       (default 45s).
    2. Synthesis Phase: Synthesizer aggregates results and streams final response. Maximum
       duration controlled by SYNTHESIS_TIMEOUT (default 30s).

    Timeout Behavior:
    - If worker coordination exceeds WORKER_COORDINATION_TIMEOUT, all pending workers are
      cancelled and an error event is sent via SSE.
    - If synthesis exceeds SYNTHESIS_TIMEOUT, the stream terminates with an error event.
    - Error events include phase, timeout duration, and human-readable message.
    - Total request budget = WORKER_COORDINATION_TIMEOUT + SYNTHESIS_TIMEOUT (default: 75s).

    Error Handling:
    - Timeout errors are sent as Server-Sent Events with type "streaming_timeout_error"
    - Client disconnections (EOF) are handled gracefully without error propagation
    - External service errors include service details and retry information
    - Unexpected errors trigger a generic server error event

    Args:
        request_data: ChatCompletionRequest containing model ID, messages list, and optional
                      parameters (max_tokens, temperature, etc.)
        orchestrator: Orchestrator agent instance (injected via dependency)
        token: JWT bearer token payload (injected via dependency, validates authorization)

    Returns:
        StreamingResponse with SSE-formatted ChatCompletionChunk events:
        - Each event prefixed with "data: " followed by JSON
        - Stream terminated with "data: [DONE]\\n\\n"
        - Error events include structured error information

    Raises:
        HTTPException: If service is starting up or orchestrator unavailable (503)
        StreamingTimeoutError: If worker or synthesis phase exceeds configured timeout
                              (sent as SSE event, not HTTP error)
        ExternalServiceError: If upstream API call fails (sent as SSE event)
        ValidationError: If request data fails Pydantic validation

    Example:
        Request with curl:
        ```bash
        TOKEN=$(python scripts/generate_jwt.py)
        curl -X POST http://localhost:8000/v1/chat/completions \\
          -H "Authorization: Bearer $TOKEN" \\
          -H "Content-Type: application/json" \\
          -N \\
          -d '{
            "model": "orchestrator-worker",
            "messages": [{"role": "user", "content": "Analyze this topic"}],
            "max_tokens": 500
          }'
        ```

        Successful streaming response:
        ```
        data: {"object":"chat.completion.chunk","choices":[{"delta":{"content":"Analysis"}}]}

        data: {"object":"chat.completion.chunk","choices":[{"delta":{"content":" starts here"}}]}

        data: [DONE]
        ```

        Timeout error response:
        ```
        data: {"error":{"message":"Streaming operation timed out during worker coordination phase after 45s","type":"streaming_timeout_error","phase":"worker coordination","timeout_seconds":45}}

        data: [DONE]
        ```

    See Also:
        - CLAUDE.md - Request Timeout Enforcement section for configuration details
        - JWT_AUTHENTICATION.md - Bearer token generation and usage
    """
    request_start_time = time.time()

    # Extract user info from JWT token
    user_subject = token.get("sub", "unknown")

    logger.info(
        "Chat completion request",
        extra={"model": request_data.model, "user": user_subject},
    )
    logger.debug(
        "Chat completion request details",
        extra={
            "model": request_data.model,
            "user": user_subject,
            "message_count": len(request_data.messages),
            "max_tokens": getattr(request_data, "max_tokens", None),
            "temperature": getattr(request_data, "temperature", None),
        },
    )

    async def event_generator():
        """Generate SSE events from streaming chunks."""
        try:
            logger.debug(
                "Starting streaming response generation",
                extra={"use_chain_graph": chain_graph is not None},
            )
            chunk_count = 0

            # Use chain graph if available, otherwise fall back to orchestrator
            if chain_graph is not None:
                # Use prompt-chaining workflow via LangGraph
                logger.debug("Using LangGraph chain graph for streaming")

                # Convert OpenAI messages to LangChain format
                langchain_messages = convert_openai_to_langchain_messages(request_data.messages)

                # Build initial state for the chain
                initial_state = {
                    "messages": langchain_messages,
                    "analysis": None,
                    "processed_content": None,
                    "final_response": None,
                    "step_metadata": {},
                }

                # Stream the chain execution
                settings = request.app.state.settings
                async for state_update in stream_chain(
                    chain_graph, initial_state, settings.chain_config
                ):
                    # Extract content from the state update and convert to OpenAI format
                    try:
                        chunk = convert_langchain_chunk_to_openai(state_update)
                        chunk_json = chunk.model_dump_json()
                        yield f"data: {chunk_json}\n\n"
                        chunk_count += 1
                    except Exception as chunk_error:
                        logger.warning(
                            "Failed to convert chain state to OpenAI format",
                            extra={"error": str(chunk_error)},
                        )
                        # Continue processing despite conversion error
                        continue

            else:
                # Fall back to orchestrator for backward compatibility
                logger.debug("Using orchestrator agent for streaming (chain graph not available)")

                async for chunk in orchestrator.process(request_data):
                    # Format as Server-Sent Event
                    chunk_json = chunk.model_dump_json()
                    yield f"data: {chunk_json}\n\n"
                    chunk_count += 1

            # Send final [DONE] marker
            yield "data: [DONE]\n\n"

            # Log request completion with timing
            elapsed_time = time.time() - request_start_time
            logger.info(
                "Chat completion request completed",
                extra={
                    "model": request_data.model,
                    "elapsed_seconds": elapsed_time,
                    "chunk_count": chunk_count,
                    "mode": "chain_graph" if chain_graph is not None else "orchestrator",
                },
            )
            logger.debug(
                "Streaming response completed",
                extra={
                    "chunk_count": chunk_count,
                    "elapsed_seconds": elapsed_time,
                },
            )

        except asyncio.CancelledError:
            logger.info("Client disconnected")
            # Don't yield error, just close stream
            raise

        except ExternalServiceError as exc:
            logger.error(f"External service error: {exc.message}")
            error_data = {
                "error": {
                    "message": exc.message,
                    "type": "external_service_error",
                    "code": exc.error_code,
                }
            }
            yield f"data: {json.dumps(error_data)}\n\n"

        except StreamingTimeoutError as exc:
            logger.error(
                f"Streaming timeout: {exc.message}",
                extra={
                    "phase": exc.phase,
                    "timeout_seconds": exc.timeout_seconds,
                },
            )
            error_data = {
                "error": {
                    "message": exc.message,
                    "type": "streaming_timeout_error",
                    "phase": exc.phase,
                    "timeout_seconds": exc.timeout_seconds,
                }
            }
            yield f"data: {json.dumps(error_data)}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as exc:
            logger.error(f"Unexpected error: {exc}")
            error_data = {
                "error": {
                    "message": "Internal server error",
                    "type": "server_error",
                    "code": "INTERNAL_ERROR",
                }
            }
            yield f"data: {json.dumps(error_data)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
