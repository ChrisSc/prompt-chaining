# Prompt-Chaining: Pattern Guide & Configuration

This guide explains the prompt-chaining pattern and how to configure it for your specific use case.

## What is Prompt-Chaining?

Prompt-chaining is a sequential multi-step AI reasoning pattern where complex tasks are broken into focused steps:

1. **Analyze**: Parse user intent, extract entities, assess complexity
2. **Process**: Generate content based on analysis results
3. **Synthesize**: Polish and format the final response

Each step can use different models, token limits, and configurations. This enables:
- **Better reasoning**: Focused steps handle specific tasks more effectively
- **Quality control**: Validation gates between steps prevent bad data cascading
- **Cost optimization**: Use fast/cheap models for simple steps, upgrade when needed
- **Observability**: See exactly what each step produces and costs

### When to Use

**Ideal for**:
- Tasks requiring multiple sequential reasoning steps
- Use cases needing structured outputs for downstream processing
- Workflows where steps have different concerns (analysis vs. generation vs. synthesis)
- Scenarios where quality and observability matter

**Not ideal for**:
- Parallel independent tasks (use orchestrator-worker pattern instead)
- Simple single-turn requests (use direct API calls)
- Real-time bidirectional conversations (use streaming chat)

## The Three-Step Workflow

### Step 1: Analyze (Intent Extraction)

Parses user requests to extract structured information for downstream processing.

**Responsibilities**:
- Extract user intent (what they want to accomplish)
- Identify key entities, topics, and concepts
- Assess task complexity (simple, moderate, complex)
- Gather contextual information

**Configuration** (from `ChainConfig.analyze`):
- Model: Default `claude-haiku-4-5-20251001`
- Max tokens: Default 1000
- Temperature: Default 0.5 (deterministic intent extraction)
- Timeout: Default 15 seconds
- System prompt: `src/workflow/prompts/chain_analyze.md`

**Output** (`AnalysisOutput`):
```json
{
  "intent": "User's primary goal",
  "key_entities": ["entity1", "entity2"],
  "complexity": "simple|moderate|complex",
  "context": {"additional": "contextual information"}
}
```

**Typical Performance**: 1-2 seconds, 300-400 input tokens, 150-250 output tokens, ~$0.001 cost

### Step 2: Process (Content Generation)

Generates substantive content based on analysis output with confidence scoring.

**Responsibilities**:
- Receive analysis output as context
- Generate domain-specific content addressing identified intent
- Score confidence in generated content (0.0-1.0)
- Capture metadata for traceability

**Configuration** (from `ChainConfig.process`):
- Model: Default `claude-haiku-4-5-20251001`
- Max tokens: Default 2000
- Temperature: Default 0.7 (balanced, creative responses)
- Timeout: Default 30 seconds
- System prompt: `src/workflow/prompts/chain_process.md`

**Output** (`ProcessOutput`):
```json
{
  "content": "Generated content addressing the intent",
  "confidence": 0.85,
  "metadata": {"generation_approach": "value", "coverage": "detail"}
}
```

**Validation Gate**: Content must be non-empty AND confidence >= 0.5

**Typical Performance**: 2-4 seconds, 400-600 input tokens, 400-600 output tokens, ~$0.003 cost

### Step 3: Synthesize (Polish & Format)

Polishes and formats the final response for user delivery. This is the only streaming step.

**Responsibilities**:
- Receive processed content as context
- Apply formatting and styling for presentation
- Stream response token-by-token in real-time
- Ensure professional, user-ready output

**Configuration** (from `ChainConfig.synthesize`):
- Model: Default `claude-haiku-4-5-20251001`
- Max tokens: Default 2000
- Temperature: Default 0.5 (consistent formatting)
- Timeout: Default 20 seconds
- System prompt: `src/workflow/prompts/chain_synthesize.md`

**Output** (streamed to client):
```markdown
# Formatted Response

Polished and styled content for user consumption...
```

**Typical Performance**: 1-2 seconds, 500-800 input tokens, 400-600 output tokens, ~$0.002 cost

### End-to-End Data Flow

