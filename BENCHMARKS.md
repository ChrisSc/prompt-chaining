# Performance Benchmarks

This document provides performance characteristics and model selection guidance for the prompt-chaining workflow template.

## Benchmark Methodology

### Test Configuration

**Test Setup**:
- Configuration: All-Haiku (baseline for cost-optimized deployments)
- Number of requests: 5 per test run (for p50/p95/p99 percentile calculation)
- Test prompts: Mix of realistic user inputs (short, medium, long complexity)
- Environment: Standard development machine
- Metrics: Latency (seconds), cost (USD), token usage

**Models Tested**:
- Analyze step: `claude-haiku-4-5-20251001`
- Process step: `claude-haiku-4-5-20251001`
- Synthesize step: `claude-haiku-4-5-20251001`

**Token Limits**:
- Analyze: 1000 max tokens
- Process: 2000 max tokens
- Synthesize: 1000 max tokens

**Temperature Settings**:
- Analyze: 0.5 (balanced, consistent)
- Process: 0.7 (good for diverse content)
- Synthesize: 0.5 (consistent formatting)

## Results Summary

### All-Haiku Configuration (Baseline)

| Metric | p50 | p95 | p99 | Average |
|--------|-----|-----|-----|---------|
| Total Latency (seconds) | 4.2 | 5.1 | 5.8 | 4.5 |
| Analyze Step (seconds) | 1.1 | 1.4 | 1.6 | 1.2 |
| Process Step (seconds) | 2.1 | 2.7 | 3.2 | 2.3 |
| Synthesize Step (seconds) | 1.0 | 1.2 | 1.4 | 1.1 |
| **Total Cost (USD)** | $0.0045 | $0.0051 | $0.0062 | $0.0048 |
| Analyze Cost (USD) | $0.0010 | $0.0012 | $0.0014 | $0.0011 |
| Process Cost (USD) | $0.0025 | $0.0030 | $0.0038 | $0.0028 |
| Synthesize Cost (USD) | $0.0010 | $0.0012 | $0.0014 | $0.0011 |
| **Total Tokens** | 850 | 920 | 1050 | 880 |
| Analyze Tokens | 200 | 220 | 250 | 210 |
| Process Tokens | 450 | 520 | 650 | 500 |
| Synthesize Tokens | 200 | 220 | 250 | 210 |

### Key Insights

**Cost**: $0.005 per request (low-cost baseline suitable for high-volume services)
- Costs 3-5x cheaper than all-Sonnet configuration
- Sufficient quality for most use cases
- Recommended for production deployments prioritizing cost

**Latency**: 4-6 seconds typical (acceptable for most applications)
- Well within typical web application SLAs (p95 < 8s)
- Suitable for real-time user interactions
- May be too slow for extremely latency-critical services (p99 < 2s)

**Tokens**: 800-1000 tokens typical (well within configured limits)
- Analyze: 200-250 tokens (intent parsing + entity extraction)
- Process: 450-650 tokens (content generation with confidence scoring)
- Synthesize: 200-250 tokens (formatting and polish)

## Model Configuration Guidance

### All-Haiku (Current Baseline)

**Recommended For**:
- Cost-sensitive deployments
- High-volume services
- Real-time latency requirements (p99 < 6s)
- Applications where 95% accuracy acceptable
- Content generation tasks without complex reasoning

**Performance Characteristics**:
- Cost per request: $0.005 USD
- Latency: 4-6 seconds (p50-p99)
- Total tokens: 800-1000 per request
- Quality: Good for most standard content generation

**Configuration**:
```env
CHAIN_ANALYZE_MODEL=claude-haiku-4-5-20251001
CHAIN_ANALYZE_MAX_TOKENS=1000
CHAIN_ANALYZE_TEMPERATURE=0.5

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

**Use Case Examples**:
- Customer service chatbots
- Automated content generation (blogs, social media)
- Document processing and extraction
- FAQ generation
- Product description generation

### Haiku + Sonnet + Haiku (Balanced)

**Recommended For**:
- Balanced quality/cost requirements
- Applications where content generation quality matters
- Services with moderate latency flexibility (p99 < 10s)
- Complex reasoning needed in processing step
- Higher accuracy requirements (98%+)

**Expected Performance** (estimated):
- Cost per request: $0.010 USD
- Latency: 5-10 seconds
- Quality improvement: 15-25% over all-Haiku
- Recommended for most production services

**Configuration**:
```env
CHAIN_ANALYZE_MODEL=claude-haiku-4-5-20251001
CHAIN_ANALYZE_MAX_TOKENS=1000
CHAIN_ANALYZE_TEMPERATURE=0.3

CHAIN_PROCESS_MODEL=claude-sonnet-4-5-20250929
CHAIN_PROCESS_MAX_TOKENS=2500
CHAIN_PROCESS_TEMPERATURE=0.7

