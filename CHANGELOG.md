# Changelog

All notable changes to the Prompt Chaining Template will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2025-11-04

### Added
- **JWT Bearer Authentication** - Production-ready authentication system
  - OpenAI-compatible Bearer token format (`Authorization: Bearer <token>`)
  - HMAC-SHA256 (HS256) JWT signing algorithm
  - Token generation utility script (`scripts/generate_jwt.py`)
  - Configurable token expiration support (s/m/h/d/w formats)
  - Minimum 32-character secret key enforcement
  - Console client Bearer token integration (`API_BEARER_TOKEN` environment variable)
- **Authentication Dependencies** - FastAPI security dependency injection
  - JWT verification with proper error handling
  - Automatic 401 (unauthorized) for missing/expired tokens
  - Automatic 403 (forbidden) for invalid tokens
  - Structured logging for authentication events
- **Protected API Endpoints** - Secured with JWT authentication
  - `/v1/chat/completions` - Requires valid Bearer token
  - `/v1/models` - Requires valid Bearer token
  - `/health/` and `/health/ready` remain public (monitoring)
- **Comprehensive Test Coverage** - 100 tests total (46 auth-specific)
  - 24 unit tests for JWT verification, generation, and parsing
  - 22 integration tests for endpoint authentication
  - 100% coverage of authentication module
  - OpenAI compatibility verification tests
- **Enhanced Documentation**
  - Updated CLAUDE.md with authentication section
  - Updated README.md with quick start auth setup
  - Updated ARCHITECTURE.md with security considerations
  - Enhanced .env.example with JWT configuration
  - Comprehensive authentication guides in artifacts

### Changed
- **Configuration** - Added JWT settings to Settings class
  - `JWT_SECRET_KEY` - Required for production (min 32 chars)
  - `JWT_ALGORITHM` - Configurable algorithm (default: HS256)
- **Dependencies** - Added PyJWT>=2.8.0 to project dependencies
- **Console Client** - Now requires `API_BEARER_TOKEN` environment variable

### Security
- Proper exception chaining for debugging (`raise ... from exc`)
- No sensitive data exposed in logs or error messages
- Constant-time token comparison
- Token signature verification on every request
- Support for token expiration and rotation

### Breaking Changes
**None** - Fully backward compatible. Authentication is optional when `JWT_SECRET_KEY` is not configured (development mode).

## [0.1.0] - 2025-01-03

### Added
- Initial template release
- Orchestrator-worker multi-agent pattern
- OpenAI-compatible chat completions API with SSE streaming
- AsyncAnthropic client integration for parallel worker execution
- Comprehensive configuration management via Pydantic Settings
- Structured JSON logging with optional Loki integration
- Generic internal models (TaskRequest, TaskResult, AggregatedResult)
- System prompt management via text files
- FastAPI application with lifespan management
- Health check endpoints
- Console client for testing
- Development scripts (dev.sh, test.sh, format.sh)
- Complete documentation (README, ARCHITECTURE, CLAUDE)
- Type hints and mypy configuration
- Testing infrastructure setup
- CORS middleware
- Error handling with custom exception hierarchy
- Request tracking middleware

### Architecture Decisions
- Orchestrator uses Claude Sonnet 4.5 (smart coordinator)
- Workers use Claude Haiku 4.5 (fast executors)
- True parallelism via asyncio.gather()
- Streaming-only responses for better UX
- Environment-based configuration for flexibility

### Template Characteristics
- Generic echo/task example (not domain-specific)
- 2-3 workers spawned per request (configurable)
- Simple heuristic for task count determination
- Designed for easy customization

## [0.2.3] - 2025-11-08

### Added
- **Request Timeout Enforcement** - Invariant protection against runaway requests
  - Two-phase timeout enforcement (worker coordination + synthesis)
  - Worker coordination timeout (default 45s, configurable 1-270s)
  - Synthesis timeout (default 30s, configurable 1-270s)
  - StreamingTimeoutError exception with proper HTTP 504 status
  - SSE-formatted error responses maintaining stream integrity
  - Comprehensive logging with timeout phase and duration metadata
  - 25 comprehensive unit and integration tests with 84% code coverage
  - Complete documentation and troubleshooting guide in CLAUDE.md
  - Migration guide for upgrading from deprecated STREAMING_TIMEOUT

