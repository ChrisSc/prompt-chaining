## What

<!-- Brief description of the changes in this PR -->

## Why

<!-- Problem being solved or motivation for this feature -->

## How

<!-- Technical approach and key implementation details -->

## Type of Change

<!-- Mark the relevant option with an [x] -->

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Code quality improvement (refactoring, optimization, etc.)
- [ ] Test coverage improvement

## Testing

<!-- Describe the tests you ran and how to reproduce them -->

### Test Checklist

- [ ] All tests pass locally (`./scripts/test.sh`)
- [ ] Added new tests for new functionality
- [ ] Manually tested with `./scripts/dev.sh`
- [ ] Coverage remains >80% (or improved)
- [ ] Tested with different Python versions (if applicable)

### Manual Testing Steps

<!-- If applicable, describe how to manually test this change -->

1.
2.
3.

## Code Quality

- [ ] Code follows style guidelines (`./scripts/format.sh` passes)
- [ ] No mypy type checking errors
- [ ] All functions have type hints
- [ ] Added/updated docstrings for public APIs
- [ ] Code is DRY (Don't Repeat Yourself)

## Documentation

- [ ] Updated CLAUDE.md (if workflow/architecture changed)
- [ ] Updated README.md (if user-facing features changed)
- [ ] Updated CONTRIBUTING.md (if development process changed)
- [ ] Updated JWT_AUTHENTICATION.md (if auth changed)
- [ ] Added/updated code comments for complex logic
- [ ] Updated API documentation (if endpoints changed)

## Breaking Changes

<!-- If this PR introduces breaking changes, describe them here -->

**Does this PR introduce breaking changes?** No / Yes

<!-- If yes, complete the following: -->

### What breaks?

<!-- Describe what will break for existing users -->

### Migration Path

<!-- Explain how users can migrate their code -->

### Deprecation Notice

<!-- If applicable, describe the deprecation timeline -->

## Template vs. Customization

<!-- Mark the relevant option with an [x] -->

- [ ] This is a **template improvement** (generic, benefits all use cases)
- [ ] This is **domain-specific** (should this be in a fork instead?)

<!-- If domain-specific, please explain why this should be in the template -->

## Additional Context

<!-- Add any other context, screenshots, or related issues -->

### Related Issues

<!-- Link to related issues using # -->

Closes #
Related to #

### Screenshots (if applicable)

<!-- Add screenshots for UI changes or visual improvements -->

### Dependencies

<!-- List any new dependencies added and why they're needed -->

### Performance Impact

<!-- Describe any performance implications -->

### Cost Impact

<!-- Describe any token usage or cost implications -->

---

## Contributor Checklist

Before requesting a review, please confirm:

- [ ] I have read [CONTRIBUTING.md](https://github.com/ChrisSc/prompt-chaining/blob/main/CONTRIBUTING.md)
- [ ] I have followed the [critical development rules](https://github.com/ChrisSc/prompt-chaining/blob/main/CONTRIBUTING.md#critical-development-rules)
- [ ] My code uses relative imports (`workflow.*`, not `src.workflow.*`)
- [ ] My code uses async/await for all I/O operations
- [ ] I have tested with `fastapi dev`, not `uvicorn` directly
- [ ] I have added tests that prove my fix is effective or that my feature works
- [ ] New and existing tests pass locally with my changes
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] My changes generate no new warnings or errors
- [ ] I have checked my code for security implications
- [ ] This PR is focused on a single concern (not multiple unrelated changes)

---

## Prompt-Chaining Specific

- [ ] System prompts output valid JSON matching Pydantic models (AnalysisOutput, ProcessOutput, SynthesisOutput)
- [ ] Validation gates tested for both pass and fail paths
- [ ] Chain step configuration verified (model, tokens, temperature, timeout)
- [ ] Streaming synthesis tested if response involves streaming
- [ ] Per-step token tracking and cost calculation verified
- [ ] Error messages use step-based terminology (analyze/process/synthesize, not "phase")

---

## Reviewer Notes

<!-- For reviewers: Add any notes, concerns, or areas to focus on during review -->