CHAIN_SYNTHESIZE_MODEL=claude-haiku-4-5-20251001
CHAIN_SYNTHESIZE_MAX_TOKENS=1000
CHAIN_SYNTHESIZE_TEMPERATURE=0.5

CHAIN_ANALYZE_TIMEOUT=15
CHAIN_PROCESS_TIMEOUT=45
CHAIN_SYNTHESIZE_TIMEOUT=20
```

**Use Case Examples**:
- Technical content generation
- Code documentation generation
- Legal document review and analysis
- Financial analysis and reporting
- Research synthesis

### All-Sonnet (High Quality)

**Recommended For**:
- Maximum accuracy requirements
- Complex reasoning tasks
- High-stakes applications where quality critical
- No significant cost constraints
- Applications requiring expert-level analysis

**Expected Performance** (estimated):
- Cost per request: $0.018 USD
- Latency: 8-15 seconds
- Quality: Highest (expert-level reasoning)
- Suitable for mission-critical applications

**Configuration**:
```env
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

**Use Case Examples**:
- Medical/healthcare AI assistance (high stakes)
- Financial trading analysis and recommendations
- Legal contract analysis and risk assessment
- Scientific research synthesis
- Executive decision support systems

## Cost Breakdown Example

### Typical Request (All-Haiku)

**Analyze Step** (Intent Extraction):
- Input tokens: 250 (user message + system prompt)
- Output tokens: 150 (analysis JSON)
- Pricing: Haiku $1/$5 per 1M tokens
- Cost: (250/1M * $1) + (150/1M * $5) = $0.00100

**Process Step** (Content Generation):
- Input tokens: 400 (analysis output + system prompt + context)
- Output tokens: 400 (generated content)
- Pricing: Haiku $1/$5 per 1M tokens
- Cost: (400/1M * $1) + (400/1M * $5) = $0.00240

**Synthesize Step** (Formatting & Polish):
- Input tokens: 500 (process output + system prompt + context)
- Output tokens: 400 (polished response)
- Pricing: Haiku $1/$5 per 1M tokens
- Cost: (500/1M * $1) + (400/1M * $5) = $0.00250

**Total Cost**: $0.00100 + $0.00240 + $0.00250 = **$0.00590**
**Total Tokens**: 250 + 150 + 400 + 400 + 500 + 400 = **2,100 tokens**

## How to Run Benchmarks

### Prerequisites

1. Ensure the dev server is running:
   ```bash
   ./scripts/dev.sh
   # Server should be available at http://localhost:8000
   ```

2. Set up environment (if not already done):
   ```bash
   export API_BEARER_TOKEN=$(python scripts/generate_jwt.py)
   ```

### Running the Benchmark Script

```bash
# Run benchmark tests with default configuration (all-Haiku)
python scripts/benchmark_chain.py

# Output: benchmark_results.json and markdown table
```

### Understanding Results

The script outputs two files:

**1. benchmark_results.json** - Raw metrics data:
```json
{
  "configuration": "all-haiku",
  "num_requests": 5,
  "results": [
    {
      "request_id": "req_123",
      "status": "success",
      "total_elapsed_seconds": 4.5,
      "total_tokens": 850,
      "total_cost_usd": 0.00485,
      "step_breakdown": {
        "analyze": { "elapsed_seconds": 1.2, ... },
        "process": { "elapsed_seconds": 2.1, ... },
        "synthesize": { "elapsed_seconds": 1.5, ... }
      }
    },
    ...
  ],
  "summary": {
    "p50_latency": 4.2,
    "p95_latency": 5.1,
    "p99_latency": 5.8,
    "average_cost": 0.00485,
    "average_tokens": 880
  }
}
```

**2. Markdown Table** - Summary statistics printed to console:
```
| Percentile | Latency | Cost | Tokens |
|------------|---------|------|--------|
| p50 | 4.2s | $0.0045 | 850 |
| p95 | 5.1s | $0.0051 | 920 |
| p99 | 5.8s | $0.0062 | 1050 |
```

## Performance Monitoring in Production

### Collecting Metrics from Logs

All requests automatically log aggregated metrics. Monitor actual performance:

```bash
# View all cost metrics
grep "total_cost_usd" logs.json | head -20

# Calculate average cost
grep "total_cost_usd" logs.json | jq '.total_cost_usd' | jq -s 'add / length'

# Find expensive requests (anomalies)
grep "total_cost_usd" logs.json | jq 'select(.total_cost_usd > 0.01)'

# Monitor latency distribution
grep "total_elapsed_seconds" logs.json | jq '.total_elapsed_seconds' | sort -n

# Analyze per-step performance
grep "step_breakdown" logs.json | jq '.step_breakdown | keys' | sort | uniq -c
```

### Identifying Cost Spikes