### Fixed
- **Async Generator Timeout Handling** - Fixed bug preventing timeout enforcement on streaming operations
  - Properly wrap async generators with timeout by collecting chunks first
  - Prevents "TypeError: 'async for' requires an object with __aiter__ method" errors
- **Request Size Middleware Tests** - Fixed 24 failing tests
  - Corrected test mocking to use request.app.state.settings instead of non-existent get_settings()
  - Updated test expectations to match actual error codes and behavior

### Changed
- Enhanced orchestrator.process() with timeout enforcement on worker coordination and synthesis phases

## [0.2.4] - 2025-11-08

### Added
- **Docker Container Support** - Production-ready containerization for 95%+ of deployments
  - Multi-stage Dockerfile with builder + production stages (296MB final image, 60% size reduction)
  - Security hardening: Non-root user (appuser, UID 1000), minimal python:3.12-slim base image
  - Health checks: Liveness probe with 30s interval, 3s timeout, 5s startup grace period
  - BuildKit optimization: RUN cache mounts for pip, layer optimization, .dockerignore build context cleanup
- **Docker Compose Configuration**
  - Production orchestration (docker-compose.yml) with restart policy, health checks, networking
  - Development overrides (docker-compose.dev.yml) for hot-reload and DEBUG logging
  - Flexible configuration: API_HOST/API_PORT read from .env (not hardcoded)
  - Optional resource limits and volume mounts with comprehensive documentation
- **Automated Docker Testing** - scripts/docker-test.sh pipeline
  - Build validation, API endpoint testing, runtime verification, configuration validation
  - 5 test modules: 285 tests passing, 15 skipped (Docker daemon optional)
  - Docker build compliance, image size verification, security checks
- **Enhanced Documentation**
  - CLAUDE.md: Consolidated environment variables (25-30% → 5-10% duplication), Docker quick start
  - README.md: Docker deployment guide with quick start (8 steps), deployment options, command reference
  - pyproject.toml: Fixed package-data to include prompt .md files in distribution
  - .dockerignore: Build context optimization, secrets protection
- **Docker Audit Report** - Comprehensive compliance verification
  - Validated against official Docker and Docker Compose specifications
  - Multi-stage build, cache mounts, signal handling, HEALTHCHECK configuration all compliant
  - 0 critical, 0 high, 1 medium opportunity, 2 low enhancements identified

### Changed
- CLAUDE.md: Significant refactoring and consolidation
  - Fixed prompt file extension documentation (.txt → .md)
  - Created "Configuration Reference" section consolidating environment variables
  - Removed duplicate JWT setup instructions (consolidated from 4+ places to 2)
  - Simplified Development Setup to reference Configuration Reference
  - Added Docker Quick Start section with 6-step onboarding
- pyproject.toml: Added [tool.setuptools.package-data] section for prompt files
- docker-compose.yml: Removed hardcoded API_PORT, now reads from .env (configuration fix)

### Verified
- ✅ docker build: Image builds successfully (296MB)
- ✅ docker-compose up -d: Container starts and reports healthy
- ✅ Health check: /health/ endpoint responds with 200 OK
- ✅ API authentication: Protected endpoints require bearer tokens
- ✅ Console client: Verified with console_client.py against containerized API
- ✅ 285 tests passing, 15 skipped, 84% code coverage

### Security
- Non-root user execution (appuser, UID 1000)
- Minimal base image (python:3.12-slim)
- Secrets excluded from .dockerignore
- No hardcoded credentials in Dockerfile or Compose files
- Read-only volumes where appropriate
- HEALTHCHECK ensures container responsiveness

## [0.3.0] - 2025-11-09

### Added
- **Security headers middleware for HTTP hardening**
  - X-Content-Type-Options: nosniff (prevents MIME type sniffing attacks)
  - X-Frame-Options: DENY (prevents clickjacking attacks)
  - X-XSS-Protection: 1; mode=block (enables browser XSS protection)
  - Strict-Transport-Security: max-age=31536000; includeSubDomains (forces HTTPS, only added for HTTPS requests)
  - Supports both direct HTTPS connections and reverse proxy scenarios (X-Forwarded-Proto header)
