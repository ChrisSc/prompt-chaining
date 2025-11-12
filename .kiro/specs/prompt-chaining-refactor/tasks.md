# Implementation Plan

## Documentation References

This implementation uses curated documentation to break dependency on pre-training:

- **FastAPI Documentation**: `./documentation/fastapi/INDEX_AGENT.md`
- **LangChain Documentation**: `./documentation/langchain/INDEX.md`
- **Pydantic Documentation**: `./documentation/pydantic/LLM_INDEX.md`

Refer to these documents for implementation details, patterns, and examples.

---

- [x] 1. Add LangChain and LangGraph dependencies
  - Add `langchain`, `langchain-anthropic`, and `langgraph` to `pyproject.toml` dependencies
  - Update dependency versions to latest stable releases
  - Run `pip install -e ".[dev]"` to verify installation
  - _Requirements: 1.1, 1.3_
  - _Documentation: See `./documentation/langchain/INDEX.md` for LangChain installation guide at `oss/python/langchain/install.md`_

- [x] 2. Create chain state and data models
  - [x] 2.1 Create `src/workflow/models/chains.py` with ChainState TypedDict
    - Define ChainState with messages, analysis, processed_content, final_response, step_metadata fields
    - Use LangGraph's `add_messages` annotation for message accumulation
    - _Requirements: 1.1, 3.4_
    - _Documentation: See `./documentation/langchain/INDEX.md` → LangGraph section → `oss/python/langgraph/overview.md` for StateGraph patterns_
  - [x] 2.2 Create Pydantic models for step outputs in `models/chains.py`
    - Implement AnalysisOutput model with intent, key_entities, complexity, context fields
    - Implement ProcessOutput model with content, confidence, metadata fields
    - Implement SynthesisOutput model with final_text, formatting fields
    - _Requirements: 2.4, 5.3_
    - _Documentation: See `./documentation/pydantic/LLM_INDEX.md` → CORE section → `models/index.md` for BaseModel fundamentals and `fields/index.md` for Field definition_
  - [x] 2.3 Create ChainStepConfig and ChainConfig models in `models/chains.py`
    - Define ChainStepConfig with model, max_tokens, temperature, system_prompt_file
    - Define ChainConfig with analyze, process, synthesize step configs and timeout settings
    - _Requirements: 5.2, 5.4_
    - _Documentation: See `./documentation/pydantic/LLM_INDEX.md` → CORE section → `models/index.md` for model composition and nested models_

- [ ] 3. Create system prompts for chain steps
  - [ ] 3.1 Create `src/workflow/prompts/chain_analyze.md`
    - Write prompt instructing LLM to analyze user request and extract intent, entities, complexity
    - Include examples of expected JSON output format
    - _Requirements: 2.1, 5.1_
  - [ ] 3.2 Create `src/workflow/prompts/chain_process.md`
    - Write prompt instructing LLM to generate response based on analysis
    - Include guidance on using analysis context effectively
    - _Requirements: 2.2, 5.1_
  - [ ] 3.3 Create `src/workflow/prompts/chain_synthesize.md`
    - Write prompt instructing LLM to format and polish final response
    - Include formatting guidelines and tone instructions
    - _Requirements: 2.3, 5.1_

- [ ] 4. Implement validation gates
  - [ ] 4.1 Create `src/workflow/chains/validation.py` with ValidationGate base class
    - Implement base ValidationGate class with schema validation using Pydantic
    - Add validate() method returning (is_valid, error_message) tuple
    - _Requirements: 2.4, 5.3_
  - [ ] 4.2 Implement AnalysisValidationGate in `chains/validation.py`
    - Validate AnalysisOutput schema
    - Add business logic validation for required fields (intent must be present)
    - _Requirements: 2.4, 5.5_
  - [ ] 4.3 Implement ProcessValidationGate in `chains/validation.py`
    - Validate ProcessOutput schema
    - Add business logic validation for content length and confidence thresholds
    - _Requirements: 2.4, 5.5_
  - [ ] 4.4 Create conditional edge functions for LangGraph
    - Implement should_proceed_to_process() function using AnalysisValidationGate
    - Implement should_proceed_to_synthesize() function using ProcessValidationGate
    - Return "next_step" or "error" based on validation results
    - _Requirements: 2.5, 3.5_

