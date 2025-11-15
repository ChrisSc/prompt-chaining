# Structured Output Improvements - Integration Testing Guide

## Quick Start

Run all integration tests for structured output improvements:

```bash
# Start Docker container
docker-compose up -d

# Wait for health check
curl http://localhost:8000/health/

# Run tests
python -m pytest tests/integration/test_structured_output_improvements.py -v

# Stop Docker container
docker-compose down
```

## Test Suite Overview

File: `/home/chris/projects/prompt-chaining/tests/integration/test_structured_output_improvements.py`

**Total Tests**: 21
**Categories**: 7 test classes
**Execution Time**: ~4-5 minutes
**Success Rate**: 100% (all pass)

## Test Classes and Coverage

### 1. TestConfigurationLoading (2 tests)

Tests for CHAIN_MIN_CONFIDENCE_THRESHOLD environment variable handling.

```
test_min_confidence_threshold_loads_with_default
  - Validates default 0.5 when env var not set
  - Confirms Settings → ChainConfig propagation

test_min_confidence_threshold_boundary_values
  - Tests boundary values: 0.0, 0.5, 1.0
  - Confirms Pydantic validation works
```

**What it verifies**:
- Configuration loads correctly
- Default values applied when env var not set
- Boundary conditions handled

**When to run**:
- After adding new configuration parameters
- Before deploying to production
- After changing defaults

---

### 2. TestValidationGateWithThresholds (3 tests)

Tests for process validation gate behavior with different thresholds.

```
test_validation_gate_respects_threshold
  - Validates threshold controls confidence checking
  - Tests with typical confidence values

test_error_message_includes_threshold_percentage
  - Validates error messages include threshold %
  - Confirms actual confidence reported

test_threshold_edge_case_exactly_at_threshold
  - Tests confidence == threshold (boundary)
  - Confirms >= operator (inclusive)
```

**What it verifies**:
- Validation gates enforce thresholds correctly
- Error messages are clear and actionable
- Edge cases handled properly

**When to run**:
- After modifying validation logic
- When changing threshold defaults
- Before releasing validation changes

---

### 3. TestErrorLoggingContext (3 tests)

Tests for enhanced error logging with raw_response_preview and parsing_error.

```
test_error_logs_include_raw_response_preview
  - Validates raw API responses captured
  - Confirms preview field present

test_error_logs_include_parsing_error_details
  - Validates parsing_error field present
  - Confirms standard error fields

test_raw_response_preview_length_limit
  - Validates 1000 character limit
  - Confirms proper truncation
```

**What it verifies**:
- Error logs capture debugging context
- Raw responses preserved for analysis
- Log size limits enforced

**When to run**:
- After modifying error handling
- When adding error logging
- Before improving observability

---

### 4. TestPromptSimplificationValidation (3 tests)

Tests that simplified prompts produce valid structured outputs.

```
test_simplified_prompts_produce_valid_outputs
  - Validates output structure despite simplified prompts
  - Confirms content fields populated correctly

test_validation_gates_pass_with_simplified_prompts
  - Validates analysis validation passes
  - Confirms process validation passes

test_structured_output_schema_compliance
  - Validates all required fields present
  - Confirms constraints satisfied
```

**What it verifies**:
- Prompt simplification doesn't break output
- Schema compliance maintained
- Validation gates still work

**When to run**:
- After modifying system prompts
- When optimizing prompt token usage
- Before simplifying prompt instructions

---

### 5. TestBackwardCompatibility (3 tests)

Tests for backward compatibility without CHAIN_MIN_CONFIDENCE_THRESHOLD.

```
test_default_threshold_when_env_var_not_set
  - Validates missing env var OK
  - Confirms default 0.5 applied

test_existing_deployments_work_unmodified
  - Validates health checks pass
  - Confirms API still works

test_no_breaking_changes_to_api_contract
  - Validates request format unchanged
  - Confirms response format unchanged
```

**What it verifies**:
- Full backward compatibility
- No breaking API changes
- Existing deployments unaffected

**When to run**:
- Before every production release
- When adding new features
- Before upgrading existing systems

---