```
User Request
    ↓
[Analyze] Extract intent & entities
    ↓
[Validation Gate 1: Intent required?]
    ├─ PASS → [Process] Generate content
    └─ FAIL → [Error Handler]
    ↓
[Validation Gate 2: Confidence >= 0.5?]
    ├─ PASS → [Synthesize] Polish & stream
    └─ FAIL → [Error Handler]
    ↓
Stream response to client
```

## Configuration Guide

### Quick Start: Three Templates

**Fast & Cost-Optimized** (recommended starting point):
```env
# All-Haiku: cheapest option
CHAIN_ANALYZE_MODEL=claude-haiku-4-5-20251001
CHAIN_ANALYZE_MAX_TOKENS=1000
CHAIN_ANALYZE_TEMPERATURE=0.3

CHAIN_PROCESS_MODEL=claude-haiku-4-5-20251001
CHAIN_PROCESS_MAX_TOKENS=2000
CHAIN_PROCESS_TEMPERATURE=0.7

CHAIN_SYNTHESIZE_MODEL=claude-haiku-4-5-20251001
CHAIN_SYNTHESIZE_MAX_TOKENS=1000
CHAIN_SYNTHESIZE_TEMPERATURE=0.5

CHAIN_ANALYZE_TIMEOUT=15
CHAIN_PROCESS_TIMEOUT=30
CHAIN_SYNTHESIZE_TIMEOUT=20
```
**Cost**: ~$0.006-0.008/request | **Speed**: 4-8 seconds

**Balanced Quality** (best for most use cases):
```env
# Haiku for analysis (fast intent parsing)
CHAIN_ANALYZE_MODEL=claude-haiku-4-5-20251001
CHAIN_ANALYZE_MAX_TOKENS=1000
CHAIN_ANALYZE_TEMPERATURE=0.3

# Sonnet for processing (quality where it matters)
CHAIN_PROCESS_MODEL=claude-sonnet-4-5-20250929
CHAIN_PROCESS_MAX_TOKENS=2500
CHAIN_PROCESS_TEMPERATURE=0.7

# Haiku for synthesis (efficient formatting)
CHAIN_SYNTHESIZE_MODEL=claude-haiku-4-5-20251001
CHAIN_SYNTHESIZE_MAX_TOKENS=1000
CHAIN_SYNTHESIZE_TEMPERATURE=0.5

CHAIN_ANALYZE_TIMEOUT=15
CHAIN_PROCESS_TIMEOUT=45
CHAIN_SYNTHESIZE_TIMEOUT=20
```
**Cost**: ~$0.010-0.012/request | **Speed**: 5-10 seconds

**High Accuracy** (quality-critical applications):
```env
# All-Sonnet: best quality
CHAIN_ANALYZE_MODEL=claude-sonnet-4-5-20250929
CHAIN_ANALYZE_MAX_TOKENS=1500
CHAIN_ANALYZE_TEMPERATURE=0.5

CHAIN_PROCESS_MODEL=claude-sonnet-4-5-20250929
CHAIN_PROCESS_MAX_TOKENS=3000
CHAIN_PROCESS_TEMPERATURE=0.7

CHAIN_SYNTHESIZE_MODEL=claude-sonnet-4-5-20250929
CHAIN_SYNTHESIZE_MAX_TOKENS=1500
CHAIN_SYNTHESIZE_TEMPERATURE=0.5

CHAIN_ANALYZE_TIMEOUT=30
CHAIN_PROCESS_TIMEOUT=60
CHAIN_SYNTHESIZE_TIMEOUT=30
```
**Cost**: ~$0.016-0.020/request | **Speed**: 8-15 seconds

### Per-Step Tuning

**Temperature** controls randomness:

| Step | Value | Use Case |
|------|-------|----------|
| Analyze | 0.0-0.3 | Consistent, deterministic intent extraction |
| Analyze | 0.5 (default) | Balanced extraction |
| Analyze | 0.7-1.0 | Creative entity interpretation |
| Process | 0.5 | Factual, consistent content |
| Process | 0.7 (default) | Balanced, diverse responses |
| Process | 0.9+ | Creative, experimental content |
| Synthesize | 0.3-0.5 | Consistent formatting |
| Synthesize | 0.5-0.7 | Balanced formatting |

