"""
Configuration management using Pydantic Settings.

This module handles all environment-based configuration for the Template Service application,
including API settings, LLM model configuration, and external service connections.
"""

from typing import TYPE_CHECKING, Any

from pydantic import Field, HttpUrl, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from workflow.models.chains import ChainConfig


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables and .env file.

    Follows Pydantic BaseSettings best practices for configuration management.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # API Configuration
    api_host: str = Field(default="0.0.0.0", description="API server host address")
    api_port: int = Field(default=8000, description="API server port")
    api_title: str = Field(default="Prompt Chaining Workflow", description="API title")
    api_version: str = Field(default="0.4.1", description="API version")

    # Environment
    environment: str = Field(
        default="development",
        description="Deployment environment",
        pattern="^(development|staging|production|test)$",
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level",
        pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
    )
    log_format: str = Field(
        default="json",
        description="Logging format",
        pattern="^(json|standard)$",
    )

    # Claude API Configuration
    anthropic_api_key: str = Field(
        description="Anthropic API key for Claude models",
        min_length=1,
    )

    # Service Model Display Name
    service_model_name: str = Field(
        default="prompt-chaining",
        description="Display name for service model in API responses",
    )

    # CORS Configuration
    cors_origins: list[str] = Field(
        default=["*"],  # Allow all origins for development
        description="Allowed CORS origins",
    )
    cors_allow_credentials: bool = Field(
        default=False,  # Must be False when using wildcard
        description="Allow CORS credentials",
    )
    cors_allow_methods: list[str] = Field(
        default=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        description="Allowed CORS methods",
    )
    cors_allow_headers: list[str] = Field(
        default=["Content-Type", "Authorization"],
        description="Allowed CORS headers",
    )

    # Request Validation
    max_request_body_size: int = Field(
        default=1048576,  # 1 MB in bytes
        description="Maximum request body size in bytes",
        ge=1024,  # Minimum 1 KB
        le=10485760,  # Maximum 10 MB
    )

    # Optional: Loki logging endpoint
    loki_url: HttpUrl | None = Field(
        default=None,
        description="Loki log aggregation endpoint",
    )

    # Streaming Configuration
    streaming_timeout: int = Field(
        default=60,
        description="Deprecated: use analyze_timeout, process_timeout, and synthesize_timeout",
        ge=1,
        le=300,
    )
    streaming_chunk_buffer: int = Field(
        default=0,
        description="Number of characters to buffer before yielding (0=no buffering)",
        ge=0,
        le=1000,
    )
    worker_coordination_timeout: int = Field(
        default=45,
        description="Maximum time for all non-synthesis steps in seconds (deprecated)",
        ge=1,
        le=270,
    )
    synthesis_timeout: int = Field(
        default=30,
        description="Maximum time for synthesize step in seconds (deprecated, use chain_synthesize_timeout)",
        ge=1,
        le=270,
    )

    # JWT Authentication Configuration
    jwt_secret_key: str = Field(
        description="Secret key for JWT token signing and verification (minimum 32 characters for security)",
        min_length=32,
    )
    jwt_algorithm: str = Field(
        default="HS256",
        description="Algorithm used for JWT signing (HS256 recommended)",
    )

    # Security Headers Configuration
    enable_security_headers: bool = Field(
        default=True,
        description="Enable security headers (X-Content-Type-Options, X-Frame-Options, HSTS, X-XSS-Protection)",
    )

    # Rate Limiting Configuration
    rate_limit_enabled: bool = Field(
        default=True,
        description="Enable rate limiting for API endpoints",
    )
    rate_limit_default: str = Field(
        default="100/hour",
        description="Default rate limit applied globally (format: count/time_unit)",
    )
    rate_limit_chat_completions: str = Field(
        default="10/minute",
        description="Rate limit for chat completions endpoint (format: count/time_unit)",
    )
    rate_limit_models: str = Field(
        default="60/minute",
        description="Rate limit for models listing endpoint (format: count/time_unit)",
    )

    # Circuit Breaker Configuration
    circuit_breaker_enabled: bool = Field(
        default=True,
        description="Enable circuit breaker pattern for external API calls",
    )
    circuit_breaker_failure_threshold: int = Field(
        default=3,
        description="Number of consecutive failures before opening circuit",
        ge=1,
        le=10,
    )
    circuit_breaker_timeout: int = Field(
        default=30,
        description="Seconds to wait before attempting half-open state",
        ge=10,
        le=300,
    )
    circuit_breaker_half_open_attempts: int = Field(
        default=1,
        description="Number of test attempts in half-open state",
        ge=1,
        le=5,
    )

    # Retry Configuration
    retry_max_attempts: int = Field(
        default=3,
        description="Maximum retry attempts for retryable errors",
        ge=1,
        le=10,
    )
    retry_exponential_multiplier: float = Field(
        default=1.0,
        description="Multiplier for exponential backoff",
        ge=0.5,
        le=5.0,
    )
    retry_exponential_max: int = Field(
        default=30,
        description="Maximum wait time in seconds for exponential backoff",
        ge=5,
        le=300,
    )

    # Prompt-Chaining Configuration
    chain_analyze_model: str = Field(
        default="claude-haiku-4-5-20251001",
        description="Model ID for the analyze step in prompt-chaining",
    )
    chain_analyze_max_tokens: int = Field(
        default=2048,
        description="Max tokens for analyze step",
        ge=1,
        le=8000,
    )
    chain_analyze_temperature: float = Field(
        default=0.5,
        description="Temperature for analyze step",
        ge=0.0,
        le=2.0,
    )
    chain_analyze_timeout: int = Field(
        default=15,
        description="Timeout in seconds for analyze step",
        ge=1,
        le=270,
    )

    chain_process_model: str = Field(
        default="claude-haiku-4-5-20251001",
        description="Model ID for the process step in prompt-chaining",
    )
    chain_process_max_tokens: int = Field(
        default=2048,
        description="Max tokens for process step",
        ge=1,
        le=8000,
    )
    chain_process_temperature: float = Field(
        default=0.7,
        description="Temperature for process step",
        ge=0.0,
        le=2.0,
    )
    chain_process_timeout: int = Field(
        default=30,
        description="Timeout in seconds for process step",
        ge=1,
        le=270,
    )

    chain_synthesize_model: str = Field(
        default="claude-haiku-4-5-20251001",
        description="Model ID for the synthesize step in prompt-chaining",
    )
    chain_synthesize_max_tokens: int = Field(
        default=2048,
        description="Max tokens for synthesize step",
        ge=1,
        le=8000,
    )
    chain_synthesize_temperature: float = Field(
        default=0.5,
        description="Temperature for synthesize step",
        ge=0.0,
        le=2.0,
    )
    chain_synthesize_timeout: int = Field(
        default=20,
        description="Timeout in seconds for synthesize step",
        ge=1,
        le=270,
    )

    chain_enable_validation: bool = Field(
        default=True,
        description="Enable validation gates between prompt-chaining steps",
    )
    chain_strict_validation: bool = Field(
        default=False,
        description="Enforce strict validation in prompt-chaining steps",
    )

    @computed_field
    @property
    def base_url(self) -> str:
        """Computed property for base API URL."""
        protocol = "http" if self.environment == "development" else "https"
        return f"{protocol}://{self.api_host}:{self.api_port}"

    @computed_field
    @property
    def model_pricing(self) -> dict[str, dict[str, float]]:
        """
        Computed property for model pricing information.

        Returns Anthropic API pricing for supported models in USD per 1M tokens.
        Used by token tracking utilities for cost calculation.
        """
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

    def get_log_config(self) -> dict[str, Any]:
        """Get logging configuration dictionary."""
        return {
            "level": self.log_level,
            "format": self.log_format,
            "loki_url": str(self.loki_url) if self.loki_url else None,
        }

    @property
    def chain_config(self) -> "ChainConfig":
        """
        Build and return ChainConfig for the prompt-chaining workflow.

        Constructs a ChainConfig instance from Settings fields, mapping:
        - Analyze step: chain_analyze_* settings
        - Process step: chain_process_* settings
        - Synthesize step: chain_synthesize_* settings
        - Timeouts and validation gates

        Returns:
            ChainConfig instance ready for use with build_chain_graph()

        Raises:
            ImportError: If ChainConfig import fails
        """
        # Lazy import to avoid circular dependencies
        from workflow.models.chains import ChainConfig, ChainStepConfig

        return ChainConfig(
            analyze=ChainStepConfig(
                model=self.chain_analyze_model,
                max_tokens=self.chain_analyze_max_tokens,
                temperature=self.chain_analyze_temperature,
                system_prompt_file="chain_analyze.md",
            ),
            process=ChainStepConfig(
                model=self.chain_process_model,
                max_tokens=self.chain_process_max_tokens,
                temperature=self.chain_process_temperature,
                system_prompt_file="chain_process.md",
            ),
            synthesize=ChainStepConfig(
                model=self.chain_synthesize_model,
                max_tokens=self.chain_synthesize_max_tokens,
                temperature=self.chain_synthesize_temperature,
                system_prompt_file="chain_synthesize.md",
            ),
            analyze_timeout=self.chain_analyze_timeout,
            process_timeout=self.chain_process_timeout,
            synthesize_timeout=self.chain_synthesize_timeout,
            enable_validation=self.chain_enable_validation,
            strict_validation=self.chain_strict_validation,
        )
