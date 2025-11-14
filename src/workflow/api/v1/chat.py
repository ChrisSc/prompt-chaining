"""Chat completions endpoint for OpenAI-compatible API."""

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from workflow.api.dependencies import verify_bearer_token
from workflow.api.limiter import limiter
from workflow.chains.graph import stream_chain
from workflow.models.chains import ChainState
from workflow.models.openai import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionStreamChoice,
    ChoiceDelta,
    MessageRole,
)
from workflow.utils.errors import ExternalServiceError, StreamingTimeoutError
from workflow.utils.logging import get_logger
from workflow.utils.message_conversion import (
    convert_langchain_chunk_to_openai,
    convert_openai_to_langchain_messages,
)
from workflow.utils.request_context import get_request_id
from workflow.utils.token_tracking import aggregate_step_metrics
from workflow.utils.user_context import get_user_context

logger = get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["chat"])


async def get_chain_graph(request: Request) -> Any:
    """
    Dependency to get the compiled LangGraph chain graph from app state.

    Returns the initialized chain graph for prompt-chaining execution.

    Args:
        request: FastAPI request object

    Returns:
        Compiled LangGraph StateGraph instance

    Raises:
        HTTPException: If service initialization failed
    """
    chain_graph = getattr(request.app.state, "chain_graph", None)

    if chain_graph is None:
        logger.error(
            "Chain graph not available - service initialization may have failed",
            extra={
                "endpoint": "chat.completions",
                "status_code": 503,
                "service_status": "initialization_failed",
            },
        )

    return chain_graph


@router.post("/chat/completions")
@limiter.limit("10/minute")
async def create_chat_completion(
    request: Request,
    request_data: ChatCompletionRequest,
    chain_graph: Any = Depends(get_chain_graph),
    token: dict = Depends(verify_bearer_token),
):
    """
    Stream chat completions through the prompt-chaining workflow.

    Executes three sequential steps (analyze → process → synthesize) and returns
    streaming response via Server-Sent Events (SSE). Each step has independent
    timeout configuration.

    Args:
        request_data: ChatCompletionRequest with model, messages, and parameters
        chain_graph: Compiled LangGraph StateGraph (injected via dependency)
        token: JWT bearer token payload (validates authorization)

    Returns:
        StreamingResponse with SSE-formatted ChatCompletionChunk events.
        Stream terminates with "data: [DONE]\\n\\n"

    Raises:
        HTTPException: If chain graph unavailable (503)
        StreamingTimeoutError: If step exceeds timeout (sent as SSE event)
        ExternalServiceError: If upstream API fails (sent as SSE event)

    See Also:
        CLAUDE.md - Configuration and timeout details
        JWT_AUTHENTICATION.md - Bearer token usage
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
            final_step_metadata = {}

            # Use prompt-chaining workflow via LangGraph
            if chain_graph is None:
                logger.error("Chain graph not available - application not properly initialized")
                raise HTTPException(
                    status_code=503,
                    detail="Service initialization failed - chain graph not available",
                )

            logger.debug("Using LangGraph chain graph for streaming")

            # Convert OpenAI messages to LangChain format
            langchain_messages = convert_openai_to_langchain_messages(request_data.messages)

            # Get request_id and user_id from context
            request_id = get_request_id() or "unknown"
            user_id = get_user_context() or "unknown"

            # Build initial state for the chain
            initial_state: ChainState = {
                "messages": langchain_messages,
                "request_id": request_id,
                "user_id": user_id,
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
                # Handle synthesize_tokens events from custom streaming
                if "synthesize_tokens" in state_update:
                    try:
                        token_event = state_update.get("synthesize_tokens", {})
                        if isinstance(token_event, dict):
                            token_type = token_event.get("type")
                            token_content = token_event.get("content", "")

                            # Only emit non-empty tokens
                            if token_type == "token" and token_content:
                                # Create ChatCompletionChunk for this token
                                chunk = ChatCompletionChunk(
                                    id=f"chatcmpl-{int(time.time() * 1000)}",
                                    object="chat.completion.chunk",
                                    created=int(time.time()),
                                    model=request_data.model,
                                    choices=[
                                        ChatCompletionStreamChoice(
                                            index=0,
                                            delta=ChoiceDelta(
                                                role=MessageRole.ASSISTANT,
                                                content=token_content,
                                            ),
                                            finish_reason=None,
                                        )
                                    ],
                                )
                                yield f"data: {chunk.model_dump_json()}\n\n"
                                chunk_count += 1
                    except Exception as token_error:
                        logger.warning(
                            "Failed to process token event",
                            extra={"error": str(token_error)},
                        )
                        # Continue processing despite error
                        continue

                # Capture step metadata for aggregation
                # state_update structure: {"node_name": {"analysis": {...}, "step_metadata": {...}, ...}}
                for node_name, node_update in state_update.items():
                    if isinstance(node_update, dict):
                        step_metadata = node_update.get("step_metadata", {})
                        if isinstance(step_metadata, dict):
                            final_step_metadata.update(step_metadata)

                # Skip convert_langchain_chunk_to_openai if we already handled this state update
                if "synthesize_tokens" in state_update or "synthesize" in state_update:
                    continue

                # Extract content from the state update and convert to OpenAI format (for analyze/process nodes)
                try:
                    chunk = convert_langchain_chunk_to_openai(state_update)
                    if chunk.choices[0].delta.content:  # Only yield if has content
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

            # Send final [DONE] marker
            yield "data: [DONE]\n\n"

            # Log request completion with aggregated metrics
            elapsed_time = time.time() - request_start_time

            # Calculate aggregated metrics from step metadata
            if final_step_metadata:
                total_tokens, total_cost_usd, aggregated_elapsed = aggregate_step_metrics(
                    final_step_metadata
                )
            else:
                total_tokens, total_cost_usd, aggregated_elapsed = 0, 0.0, 0.0

            logger.info(
                "Request completed",
                extra={
                    "request_id": request.headers.get("X-Request-ID", "unknown"),
                    "total_tokens": total_tokens,
                    "total_cost_usd": total_cost_usd,
                    "total_elapsed_seconds": elapsed_time,
                    "aggregated_step_elapsed_seconds": aggregated_elapsed,
                    "step_breakdown": final_step_metadata,
                    "status": "success",
                },
            )
            logger.debug(
                "Streaming response completed",
                extra={
                    "chunk_count": chunk_count,
                    "elapsed_seconds": elapsed_time,
                    "model": request_data.model,
                    "user": user_subject,
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