**Token Limits** (adjust based on expected response complexity):

| Step | Default | Concise | Detailed |
|------|---------|---------|----------|
| Analyze | 2048 | 500-1000 | 1500-2048 |
| Process | 2048 | 1000-1500 | 2048-4000+ |
| Synthesize | 2048 | 500-1000 | 1500-2048 |

**Timeout Tuning** (prevent runaway requests):

| Step | Default | Latency-Critical | Complex Tasks |
|------|---------|------------------|----------------|
| Analyze | 15s | 10s | 30s |
| Process | 30s | 15s | 60s |
| Synthesize | 20s | 10s | 30s |

### Model Selection Decision Tree

```
Does your task primarily extract/parse information?
├─ YES: Use all-Haiku config
│
└─ NO: Does content generation require complex reasoning?
   ├─ YES (high stakes, accuracy critical):
   │   └─ Use Haiku analyze + Sonnet process + Haiku synthesize
   │
   └─ NO (general purpose):
       ├─ Start with all-Haiku
       ├─ If quality issues:
       │   ├─ First: Increase process temperature (0.7 → 0.9)
       │   ├─ Second: Increase process tokens (2000 → 3000)
       │   ├─ Third: Upgrade process to Sonnet
       │   └─ Last: Upgrade other steps if needed
```

### Cost Optimization Tips

1. **Start cheap**: Begin with all-Haiku, monitor actual costs
2. **Upgrade strategically**: Process step has biggest quality impact per dollar
3. **Monitor token usage**: `grep "total_cost_usd" logs.json | jq '.total_cost_usd'`
4. **Reduce limits if needed**: Check actual token consumption, adjust max_tokens down
5. **Tune temperature**: Lower temperature (0.3-0.5) = shorter, more consistent responses

## Validation Gates for Quality Control

Validation gates enforce data quality between steps and prevent bad data from cascading.

### How Validation Works

**Gate 1: After Analysis**
- Validates: `AnalysisOutput` schema compliance
- Business rule: `intent` field must be present and non-empty (after stripping whitespace)
- Routes: Valid → Process step | Invalid → Error handler
- Prevents: Empty intent from corrupting processing step

**Gate 2: After Processing**
- Validates: `ProcessOutput` schema compliance
- Business rules:
  - `content` field must be non-empty
  - `confidence` must be >= 0.5 (minimum quality threshold)
- Routes: Valid → Synthesize step | Invalid → Error handler
- Prevents: Low-confidence or incomplete content from being synthesized

### Configuration

**Enable/Disable Validation**:
```env
CHAIN_ENABLE_VALIDATION=true   # Enable quality gates (default)
CHAIN_STRICT_VALIDATION=false  # Warn on errors (vs. fail)
```

**Modes**:
- **Strict Mode** (`strict_validation=true`): Fail immediately on validation error, return error to client
- **Lenient Mode** (`strict_validation=false`): Log warning, attempt to handle gracefully

### Debugging Validation Failures

**Common Issue: Empty Intent**
```
Error: "intent field is required and must be non-empty"
→ Review chain_analyze.md prompt
→ Increase analyze temperature (0.3 → 0.5-0.7)
→ Increase analyze max_tokens (1000 → 1500)
```

**Common Issue: Low Confidence**
```
Error: "confidence score 0.3 does not meet minimum threshold of 0.5"
→ Increase process temperature (0.7 → 0.9)
→ Increase process tokens (2000 → 3000)
→ Upgrade process model to Sonnet
```

**Debugging Steps**:
1. Check logs for exact validation error message
2. Note which step failed (analyze vs. process)
3. Review the output that failed validation
4. Adjust configuration per recommendations above
5. Monitor logs again: `grep "validation" logs.json`

## Cost & Performance

### Typical Execution Times & Costs (Haiku models)