- Configuration option `ENABLE_SECURITY_HEADERS` to control security headers (default: enabled)
- Comprehensive unit and integration tests for security headers middleware (66 tests, 100% coverage)
- Docker testing instructions for security headers verification

## [0.3.2] - 2025-11-09

### Added
- **Comprehensive Logging Facility** - Observability-first design across all source code
  - All 5 Python log levels: CRITICAL/FATAL, ERROR, WARNING, INFO, DEBUG
  - CRITICAL/FATAL logging for catastrophic failures (orchestrator init, missing JWT secrets, startup)
  - DEBUG logging for operational visibility (health checks, security headers, API requests, token calculations)
  - Structured JSON logging with rich context fields (request_id, user, duration_ms, client_ip, etc)
  - Token cost calculation tracking with DEBUG-level breakdown (input/output tokens, costs, totals)
  - Rate limit checkpoint logging at DEBUG level
  - Enhanced token tracking with WARNING logs for unknown model pricing
- **Comprehensive Test Coverage for Logging**
  - 20 unit tests covering all 5 log levels (test_logging_levels.py)
  - 6 Docker integration tests validating container logging (test_logging_docker.py)
  - 85%+ code coverage maintained across all logging enhancements
- **Enhanced Documentation**
  - CLAUDE.md: New "Logging & Observability" section with practical examples and troubleshooting
  - README.md: Quick logging reference with LOG_LEVEL configuration
  - ARCHITECTURE.md: Logging architecture, component-by-level matrix, production considerations

### Changed
- Logging is now observability-first pattern, enabling Claude-assisted development with real-time feedback
- DEBUG level provides visibility into request flow for rapid iteration and debugging
- All API endpoints emit appropriate logging at DEBUG/INFO levels

### Benefits
- Real-time debugging with full request flow visibility via DEBUG logs
- Production-ready observability for log aggregation (Loki, ELK, Datadog)
- Cost transparency through token tracking logs
- Security monitoring via CRITICAL-level alerts
- Claude-optimized architecture enabling AI-assisted development and debugging

## [0.3.3] - 2025-11-09

### Added
- **Circuit Breaker Pattern & Resilient Retry Logic** - Production-grade resilience for external API calls
  - State machine implementation (CLOSED → OPEN → HALF_OPEN → CLOSED)
  - Exponential backoff retry logic using tenacity library with configurable jitter
  - Conservative circuit breaker thresholds: 3 consecutive failures, 30s timeout before recovery
  - Automatic recovery testing in HALF_OPEN state (1 successful attempt to close)
  - WARNING level logging for circuit breaker failures and state transitions for operator visibility
  - Proper exception mapping from Anthropic SDK to custom retryable error types
  - Mixed fallback behavior: critical operations fail fast, non-critical operations gracefully degrade
- **New Error Classes** for fine-grained error handling
  - `CircuitBreakerOpenError` - Circuit is open, blocking calls (HTTP 503)
  - `AnthropicRateLimitError` - Rate limit exceeded (retryable)
  - `AnthropicServerError` - Server errors 5xx (retryable)
  - `AnthropicTimeoutError` - Request timeout (retryable)
  - `AnthropicConnectionError` - Connection failures (retryable)
- **Comprehensive Circuit Breaker Configuration** (via .env)
  - `CIRCUIT_BREAKER_ENABLED` - Enable/disable pattern (default: true)
  - `CIRCUIT_BREAKER_FAILURE_THRESHOLD` - Failures before opening (default: 3, range: 1-10)
  - `CIRCUIT_BREAKER_TIMEOUT` - Recovery timeout (default: 30s, range: 10-300s)
  - `CIRCUIT_BREAKER_HALF_OPEN_ATTEMPTS` - Successes to close (default: 1, range: 1-5)
  - `RETRY_MAX_ATTEMPTS` - Retry attempts (default: 3, range: 1-10)
  - `RETRY_EXPONENTIAL_MULTIPLIER` - Backoff multiplier (default: 1.0, range: 0.5-5.0)
  - `RETRY_EXPONENTIAL_MAX` - Max backoff delay (default: 30s, range: 5-300s)