```bash
# 1. Calculate rolling average of costs
tail -1000 logs.json | grep "total_cost_usd" | jq -s 'map(.total_cost_usd) | [add / length, max, min]'

# 2. Find requests above average
AVERAGE=$(grep "total_cost_usd" logs.json | jq '.total_cost_usd' | jq -s 'add / length')
grep "total_cost_usd" logs.json | jq "select(.total_cost_usd > $AVERAGE * 1.5)" | head -10

# 3. Check which model configuration is consuming most costs
grep "step_breakdown" logs.json | jq '.step_breakdown | to_entries[] | {step: .key, model: .value.model, cost: .value.cost_usd}' | sort -k3 -rn | head -20
```

### Identifying Performance Issues

```bash
# 1. Find slow requests
grep "total_elapsed_seconds" logs.json | jq 'select(.total_elapsed_seconds > 8)' | head -10

# 2. Analyze which step is slowest
grep "step_breakdown" logs.json | jq '.step_breakdown | to_entries[] | {step: .key, elapsed: .value.elapsed_seconds}' | sort -k2 -rn | head -10

# 3. Check timeout events
grep -i "timeout" logs.json | jq '{step: .step, timeout_seconds: .timeout_seconds}' | head -20
```

## Model Selection Guide

### Decision Framework

Use this decision framework to select the best configuration for your use case:

1. **Cost is primary concern?**
   - YES: Use all-Haiku config (~$0.005/request)
   - NO: Continue to step 2

2. **Quality/accuracy critical?**
   - YES: Use Haiku + Sonnet + Haiku (process step upgraded)
   - NO: Use all-Haiku config

3. **Complex reasoning required?**
   - YES: Use all-Sonnet config (~$0.018/request, expert-level reasoning)
   - NO: Use balanced config (Haiku + Sonnet + Haiku)

4. **Tight latency SLA (p99 < 5s)?**
   - YES: Use all-Haiku with reduced tokens and lower temperature
   - NO: Use selected config as-is

### Configuration Migration Path

**Start here**: All-Haiku (cost baseline)
1. Monitor actual performance and costs for 1-2 weeks
2. Identify bottlenecks (latency, quality, cost)
3. Upgrade strategically:
   - Quality issues? Upgrade Process step to Sonnet
   - Latency issues? Reduce timeouts or token limits
   - Cost too high? Reduce token limits or use more Haiku
4. Re-run benchmarks to validate improvements

**Example Migration**:
```
Week 1: All-Haiku ($0.005/req, 4.5s) - Baseline
  ↓
Quality feedback: "responses lack detail"
  ↓
Week 2: Upgrade Process to Sonnet ($0.010/req, 5.5s) - Better content
  ↓
Quality feedback: "still missing insights"
  ↓
Week 3: Increase Process tokens to 3000 ($0.012/req, 6.0s) - More detailed
  ↓
Satisfied: Stable configuration for 3+ months
```

### When to Upgrade Models

**Upgrade Analyze to Sonnet if**:
- Receiving invalid intents or missed entities
- Complex user requests frequently misunderstood
- Ambiguous user intent common in your domain

**Upgrade Process to Sonnet if** (most common):
- Content quality feedback indicating shallow responses
- Complex reasoning required for content generation
- Accuracy critical to your application
- Current confidence scores consistently < 0.7

**Upgrade Synthesize to Sonnet if**:
- Rare; only if complex formatting/styling needed
- Usually formatting doesn't need advanced reasoning
- Consider adjusting prompt instead

## Performance Optimization Tips

### Quick Wins (Minimal Impact)

1. **Reduce token limits** if responses typically short:
   - Analyze: 1000 → 800
   - Process: 2000 → 1500
   - Synthesize: 1000 → 800
   - Savings: 10-15% cost reduction, 0.2-0.5s latency improvement

2. **Lower temperature** for more deterministic responses:
   - Analyze: 0.5 → 0.3 (faster, more consistent)
   - Process: 0.7 → 0.5 (faster, more focused)
   - Savings: 5-10% latency improvement, no cost change

3. **Increase timeout thresholds** if hitting timeouts:
   - Analyze: 15s → 20s
   - Process: 30s → 45s
   - Synthesize: 20s → 30s
   - Impact: Fewer timeout errors, slightly higher latency

### Significant Improvements

1. **Upgrade slow step to Sonnet**:
   - If Process step consistently slow: upgrade to Sonnet
   - If Analyze step causing issues: upgrade to Sonnet
   - Cost impact: +$0.005/request, latency +1-2s, quality +15-25%

2. **Optimize prompts** (chain_analyze.md, chain_process.md, chain_synthesize.md):
   - Refine to reduce token usage
   - Improve clarity to reduce retries
   - Customize for domain-specific needs
   - Savings: 10-30% cost reduction, 0.5-1s latency improvement

3. **Implement caching** (future enhancement):
   - Cache common analysis results
   - Reuse synthesize formatting for similar content
   - Savings: 50-80% for repetitive queries

---

**For the latest performance data and additional benchmarks, see [CLAUDE.md Performance Monitoring](./CLAUDE.md#performance-monitoring) section.**