```
All-Haiku Configuration:
  Analyze:    1-2s,  85 input + 156 output tokens,  $0.00097
  Process:    2-4s,  287 input + 412 output tokens, $0.00352
  Synthesize: 1-2s,  521 input + 387 output tokens, $0.00270
  ─────────────────────────────────────────────────
  Total:      4-8s,  893 input + 955 output tokens, $0.00719

Balanced Quality (Haiku + Sonnet + Haiku):
  Analyze:    1-2s,  85 input + 156 output tokens (Haiku),   $0.00097
  Process:    3-5s,  287 input + 412 output tokens (Sonnet),  $0.00859
  Synthesize: 1-2s,  521 input + 387 output tokens (Haiku),   $0.00270
  ─────────────────────────────────────────────────
  Total:      5-9s,  893 input + 955 output tokens,           $0.01226

All-Sonnet Configuration:
  Analyze:    1-2s,  85 input + 156 output tokens,  $0.00293
  Process:    3-5s,  287 input + 412 output tokens, $0.00859
  Synthesize: 1-2s,  521 input + 387 output tokens, $0.00811
  ─────────────────────────────────────────────────
  Total:      5-9s,  893 input + 955 output tokens, $0.01963
```

### Cost Optimization Strategies

**Pattern 1: Volume Services** (maximize throughput, minimize cost)
- Use all-Haiku
- Reduce token limits for brevity
- Lower temperature for determinism
- Cost: ~$0.006-0.008/request

**Pattern 2: Balanced** (optimize quality/cost ratio)
- Use Haiku for analysis and synthesis
- Upgrade to Sonnet for processing (biggest quality impact)
- Default timeouts
- Cost: ~$0.010-0.012/request

**Pattern 3: Quality-Critical** (maximize accuracy)
- Use Sonnet for all steps
- Higher token limits for detailed responses
- Balanced temperature
- Cost: ~$0.015-0.025/request

### Performance Monitoring

**View cost per request**:
```bash
grep "total_cost_usd" logs.json | jq '.total_cost_usd' | sort -n
```

**Analyze per-step costs**:
```bash
grep "step_breakdown" logs.json | jq '.step_breakdown'
```

**Monitor latency**:
```bash
grep "total_elapsed_seconds" logs.json | jq '.total_elapsed_seconds'
```

**Find expensive outliers**:
```bash
grep "total_cost_usd" logs.json | jq 'select(.total_cost_usd > 0.05)'
```

## Common Configuration Recipes

### Customer Support (Fast, Accurate Routing)

**Goal**: Route customer queries to appropriate teams quickly with high accuracy

```env
# Fast analysis for intent extraction
CHAIN_ANALYZE_MODEL=claude-haiku-4-5-20251001
CHAIN_ANALYZE_MAX_TOKENS=1000
CHAIN_ANALYZE_TEMPERATURE=0.3
CHAIN_ANALYZE_TIMEOUT=10

# Quality analysis for routing recommendation (upgrade to Sonnet)
CHAIN_PROCESS_MODEL=claude-sonnet-4-5-20250929
CHAIN_PROCESS_MAX_TOKENS=1500
CHAIN_PROCESS_TEMPERATURE=0.5
CHAIN_PROCESS_TIMEOUT=20

# Quick formatting
CHAIN_SYNTHESIZE_MODEL=claude-haiku-4-5-20251001
CHAIN_SYNTHESIZE_MAX_TOKENS=500
CHAIN_SYNTHESIZE_TEMPERATURE=0.3
CHAIN_SYNTHESIZE_TIMEOUT=10

# Strict validation (fail on low confidence routing)
CHAIN_ENABLE_VALIDATION=true
CHAIN_STRICT_VALIDATION=true
```

**Typical**: 1-3 requests/second, $0.008-0.012/request

### Content Generation (Blog Posts, Articles)

**Goal**: Generate high-quality written content with good structure