- [ ] 5. Implement chain step functions
  - [ ] 5.1 Create `src/workflow/chains/steps.py` with analyze_step function
    - Extract user message from ChainState.messages
    - Initialize ChatAnthropic with Haiku model and load chain_analyze.md prompt
    - Call LLM with system prompt and user message
    - Parse response into AnalysisOutput structure
    - Log step metrics (tokens, cost, duration)
    - Return state update with analysis and messages
    - _Requirements: 2.1, 3.1, 3.3, 4.5_
    - _Documentation: See `./documentation/langchain/INDEX.md` → `oss/python/langchain/models.md` for ChatAnthropic usage and `oss/python/integrations/providers/anthropic.md` for Anthropic integration_
  - [ ] 5.2 Implement process_step function in `chains/steps.py`
    - Extract analysis from ChainState.analysis
    - Build processing prompt from analysis context
    - Initialize ChatAnthropic with Sonnet model and load chain_process.md prompt
    - Call LLM with system prompt and constructed prompt
    - Log step metrics (tokens, cost, duration)
    - Return state update with processed_content and messages
    - _Requirements: 2.2, 3.1, 3.3, 4.5_
    - _Documentation: See `./documentation/langchain/INDEX.md` → `oss/python/langchain/models.md` for model configuration_
  - [ ] 5.3 Implement synthesize_step async generator function in `chains/steps.py`
    - Extract processed_content from ChainState.processed_content
    - Build synthesis prompt from processed content
    - Initialize ChatAnthropic with Haiku model, streaming=True, and load chain_synthesize.md prompt
    - Stream LLM response using astream() method
    - Yield state updates with message chunks and accumulated final_response
    - Log step metrics after streaming completes
    - _Requirements: 2.3, 3.1, 3.3, 4.5_
    - _Documentation: See `./documentation/langchain/INDEX.md` → `oss/python/langchain/streaming.md` for streaming patterns with LangChain_

- [ ] 6. Implement LangGraph StateGraph orchestration
  - [ ] 6.1 Create `src/workflow/chains/graph.py` with StateGraph initialization
    - Initialize StateGraph with ChainState
    - Add nodes for analyze_step, process_step, synthesize_step
    - Add conditional edges from analyze to process and process to synthesize
    - Compile graph with checkpointer for memory
    - _Requirements: 3.1, 3.2_
    - _Documentation: See `./documentation/langchain/INDEX.md` → LangGraph section → `oss/python/langgraph/how-tos/` for graph construction patterns_
  - [ ] 6.2 Create graph streaming and invocation methods
    - Implement async method to invoke graph with initial input
    - Implement async generator to stream graph output with astream()
    - Handle state updates and message accumulation
    - _Requirements: 3.1, 4.5_
  - [ ] 6.3 Integrate graph with FastAPI chat endpoint
    - Update `/v1/chat/completions` endpoint to use chain_graph instead of orchestrator
    - Convert ChainState messages to OpenAI ChatCompletionChunk format
    - Stream final_response through SSE
    - _Requirements: 4.1, 4.2_
    - _Documentation: See `./documentation/fastapi/INDEX_AGENT.md` for streaming response patterns_

- [ ] 7. Create integration tests for chain
  - [ ] 7.1 Create `tests/integration/test_chain_full.py`
    - Test full chain execution with mocked LLM responses
    - Verify state transitions and message accumulation
    - Test error paths and validation gate failures
    - _Requirements: 4.4, 4.5_
  - [ ] 7.2 Create live endpoint test for streaming
    - Test `/v1/chat/completions` streaming with actual LLM
    - Verify token usage and cost logging
    - Verify timeout enforcement
    - _Requirements: 4.3, 4.4, 4.5_

- [ ] 8. Update configuration for chain parameters
  - [ ] 8.1 Add ChainConfig to Settings in `config.py`
    - Create default ChainConfig with standard values
    - Allow override via environment variables
    - _Requirements: 5.2, 5.4_
  - [ ] 8.2 Update CLAUDE.md and README.md
    - Document chain configuration options
    - Add examples of customizing chain behavior
    - _Requirements: 5.1, 5.6_

- [ ] 9. Performance optimization and monitoring
  - [ ] 9.1 Add timing and metrics collection
    - Log duration of each chain step
    - Track total tokens and cost per request
    - Monitor memory usage with checkpointer
    - _Requirements: 4.4_
  - [ ] 9.2 Create performance benchmarks
    - Benchmark different model combinations
    - Document cost/latency tradeoffs
    - _Requirements: 4.1_

- [ ] 10. Final documentation and cleanup
  - [ ] 10.1 Update ARCHITECTURE.md
    - Document LangGraph orchestration pattern
    - Add diagrams of chain flow
    - _Requirements: 5.1, 5.6_
  - [ ] 10.2 Create PROMPT_CHAINING.md
    - Comprehensive guide to understanding and customizing chain
    - Examples and troubleshooting
    - _Requirements: 5.1, 5.6_
  - [ ] 10.3 Clean up old orchestrator-worker code (if not needed)
    - Remove or archive agents/orchestrator.py, agents/worker.py, agents/synthesizer.py
    - Update tests accordingly
    - _Requirements: 5.2, 5.3_

---

## Notes

- All tasks reference specific requirement IDs for traceability
- Documentation references point to curated docs in `./documentation/`
- Each subtask is atomic and can be reviewed independently
- Mark tasks complete as they're merged
