"""
Base agent class for the Template Service application.

Provides abstract base class for implementing agents using Claude API.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from orchestrator_worker.models.openai import ChatCompletionChunk, ChatCompletionRequest


class Agent(ABC):
    """
    Abstract base class for agents in the Template Service system.

    All agents should inherit from this class and implement required methods.
    """

    def __init__(self, name: str, model: str) -> None:
        """
        Initialize an agent.

        Args:
            name: Human-readable name for the agent
            model: Claude model ID to use
        """
        self.name = name
        self.model = model

    @abstractmethod
    async def process(self, request: ChatCompletionRequest) -> AsyncIterator[ChatCompletionChunk]:
        """
        Process a chat completion request with streaming response.

        Args:
            request: The chat completion request

        Yields:
            Streaming chunks of the chat completion response

        Raises:
            NotImplementedError: If not implemented by subclass
        """
        # Make this a generator to satisfy the type checker
        # Subclasses must override with actual implementation
        yield  # type: ignore
        raise NotImplementedError("Subclass must implement process() method")

    async def initialize(self) -> None:
        """
        Initialize the agent.

        Called during application startup. Override in subclasses for initialization logic.
        """

    async def shutdown(self) -> None:
        """
        Shutdown the agent.

        Called during application shutdown. Override in subclasses for cleanup logic.
        """