```env
# Deep analysis of topic/requirements
CHAIN_ANALYZE_MODEL=claude-haiku-4-5-20251001
CHAIN_ANALYZE_MAX_TOKENS=1500
CHAIN_ANALYZE_TEMPERATURE=0.7
CHAIN_ANALYZE_TIMEOUT=20

# High-quality content generation (Sonnet for better writing)
CHAIN_PROCESS_MODEL=claude-sonnet-4-5-20250929
CHAIN_PROCESS_MAX_TOKENS=4000
CHAIN_PROCESS_TEMPERATURE=0.8
CHAIN_PROCESS_TIMEOUT=60

# Careful polishing (higher tokens for detailed formatting)
CHAIN_SYNTHESIZE_MODEL=claude-sonnet-4-5-20250929
CHAIN_SYNTHESIZE_MAX_TOKENS=2000
CHAIN_SYNTHESIZE_TEMPERATURE=0.5
CHAIN_SYNTHESIZE_TIMEOUT=30

# Lenient validation (accept some lower-confidence outputs)
CHAIN_ENABLE_VALIDATION=true
CHAIN_STRICT_VALIDATION=false
```

**Typical**: Batch processing, $0.020-0.030/request

### Data Processing (Forms, Documents)

**Goal**: Extract and validate information from structured or semi-structured input

```env
# Careful analysis of document structure
CHAIN_ANALYZE_MODEL=claude-haiku-4-5-20251001
CHAIN_ANALYZE_MAX_TOKENS=2000
CHAIN_ANALYZE_TEMPERATURE=0.3
CHAIN_ANALYZE_TIMEOUT=20

# Accurate extraction (Sonnet for complex documents)
CHAIN_PROCESS_MODEL=claude-sonnet-4-5-20250929
CHAIN_PROCESS_MAX_TOKENS=2000
CHAIN_PROCESS_TEMPERATURE=0.3
CHAIN_PROCESS_TIMEOUT=30

# Validation and formatting
CHAIN_SYNTHESIZE_MODEL=claude-haiku-4-5-20251001
CHAIN_SYNTHESIZE_MAX_TOKENS=1000
CHAIN_SYNTHESIZE_TEMPERATURE=0.2
CHAIN_SYNTHESIZE_TIMEOUT=15

# Strict validation (fail on errors)
CHAIN_ENABLE_VALIDATION=true
CHAIN_STRICT_VALIDATION=true
```

**Typical**: Batch processing, $0.010-0.015/request

## Customization

### Customizing System Prompts

Each step loads its behavior from a markdown file in `src/workflow/prompts/`:

1. **chain_analyze.md**: Edit to customize intent parsing and entity extraction logic
2. **chain_process.md**: Edit to customize content generation approach
3. **chain_synthesize.md**: Edit to customize formatting and polishing rules

**Important**: Each prompt MUST output valid JSON matching its Pydantic model:
- `AnalysisOutput`: `{"intent": "...", "key_entities": [...], "complexity": "...", "context": {...}}`
- `ProcessOutput`: `{"content": "...", "confidence": 0.85, "metadata": {...}}`
- `SynthesisOutput`: `{"final_text": "...", "formatting": "markdown"}`

No markdown wrappers or extra text - valid JSON only.

### Extending Domain Models

Edit `src/workflow/models/chains.py` to add domain-specific fields:

```python
class AnalysisOutput(BaseModel):
    intent: str
    key_entities: list[str]
    complexity: str
    context: dict[str, Any]
    # Add your domain fields here:
    sentiment: str = "neutral"  # Example
    priority: int = 0            # Example

class ProcessOutput(BaseModel):
    content: str
    confidence: float
    metadata: dict[str, Any]
    # Add your domain fields here:
    citations: list[str] = []    # Example
    warnings: list[str] = []     # Example
```

Update system prompts to output these new fields in the JSON.

### Adding Custom Validation

Edit `src/workflow/chains/validation.py` to add business logic:

```python
class CustomValidationGate(ValidationGate):
    def validate(self, data: dict) -> tuple[bool, str | None]:
        # Your validation logic here
        if some_condition_failed:
            return False, "Human-readable error message"
        return True, None
```

## Next Steps

- **For configuration details**: See `CLAUDE.md` "Chain Configuration Reference"
- **For technical deep dive**: See `ARCHITECTURE.md` "Prompt-Chaining Step Functions" and "LangGraph StateGraph"
- **For API reference**: See `README.md` "API Reference" or http://localhost:8000/docs
- **For benchmarks**: Run `python scripts/benchmark_chain.py` to see performance of different configurations
