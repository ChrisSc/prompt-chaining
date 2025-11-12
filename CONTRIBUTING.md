# Contributing to Agentic Orchestrator Worker Template

Thank you for your interest in contributing! This template provides the foundation for building multi-agent orchestration services, and we value contributions that improve the template for everyone.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Before You Start](#before-you-start)
- [Development Setup](#development-setup)
- [Critical Development Rules](#critical-development-rules)
- [Making Changes](#making-changes)
- [Test Requirements](#test-requirements)
- [Code Quality Standards](#code-quality-standards)
- [Customization vs. Template Improvements](#customization-vs-template-improvements)
- [Documentation Requirements](#documentation-requirements)
- [Pull Request Process](#pull-request-process)
- [Common Issues & Troubleshooting](#common-issues--troubleshooting)
- [Getting Help](#getting-help)

## Code of Conduct

This project adheres to a Code of Conduct that we expect all contributors to follow. Please read [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) before contributing.

## Before You Start

### Understanding This Project

This is a **template project** designed for customization, not a finished application. It provides:

- Multi-agent orchestration pattern (Orchestrator → Workers → Synthesizer)
- OpenAI-compatible API endpoints with FastAPI
- JWT bearer authentication
- Streaming responses with Server-Sent Events
- Token tracking and cost monitoring

### What We're Looking For

We welcome contributions that:

- **Improve the template foundation** - Better patterns, clearer abstractions, enhanced features
- **Fix bugs** - Issues that affect template functionality
- **Enhance documentation** - Clearer explanations, better examples
- **Add tests** - Improve coverage and reliability
- **Optimize performance** - Reduce latency, improve cost efficiency

**Note:** If you're customizing this template for your specific use case, those changes should remain in your fork. See [Customization vs. Template Improvements](#customization-vs-template-improvements) for guidance.

### Prerequisites

- **Python 3.10+** (strict requirement)
- **Anthropic API key** (for Claude API access)
- **Understanding of async Python** (asyncio, async/await patterns)
- **Familiarity with FastAPI** (helpful but not required)

## Development Setup

### 1. Clone and Set Up Environment

```bash
# Clone or fork the repository
git clone https://github.com/yourusername/agentic-orchestrator-worker-template.git
cd agentic-orchestrator-worker-template

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install with development dependencies
pip install -e ".[dev]"
```

### 2. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Generate secure JWT secret (minimum 32 characters)
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Edit .env and add:
#   - ANTHROPIC_API_KEY=<your-key>
#   - JWT_SECRET_KEY=<generated-secret>
#   - Other optional settings
```

### 3. Verify Setup

```bash
# Start development server
./scripts/dev.sh

# In another terminal, run tests
./scripts/test.sh

# Check code quality
./scripts/format.sh
```

If all three commands succeed, you're ready to contribute!

## Critical Development Rules

These rules are **non-negotiable** and must be followed in all contributions:

### 1. Import Convention (CRITICAL)

**✅ Correct:**
```python
from orchestrator_worker.config import Settings
from orchestrator_worker.agents.base import Agent
```

**❌ Wrong:**
```python
from src.orchestrator_worker.config import Settings  # Will break!
```

**Why:** FastAPI CLI (`fastapi dev`) requires relative imports for proper module discovery. Absolute imports starting with `src.` will cause import errors.

### 2. Use FastAPI CLI, Not Uvicorn

**✅ Correct:**
```bash
fastapi dev src/orchestrator_worker/main.py
./scripts/dev.sh  # Uses fastapi dev internally
```

**❌ Wrong:**
```bash
uvicorn src.orchestrator_worker.main:app  # Don't use directly
```

**Why:** FastAPI CLI provides better auto-reload, error messages, and module discovery than uvicorn directly.

### 3. JWT Secret Key Requirements

**Requirements:**
- Minimum 32 characters
- Use cryptographically secure random generation
- Never commit to version control

**Generation:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 4. Type Hints Required

All functions and methods must have complete type hints:

```python
from typing import AsyncIterator
from orchestrator_worker.models.openai import ChatCompletionChunk

async def process(self, request: TaskRequest) -> AsyncIterator[ChatCompletionChunk]:
    """Process a task request and yield streaming chunks."""
    # Implementation
```

**Why:** Strict mypy checking is enabled. Missing type hints will fail CI checks.

### 5. Async/Await Patterns

All I/O operations must use async/await:

```python
# ✅ Correct
async def fetch_data(self) -> dict:
    async with AsyncAnthropic() as client:
        response = await client.messages.create(...)
        return response

# ❌ Wrong
def fetch_data(self) -> dict:
    client = Anthropic()  # Blocking!
    response = client.messages.create(...)
    return response
```

## Making Changes

### 1. Create a Feature Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/bug-description
```

### 2. Make Your Changes

- **Code:** Modify files in `src/orchestrator_worker/`
- **Tests:** Add/update tests in `tests/`
- **Docs:** Update relevant documentation files

### 3. Test Your Changes

```bash
# Run full test suite with coverage
./scripts/test.sh

# View coverage report
open htmlcov/index.html

# Run specific test file
pytest tests/unit/test_config.py -v
```

### 4. Check Code Quality

```bash
# Format, lint, and type check (must pass)
./scripts/format.sh
```

### 5. Commit and Push

```bash
git add .
git commit -m "Brief description of changes"
git push origin feature/your-feature-name
```

## Test Requirements

### Coverage Target

**Minimum:** 80% code coverage (enforced in CI)

### Test Types

We use three types of tests:

#### 1. Unit Tests (`tests/unit/`)
Test individual components in isolation:
- Configuration
- Models
- Utilities
- Agent methods (with mocked dependencies)

#### 2. Integration Tests (`tests/integration/`)
Test API endpoints with mocked external services:
- Request/response handling
- Authentication
- Error handling
- Streaming responses

#### 3. Manual Tests (`tests/manual/`)
End-to-end tests with live services:
- Live API testing
- Token generation
- Console client testing

### Testing Async Code

Use pytest-asyncio for async tests:

```python
import pytest

@pytest.mark.asyncio
async def test_agent_process():
    agent = Worker()
    await agent.initialize()

    result = await agent.process_task(task_request)

    assert result.success is True
    await agent.shutdown()
```

### Test Organization

- Mirror the `src/` structure in `tests/`
- Use fixtures in `conftest.py` for common setup
- Mock external API calls (Anthropic, etc.)
- Test both success and error paths

## Code Quality Standards

All code must pass these checks before submission:

### Formatting (Black)

```bash
# Format all code
./scripts/format.sh
```

**Configuration:**
- Line length: 100 characters
- Targets: Python 3.10+

### Linting (Ruff)

Active rule sets: E, F, W, I, N, UP, B, A, C4, PIE, PT, RET, SIM, PERF

Common violations to avoid:
- Unused imports
- Unused variables
- Missing docstrings on public APIs
- Unnecessary else after return

### Type Checking (mypy)

Strict mode enabled:
- `disallow_untyped_defs = true`
- `disallow_any_unimported = true`
- `warn_return_any = true`
- `warn_unused_ignores = true`

### Running All Checks

```bash
# This runs Black, Ruff, and mypy
./scripts/format.sh
```

All three must pass before creating a PR.

## Customization vs. Template Improvements

### If You're Customizing for Your Use Case

**These changes stay in YOUR fork:**

- Update system prompts in `src/orchestrator_worker/prompts/`
- Modify internal models in `models/internal.py` for your domain
- Customize agent logic in `agents/` for your workflows
- Add domain-specific endpoints
- Change model IDs, temperatures, or parameters

See [CLAUDE.md Customization Guide](CLAUDE.md#customization-guide) for details.

### If You're Improving the Template

**These contributions can be submitted as PRs:**

- Bug fixes in core functionality
- Performance optimizations
- Better error handling
- Enhanced logging or monitoring
- Improved test coverage
- Documentation improvements
- New generic features that benefit multiple use cases

**Guidelines:**
- Changes should remain **generic** and not domain-specific
- Maintain compatibility with the standard use case
- Keep examples simple and generic (like the current echo example)
- Document trade-offs and design decisions clearly
- Consider impact on users who have already customized the template

## Documentation Requirements

### When to Update Documentation

- **CLAUDE.md** - If adding/changing commands, workflows, or architecture
- **README.md** - If adding user-facing features or changing setup
- **CONTRIBUTING.md** - If changing development workflow or requirements
- **JWT_AUTHENTICATION.md** - If modifying authentication system

### Docstring Standards

Use Google-style or NumPy-style docstrings:

```python
async def process_task(self, task: TaskRequest) -> TaskResult:
    """Process a single task and return the result.

    Args:
        task: The task request containing prompt and parameters

    Returns:
        TaskResult with success status, data, and token usage

    Raises:
        ValidationError: If task request is invalid
        ExternalServiceError: If Claude API call fails
    """
```

### API Changes

If you modify API endpoints or models:
- Update OpenAPI schema (automatic via FastAPI)
- Add examples to documentation
- Note breaking changes clearly
- Update version in `pyproject.toml` (semantic versioning)

## Pull Request Process

### 1. Create Your PR

- **Title:** Clear, concise summary (e.g., "Add retry logic for API calls")
- **Description:** Include:
  - **What:** Summary of changes
  - **Why:** Problem being solved or feature being added
  - **How:** Technical approach taken
  - **Testing:** How to verify the changes work

### 2. PR Description Template

```markdown
## What
Brief description of changes

## Why
Problem being solved or motivation for feature

## How
Technical approach and key implementation details

## Testing
- [ ] All tests pass locally
- [ ] Added new tests for new functionality
- [ ] Manually tested with ./scripts/dev.sh
- [ ] Coverage remains >80%

## Checklist
- [ ] Code follows style guidelines (./scripts/format.sh passes)
- [ ] Documentation updated if needed
- [ ] No breaking changes (or documented with migration guide)
```

### 3. Review Process

- A maintainer will review your PR within 1-2 weeks
- Address feedback promptly
- CI checks must pass (tests, coverage, type checking, linting)
- May require squashing commits before merge

### 4. After Merge

- Your contribution will be noted in CHANGELOG.md
- You'll be added to contributors list in README.md
- Branch will be deleted after merge

## Common Issues & Troubleshooting

### Import Errors

**Problem:** `ModuleNotFoundError: No module named 'src'`

**Solution:**
- Check imports use `orchestrator_worker.*`, not `src.orchestrator_worker.*`
- Verify package installed: `pip install -e ".[dev]"`
- Ensure virtual environment is activated

### FastAPI Discovery Issues

**Problem:** `fastapi dev` can't find the app

**Solution:**
- Use full path: `fastapi dev src/orchestrator_worker/main.py`
- Check that `app = create_app()` exists at module level in main.py
- Verify imports use relative paths

### Authentication Issues

**Problem:** `ValidationError: jwt_secret_key Field required`

**Solution:**
```bash
# Generate secure key
python -c "import secrets; print(secrets.token_urlsafe(32))"
# Add to .env file as JWT_SECRET_KEY=<generated-key>
```

**Problem:** `401 Unauthorized` on protected endpoints

**Solution:**
```bash
# Generate bearer token
export API_BEARER_TOKEN=$(python scripts/generate_jwt.py)
# Use with curl or console_client.py
```

### Test Failures

**Problem:** Tests fail with environment errors

**Solution:**
- Ensure `.env` file exists with required variables
- Check `ANTHROPIC_API_KEY` is valid
- For unit tests, mocks should not require real API keys
- Run with `-v` for verbose output: `pytest -v`

### Type Checking Failures

**Problem:** mypy reports type errors

**Solution:**
- Add type hints to all function parameters and returns
- No implicit `Optional` - use `Optional[T]` or `T | None` explicitly
- Check `pyproject.toml` for mypy configuration
- Common fix: `from typing import Optional`

### Code Coverage Too Low

**Problem:** Coverage drops below 80%

**Solution:**
- Identify untested code: `open htmlcov/index.html`
- Add tests for new functions/classes
- Test both success and error paths
- Use parametrized tests for multiple scenarios

## Getting Help

### Documentation Resources

- **[CLAUDE.md](CLAUDE.md)** - Architecture, commands, development workflow
- **[README.md](README.md)** - Quick start, installation, API reference
- **[JWT_AUTHENTICATION.md](JWT_AUTHENTICATION.md)** - Authentication details
- **[.env.example](.env.example)** - Configuration options

### Community Channels

- **GitHub Issues** - For bug reports and feature requests
- **GitHub Discussions** - For questions, ideas, and general discussion
- **Code Review** - Ask questions in PR comments

### Before Asking

1. Check existing issues and discussions
2. Review documentation (especially CLAUDE.md)
3. Try troubleshooting steps above
4. Search commit history for related changes

### Creating an Issue

For bugs, include:
- Python version
- Steps to reproduce
- Expected vs. actual behavior
- Relevant logs or error messages
- Environment details (OS, dependencies)

For features, include:
- Use case description
- Proposed solution
- Alternatives considered
- Impact on existing users

---

## Recognition

We value all contributions! Contributors will be:
- Mentioned in release notes (CHANGELOG.md)
- Added to contributors section in README.md
- Attributed in commit messages (Co-Authored-By)

Thank you for helping improve this template! 🙏