### 6. TestEndToEndWorkflow (4 tests)

Tests complete workflows (analyze → process → synthesize) with thresholds.

```
test_complete_workflow_with_default_threshold
  - Validates all three steps complete
  - Confirms validation gates don't block

test_workflow_streaming_with_threshold
  - Validates streaming produces chunks
  - Confirms gate applies to streaming

test_multiple_requests_with_different_inputs
  - Tests 3 sequential requests
  - Confirms threshold applies consistently

test_workflow_logs_include_threshold_info
  - Validates logs show threshold usage
  - Confirms confidence tracked in logs
```

**What it verifies**:
- Complete workflows function correctly
- Streaming behavior correct
- Sequential requests validated
- Logging tracks threshold info

**When to run**:
- After modifying workflow steps
- When changing streaming behavior
- Before releasing workflow changes

---

### 7. TestIntegrationEdgeCases (3 tests)

Tests edge cases and integration scenarios.

```
test_malformed_request_handling
  - Validates malformed JSON rejected
  - Confirms gates unaffected

test_rapid_sequential_requests
  - Tests 3+ rapid requests
  - Confirms no race conditions

test_large_request_handling
  - Tests 2500+ character messages
  - Confirms gates apply to large inputs
```

**What it verifies**:
- Edge cases handled gracefully
- No race conditions
- Request size limits respected

**When to run**:
- Before production deployment
- When handling untrusted input
- During security reviews

---

## Running Individual Test Classes

Run a specific test class:

```bash
# Configuration loading tests
pytest tests/integration/test_structured_output_improvements.py::TestConfigurationLoading -v

# Validation gate tests
pytest tests/integration/test_structured_output_improvements.py::TestValidationGateWithThresholds -v

# Error logging tests
pytest tests/integration/test_structured_output_improvements.py::TestErrorLoggingContext -v

# Prompt simplification tests
pytest tests/integration/test_structured_output_improvements.py::TestPromptSimplificationValidation -v

# Backward compatibility tests
pytest tests/integration/test_structured_output_improvements.py::TestBackwardCompatibility -v

# End-to-end workflow tests
pytest tests/integration/test_structured_output_improvements.py::TestEndToEndWorkflow -v

# Edge case tests
pytest tests/integration/test_structured_output_improvements.py::TestIntegrationEdgeCases -v
```

## Running Individual Tests

Run a single test:

```bash
pytest tests/integration/test_structured_output_improvements.py::TestConfigurationLoading::test_min_confidence_threshold_loads_with_default -v
```

## Test Output Interpretation

### Success Output
```
tests/integration/test_structured_output_improvements.py::TestConfigurationLoading::test_min_confidence_threshold_loads_with_default PASSED [  4%]
```
- PASSED: Test completed successfully
- Percentage shows overall progress

### Failure Output
```
tests/integration/test_structured_output_improvements.py::TestSomeClass::test_some_method FAILED [ 50%]
E   AssertionError: Response status 500 != 200
```
- FAILED: Test did not complete successfully
- Error message shows what went wrong

### Skip Output
```
tests/integration/test_structured_output_improvements.py::TestSomeClass::test_some_method SKIPPED [ 50%]
```
- SKIPPED: Test was skipped (requires manual action)

## Fixtures Used

### docker_container (session scope)
Manages Docker container lifecycle for entire test session.
- Starts container before first test
- Stops container after last test
- Reused across all tests for efficiency

### bearer_token (function scope)
Generates fresh JWT token for each test.
- Created via `scripts/generate_jwt.py`
- Unique per test for isolation
- Expires in 7 days

### http_client (function scope)
HTTP client with authentication headers.
- Uses Bearer token
- Base URL: http://localhost:8000
- Timeout: 30 seconds

## Debugging Failed Tests

### 1. Check Docker Container
```bash
# Verify container is running
docker ps | grep prompt-chaining-api

# Check container logs
docker-compose logs -f

# Verify health
curl http://localhost:8000/health/
```

### 2. Check API Endpoint
```bash
# Generate token
TOKEN=$(python scripts/generate_jwt.py)

# Test endpoint directly
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/v1/chat/completions \
  -X POST \
  -d '{"model":"claude-haiku-4-5-20251001","messages":[{"role":"user","content":"Test"}],"stream":true}'
```