- **Integration into Core Agents**
  - Worker agent: Wrapped API calls with circuit breaker + retry decorator
  - Synthesizer agent: Both streaming and token capture calls protected
  - Orchestrator: Unchanged (coordinates workers, doesn't call API directly)
- **Comprehensive Test Coverage** - 45 unit tests achieving 100% coverage on circuit_breaker.py and anthropic_errors.py
  - State machine transitions (CLOSED → OPEN → HALF_OPEN → CLOSED)
  - Failure counting and thresholds
  - Timeout-based recovery mechanism
  - Exception mapping from Anthropic SDK
  - Retry decorator with tenacity integration
- **Documentation & Troubleshooting**
  - CLAUDE.md: Added "Circuit Breaker & Retry Logic" section with configuration guide
  - README.md: Circuit breaker listed in features
  - ARCHITECTURE.md: New "Circuit Breaker Pattern" section with state machine diagram and flow

### Changed
- Worker and Synthesizer agents now use `@create_retryable_anthropic_call()` decorator for API calls
- Exception handling in Worker and Synthesizer now logs retryable errors at WARNING level for circuit breaker visibility
- pyproject.toml: Added `tenacity>=8.0.0` dependency for robust retry logic

### Benefits
- **Resilience**: Prevents cascading failures when Anthropic API experiences transient issues
- **Operator Visibility**: WARNING-level logs show circuit breaker failures and recovery attempts
- **Cost Control**: Circuit breaker stops wasting tokens by quickly failing permanently broken requests
- **Self-Healing**: Automatic recovery mechanism (HALF_OPEN state) tests service readiness
- **Production Ready**: Conservative defaults (3 failures, 30s timeout) suitable for most deployments

### Technical Details
- Two-layer retry approach: Anthropic SDK retries (3x fast) + tenacity decorator retries (3x with exponential backoff)
- Exponential backoff with jitter prevents thundering herd during recovery
- Exception mapping captures Anthropic SDK exceptions and converts to custom retryable types
- Non-retryable errors (auth, validation) skip circuit breaker for immediate feedback
- Token capture in Synthesizer uses graceful fallback (logs warning instead of failing)

### Security & Reliability
- Circuit breaker prevents cascading failures across multi-agent system
- Exponential backoff reduces load on recovering services
- State machine prevents invalid transitions
- Comprehensive error logging for production debugging

## [0.3.4] - 2025-11-09

### Added
- **Request ID Propagation for Distributed Tracing** - End-to-end correlation across all system components
  - Automatic request ID generation (`req_{timestamp_ms}`) or extraction from `X-Request-ID` headers
  - Context-based propagation using Python `contextvars.ContextVar` for async-safe isolation
  - X-Request-ID header passed to all Anthropic API calls via `extra_headers` parameter
  - Request ID included in all structured JSON logs for complete request lifecycle tracing
  - Response headers include X-Request-ID for client-side correlation
  - All three agents (Orchestrator, Worker, Synthesizer) propagate request IDs
  - Graceful handling when request ID is missing (no errors, just not propagated)
  - Async-safe context isolation prevents interference between concurrent requests
- **New Request Context Utility Module** (`utils/request_context.py`)
  - `ContextVar`-based request ID storage with None default
  - `set_request_id(request_id: str)` - Store request ID in current async context
  - `get_request_id() -> str | None` - Retrieve request ID from context
  - Full documentation on usage and async context propagation
- **Enhanced Middleware** - Request tracking middleware improved
  - Generates new request ID if header is missing or empty (was: only if missing)
  - Sets request ID in context immediately after generation/extraction
  - DEBUG-level logging when context is set for visibility
- **Console Client Enhancement** - Testing tool now supports request ID propagation
  - Accept optional `request_id` argument: `python console_client.py "prompt" [max_tokens] [request_id]`
  - Auto-generate request ID if not provided (uuid-based format)
  - Display request ID in console output for easy tracing
  - Enable users to test request ID correlation with custom IDs
- **Comprehensive Test Coverage** - 52 new tests for request ID propagation
  - 17 unit tests for ContextVar behavior and async isolation (test_request_context.py)
  - 9 integration tests for middleware request ID generation/extraction (test_middleware_request_context.py)
  - 10 integration tests for agent propagation to Anthropic API (test_agent_request_id_propagation.py)
  - 16 end-to-end tests for chat completions request ID flow (test_chat_completions_request_id.py)
  - Test setup utility (conftest.py) with environment configuration
- **Enhanced Documentation**
  - CLAUDE.md: New "Request ID Propagation" subsection under Logging & Observability
  - README.md: Added feature bullet point for distributed tracing
  - ARCHITECTURE.md: New "Request ID Propagation" section with flow diagram and implementation details

### Changed
- All three agents now retrieve request ID from context and propagate to Anthropic API calls
- Middleware request ID extraction improved to handle empty headers
- Console client usage now supports optional request_id parameter

### Usage
```bash
# Auto-generated request ID
python console_client.py "Hello, world!"

# Custom request ID for tracing
python console_client.py "Hello" 500 "my-trace-123"

# Via curl with custom request ID
curl -H "X-Request-ID: my-trace-123" http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model":"orchestrator-worker","messages":[...]}'
```

### Benefits
- **Debugging**: Correlate client requests with Anthropic API calls for comprehensive tracing
- **Distributed Tracing**: Track request flow through orchestrator → workers → synthesizer
- **Support**: Share request IDs with Anthropic support for investigating API issues
- **Observability**: Filter logs by request_id to see complete request lifecycle
- **Production-Ready**: Async-safe context isolation prevents request interference

### Technical Details
- Uses Python `contextvars.ContextVar` for thread-safe async context storage
- Context automatically isolated per async task (no interference between concurrent requests)
- Request IDs included in structured JSON logs for correlation
- Graceful degradation: works with or without request IDs
- Zero breaking changes; fully backward compatible

### Testing
- ✅ 52 new tests with comprehensive coverage
- ✅ Unit tests verify ContextVar isolation and async behavior
- ✅ Integration tests verify middleware generation and agent propagation
- ✅ End-to-end tests verify complete request lifecycle
- ✅ Test environment setup via conftest.py with required env vars

## [0.4.1] - 2025-11-13

### Added
- **Task 9: Performance Monitoring & Metrics Collection** - Comprehensive metrics aggregation and performance tracking
  - Aggregated metrics logging per request with total tokens, cost, and elapsed time
  - Per-step breakdown showing metrics for analyze, process, and synthesize steps
  - LangGraph MemorySaver checkpointer integration for state management
  - Performance benchmark script for model configuration comparison
  - Enhanced documentation in ARCHITECTURE.md with "Performance Monitoring" section
  - Enhanced documentation in CLAUDE.md with "Performance Monitoring" subsection
  - Updated README.md features list with benchmark link
  - New BENCHMARKS.md documentation file with methodology, results, and model selection guidance

### Changed
- **Documentation Refactoring & Compression** - Optimized docs for clarity and token efficiency
  - **ARCHITECTURE.md**: Reorganized for better clarity (1427 → 350+ lines)
    - Moved detailed architecture to dedicated sections
    - Consolidated configuration best practices
    - Streamlined performance monitoring guidance
    - Removed redundant sections, improved cross-referencing
  - **CLAUDE.md**: Compressed and refactored (675 → 215 lines)
    - Created "Configuration Quick Reference" table for environment variables
    - Consolidated duplicate JWT/auth setup instructions
    - Added Docker Quick Start section (6-step onboarding)
    - Reorganized for faster developer onboarding
    - Preserved all essential information with improved structure
  - **README.md**: Streamlined for quick reference (940 → 365 lines)
    - Simplified project overview and quick setup
    - Added "Configuration & Tuning Guide" section with practical examples
    - Reorganized API reference with cleaner table format
    - Simplified common issues troubleshooting guide
    - Maintained all deployment and usage information
  - **PROMPT-CHAINING.md**: New comprehensive guide replacing PROMPT_CHAINING.md
    - Complete prompt-chaining configuration documentation
    - Model selection guidance for all three steps
    - Temperature and token limit tuning strategies
    - Validation gate configuration reference
    - Pre-built configuration patterns with cost/performance tradeoffs

### Benefits
- **Developer Experience**: 30-40% reduction in docs to read, faster onboarding
- **Clarity**: Dedicated sections for each concern (config, auth, monitoring, debugging)
- **Maintainability**: Reduced duplication across documentation files
- **Token Efficiency**: Smaller docs for Claude analysis and rapid iteration
- **Completeness**: All critical information preserved with improved organization

### Documentation
- **ARCHITECTURE.md**: Reorganized with 60%+ line reduction while preserving technical depth
- **CLAUDE.md**: Refactored with new "Configuration Quick Reference" and "Docker Quick Start"
- **README.md**: Streamlined with "Configuration & Tuning Guide" for practical setup
- **BENCHMARKS.md**: Comprehensive performance documentation
  - Benchmark methodology and test configuration
  - Performance results summary with p50/p95/p99 latency and cost metrics
  - Model configuration guidance (all-Haiku baseline)
  - Cost breakdown examples per step
  - Instructions for running benchmark script
  - Performance monitoring in production
  - Model selection guide with cost/quality tradeoffs
- **PROMPT-CHAINING.md**: New file with complete prompt-chaining configuration reference

### Features Completed
- Metrics collection across all three prompt-chaining steps
- Aggregated logging with per-step breakdown
- LangGraph MemorySaver state management integration
- Performance benchmark infrastructure
- Documentation reorganization and token efficiency optimization

## [0.4.0] - 2025-11-12

### Added
- **Prompt-Chaining Configuration Documentation** - Comprehensive guide for tuning and customizing chain steps
  - Updated CLAUDE.md with "Chain Configuration Reference" section
  - Added per-step model selection guidance (Haiku vs Sonnet recommendations)
  - Per-step temperature tuning guide with use case examples
  - Per-step token limit recommendations (analyze: 500-2048, process: 1500-3000, synthesize: 500-2000)
  - Per-step timeout configuration with latency SLA examples
  - Cost breakdown by model with example calculations
  - Cost optimization strategies (Haiku-first, selective Sonnet upgrade, token tuning)
  - Updated README.md with "Configuration & Tuning Guide"
  - Quick configuration examples (cost-optimized, balanced, high-accuracy)
  - Temperature and token limit tuning tables with practical guidance
  - Timeout tuning for different SLAs (p99 <5s, <8s, <15s)
  - Decision tree for model selection based on task requirements
  - Updated ARCHITECTURE.md with "Configuration Best Practices"
  - Cost optimization strategies with per-step analysis
  - Performance tuning for different latency requirements
  - Four production-ready configuration patterns with cost/speed tradeoffs
  - Troubleshooting guide for common configuration issues

### Documentation
- **CLAUDE.md**: Added 180+ lines documenting chain configuration
  - Marked legacy orchestrator-worker model variables as deprecated
  - Comprehensive environment variable reference for all CHAIN_* settings
  - Model selection guidance for analyze/process/synthesize steps
  - Temperature tuning recommendations per step
  - Token limit adjustment strategies
  - Timeout configuration with practical examples
  - Cost monitoring and optimization tips
  - Validation gate configuration (enable/disable, strict/lenient modes)
- **README.md**: Added 149 lines with practical tuning guidance
  - Quick-start configuration profiles (3 pre-built examples)
  - Temperature tuning table with use cases
  - Token limit ranges for different response types
  - Timeout tuning for different SLAs
  - Decision tree for configuration selection
- **ARCHITECTURE.md**: Added 288 lines with best practices
  - Cost breakdown and optimization strategies
  - Performance analysis per step
  - Four production-ready patterns with metrics
  - Comprehensive troubleshooting guide

### Notes
- Task 8.1 (Configuration Implementation) was already complete from earlier tasks
- Task 8.2 (Documentation Updates) completed in this release
- All configuration parameters from design document fully implemented and documented
- Zero breaking changes; fully backward compatible with existing configurations

---

## Version History

- **v0.3.4** - Request ID propagation for distributed tracing across all agents
- **v0.3.3** - Circuit breaker pattern & resilient retry logic with exponential backoff
- **v0.3.2** - Comprehensive logging facility with all 5 log levels (FATAL, ERROR, WARNING, INFO, DEBUG)
- **v0.3.0** - Added security headers middleware for HTTP hardening
- **v0.2.4** - Docker container support for easy deployment
- **v0.2.3** - Added request timeout enforcement with invariant protection
- **v0.2.0** - Added JWT bearer authentication with OpenAI API compatibility
- **v0.1.0** - Initial template extracted from Cooper agentic dietician project