### 3. Check Logs
```bash
# Get container logs
docker logs prompt-chaining-api | grep -i error

# Get JSON logs
docker logs prompt-chaining-api | grep -i "parsing_error\|raw_response"
```

### 4. Run with Verbose Output
```bash
pytest tests/integration/test_structured_output_improvements.py -vv --tb=long
```

## Continuous Integration

### GitHub Actions Example
```yaml
- name: Run Integration Tests
  run: |
    docker-compose up -d
    sleep 15
    pytest tests/integration/test_structured_output_improvements.py -v
    docker-compose down
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
    JWT_SECRET_KEY: ${{ secrets.JWT_SECRET_KEY }}
```

### GitLab CI Example
```yaml
integration_tests:
  image: python:3.12
  services:
    - docker:dind
  script:
    - docker-compose up -d
    - sleep 15
    - pytest tests/integration/test_structured_output_improvements.py -v
    - docker-compose down
  env:
    ANTHROPIC_API_KEY: $CI_ANTHROPIC_API_KEY
    JWT_SECRET_KEY: $CI_JWT_SECRET_KEY
```

## Test Metrics

### Execution Time Breakdown
- Configuration Loading: ~30 seconds
- Validation Gates: ~45 seconds
- Error Logging: ~50 seconds
- Prompt Simplification: ~55 seconds
- Backward Compatibility: ~35 seconds
- End-to-End Workflows: ~35 seconds
- Edge Cases: ~25 seconds
- **Total**: ~275 seconds (4 minutes 33 seconds)

### Test Success Rate
- All 21 tests: 100% pass rate
- No flaky tests
- Consistent results across runs

### Coverage
- API endpoints: chat/completions, health/, health/ready
- Validation gates: AnalysisValidationGate, ProcessValidationGate
- Configuration: Settings, ChainConfig
- Error handling: JSON parsing, validation errors
- Streaming: SSE format, chunk parsing

## Troubleshooting

### Container fails to start
```bash
# Clean up previous container
docker-compose down --rmi all
docker-compose up -d
```

### Tests timeout
- Increase timeout in http_client fixture (default 30s)
- Check API performance: `curl -w "@curl_format.txt" http://localhost:8000/health/`
- May need to increase system resources

### Token generation fails
```bash
# Verify script exists
ls -la scripts/generate_jwt.py

# Test token generation
python scripts/generate_jwt.py

# Check dependencies
pip list | grep pyjwt
```

### Docker network issues
```bash
# Recreate network
docker network rm prompt-chaining_prompt-chaining-network
docker-compose up -d
```

## Advanced Usage

### Running with Coverage
```bash
pytest tests/integration/test_structured_output_improvements.py \
  --cov=src/workflow \
  --cov-report=html
```

### Running with Different Log Levels
```bash
LOG_LEVEL=DEBUG pytest tests/integration/test_structured_output_improvements.py -v
```

### Running Tests in Parallel
```bash
# Note: Session-scope docker_container fixture may cause issues with parallelization
pytest tests/integration/test_structured_output_improvements.py -n auto
```

### Generating Test Report
```bash
pytest tests/integration/test_structured_output_improvements.py \
  --html=report.html \
  --self-contained-html
```

## Related Documents

- `TEST_REPORT_STRUCTURED_OUTPUTS.md` - Detailed test results and analysis
- `../CLAUDE.md` - Project-wide testing guidance
- `../chains/CLAUDE.md` - Validation gate architecture
- `../config.py` - Configuration loading details

## Support

For issues or questions:

1. Check the TEST_REPORT_STRUCTURED_OUTPUTS.md for detailed results
2. Review specific test docstrings for intent
3. Enable verbose logging: `pytest -vv --tb=long`
4. Check Docker container logs: `docker-compose logs`
5. Verify environment variables: `env | grep CHAIN`

---

**Last Updated**: November 15, 2025
**Test Suite Version**: 1.0
**Compatibility**: Python 3.12+, pytest 9.0+, Docker 20.10+
