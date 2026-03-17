# Performance

Optimize token usage, response time, and cost for Agent.md agents.

## Token Optimization

### 1. Shorten System Prompts

Tokens are counted for every message, including the system prompt. Shorter prompts = lower cost.

**Verbose (expensive):**
```markdown
---
name: summarizer
---

You are a highly capable AI assistant specialized in summarizing documents.
Your task is to read the input document, analyze its contents thoroughly,
identify the key points and main ideas, and then produce a concise summary
that captures the essential information while being significantly shorter
than the original. You should maintain the core meaning and important details,
but remove redundant information, examples that aren't critical, and verbose
explanations. The summary should be clear, well-structured, and easy to read.

When you receive a document:
1. First, read the entire document carefully
2. Then, identify the main themes and key points
3. Next, organize these points logically
4. Finally, write a summary that is approximately 25% the length of the original

Remember to maintain objectivity and accuracy in your summaries.
```

**Concise (efficient):**
```markdown
---
name: summarizer
---

Summarize documents to ~25% of original length. Preserve key points, remove redundancy.

Steps:
1. Read document
2. Extract main points
3. Write concise summary
```

**Token savings:** ~150 tokens → ~30 tokens = 80% reduction

This adds up:
- 10 executions/day × 120 tokens saved × 30 days = 36,000 tokens/month saved
- At $0.03/1K tokens = $1.08/month saved per agent

### 2. Use Focused Instructions

Tell the agent exactly what to do without extra context.

**Unfocused:**
```markdown
You are an expert data analyst. Analyze this CSV file and provide insights.
Think about patterns, trends, anomalies, and interesting findings. Consider
statistical significance and practical implications. Your analysis should
be thorough and actionable.
```

**Focused:**
```markdown
Analyze CSV for: 1) Top 3 trends, 2) Anomalies >2σ, 3) Actionable recommendations.
Output as JSON.
```

### 3. Limit Tool Descriptions

Tools are injected into every prompt. Keep tool descriptions brief.

**Verbose:**
```python
@tool
def calculate_statistics(data: list[float]) -> dict:
    """
    This tool calculates comprehensive statistical measures for a given dataset.
    It computes the mean (average), median (middle value), mode (most common),
    standard deviation (measure of spread), variance (square of std dev),
    minimum value, maximum value, and quartiles (25th, 50th, 75th percentiles).

    Args:
        data: A list of numerical values (integers or floats) to analyze

    Returns:
        A dictionary containing all computed statistics

    Example:
        >>> calculate_statistics([1, 2, 3, 4, 5])
        {'mean': 3.0, 'median': 3.0, ...}
    """
    ...
```

**Concise:**
```python
@tool
def calculate_statistics(data: list[float]) -> dict:
    """Calculate mean, median, mode, std dev, min, max for dataset."""
    ...
```

### 4. Reduce Conversation History

Each turn adds to context length. Limit history retention.

```yaml
---
name: chatbot
settings:
  max_history: 5  # Keep last 5 turns only
---
```

**Context growth:**
```
Turn 1: 100 tokens (system) + 50 (user) + 80 (AI) = 230 tokens
Turn 2: 230 + 50 (user) + 80 (AI) = 360 tokens
Turn 3: 360 + 50 (user) + 80 (AI) = 490 tokens
...
Turn 10: 1,030 tokens

With max_history=5:
Turn 10: 100 (system) + 250 (last 5 turns) = 350 tokens
```

### 5. Set Appropriate max_tokens

Don't request more tokens than needed.

```yaml
# Summary task (short output)
model:
  max_tokens: 500  # Not 2000

# Report generation (long output)
model:
  max_tokens: 2000

# JSON extraction (very short)
model:
  max_tokens: 200
```

**Cost impact:**
```
Requested: 2000 tokens
Actual need: 300 tokens
Wasted budget: 1700 tokens (but only charged for 300 used)

However, reserving 2000 affects rate limits and may cause context errors.
```

### 6. Batch Operations

Process multiple items in one execution instead of separate runs.

**Inefficient (multiple runs):**
```bash
# Process 10 files = 10 executions
for file in *.txt; do
  agentmd run summarizer --input $file
done

# Cost: 10 × (system prompt + overhead) = ~1,500 tokens
```

**Efficient (one run):**
```markdown
---
name: batch-summarizer
---

Summarize all .txt files in /workspace/data/.
For each file, write summary to /output/{filename}_summary.txt.
```

```bash
# Process 10 files = 1 execution
agentmd run batch-summarizer

# Cost: 1 × (system prompt + overhead) = ~200 tokens
# Savings: 1,300 tokens
```

## Temperature Tuning

Temperature controls randomness. Lower = deterministic, higher = creative.

### Deterministic Tasks (temperature = 0.0 - 0.3)

```yaml
# Data extraction, classification, structured output
model:
  temperature: 0.1
```

**Use cases:**
- JSON extraction
- Data validation
- Classification
- Code generation
- Fact-based Q&A

**Example:**
```yaml
---
name: json-extractor
model:
  provider: openai
  name: gpt-4
  temperature: 0.0  # Consistent output
---

Extract data from email and output as JSON:
{
  "from": "...",
  "subject": "...",
  "date": "...",
  "priority": "high|medium|low"
}
```

### Balanced Tasks (temperature = 0.4 - 0.7)

```yaml
# General purpose, research, analysis
model:
  temperature: 0.5
```

**Use cases:**
- Research
- Summarization
- Question answering
- General analysis

### Creative Tasks (temperature = 0.8 - 1.0)

```yaml
# Writing, brainstorming, content generation
model:
  temperature: 0.9
```

**Use cases:**
- Creative writing
- Marketing copy
- Brainstorming
- Varied responses

**Cost consideration:**
Higher temperature may generate longer outputs → more tokens → higher cost.

## Timeout Tuning

Balance reliability with cost.

### Short Timeouts (30-60s)

```yaml
settings:
  timeout: 60
```

**Use cases:**
- Simple tasks (summarization, extraction)
- Single tool calls
- Fast APIs

**Benefit:** Fail fast if something goes wrong, prevent runaway costs.

### Medium Timeouts (2-5min)

```yaml
settings:
  timeout: 300  # 5 minutes
```

**Use cases:**
- Multi-step workflows
- Multiple tool calls
- Web scraping
- File processing

### Long Timeouts (10-30min)

```yaml
settings:
  timeout: 1800  # 30 minutes
```

**Use cases:**
- Research tasks
- Large dataset processing
- Complex analysis

**Warning:** Long timeouts with expensive models can rack up costs if agent gets stuck.

**Best practice:** Combine timeout with max_iterations:
```yaml
settings:
  timeout: 300
  max_iterations: 10  # Prevent infinite loops even if under timeout
```

## Prompt Length Optimization

### 1. Use References Instead of Full Content

**Bad (includes full file):**
```markdown
---
name: analyzer
---

Analyze this data:
{paste 10,000 lines of CSV data here}
```

**Good (reference file):**
```markdown
---
name: analyzer
paths:
  - /workspace/data/large.csv
---

Read /workspace/data/large.csv and analyze the data.
```

### 2. Use Examples Sparingly

Few-shot examples improve quality but add tokens.

**Minimal (0-shot):**
```markdown
Extract name and email from text. Output as JSON.
```

**Balanced (1-shot):**
```markdown
Extract name and email from text. Output as JSON.

Example:
Input: "Contact John Doe at john@example.com"
Output: {"name": "John Doe", "email": "john@example.com"}
```

**Heavy (3-shot):**
```markdown
Extract name and email from text. Output as JSON.

Example 1: ...
Example 2: ...
Example 3: ...
```

**Guideline:**
- 0-shot: Simple, well-defined tasks
- 1-shot: Most tasks
- 2-3 shot: Complex or ambiguous tasks

### 3. Avoid Redundancy

**Redundant:**
```markdown
You are a helpful assistant. Be helpful and provide assistance.
Respond in a helpful manner and assist the user helpfully.
```

**Concise:**
```markdown
Provide helpful assistance.
```

## Schedule Frequency Optimization

### Calculate Execution Costs

```
Cost per execution: $0.05
Schedule: Every hour (24x/day)
Daily cost: 24 × $0.05 = $1.20
Monthly cost: $1.20 × 30 = $36.00
Annual cost: $36.00 × 12 = $432.00
```

### Right-Size Schedule Frequency

**Question:** "How often does data actually change?"

**Example: News aggregator**
```yaml
# Inefficient: Check every minute
triggers:
  - type: schedule
    cron: "* * * * *"  # 1,440 executions/day

# Efficient: News updates hourly
triggers:
  - type: schedule
    cron: "0 * * * *"  # 24 executions/day

# Savings: 1,416 executions/day × $0.05 = $70.80/day saved
```

**Example: Daily report**
```yaml
# Perfect: Once per day
triggers:
  - type: schedule
    cron: "0 9 * * *"  # 9 AM daily

# Cost: 1 execution/day × $0.05 = $0.05/day = $1.50/month
```

### Use Watch Triggers Instead of Polling

**Inefficient (polling):**
```yaml
# Check for new files every minute
triggers:
  - type: schedule
    cron: "* * * * *"
---
Check if /workspace/data/input.json exists. If yes, process it.
```

**Efficient (watch):**
```yaml
# React to file changes only
triggers:
  - type: watch
    paths: ["/workspace/data/input.json"]
    debounce: 2.0
---
Process /workspace/data/input.json
```

**Savings:**
- Polling: 1,440 executions/day (most find no new file)
- Watch: ~10 executions/day (only when file changes)
- Savings: 1,430 executions/day

## Provider Comparison

### Cost per 1M Tokens (March 2026 estimates)

| Provider | Model | Input | Output | Use Case |
|----------|-------|-------|--------|----------|
| OpenAI | GPT-4 Turbo | $10 | $30 | General, balanced |
| OpenAI | GPT-3.5 Turbo | $0.50 | $1.50 | Fast, cheap, simple tasks |
| Anthropic | Claude Opus 4.6 | $15 | $75 | Complex reasoning, long context |
| Anthropic | Claude Sonnet 4.5 | $3 | $15 | Balanced performance/cost |
| Google | Gemini Pro | $0.50 | $1.50 | Cheap, fast |
| Ollama | Llama 3.1 8B | $0 | $0 | Local, free, privacy |

### Choose the Right Model

**Simple tasks (extraction, classification):**
```yaml
model:
  provider: openai
  name: gpt-3.5-turbo  # 10x cheaper than GPT-4
  temperature: 0.0
```

**Complex tasks (research, analysis):**
```yaml
model:
  provider: anthropic
  name: claude-sonnet-4-5  # Good balance
  temperature: 0.5
```

**Long documents (100K+ tokens):**
```yaml
model:
  provider: anthropic
  name: claude-opus-4-6  # 200K context window
  temperature: 0.3
```

**Cost-sensitive or local:**
```yaml
model:
  provider: ollama
  name: llama3.1:8b  # Free, runs locally
  temperature: 0.5
```

### Model Switching Strategy

Use cheap models for simple steps, expensive models for hard steps.

**Example: Research pipeline**

```yaml
# Step 1: Extract URLs (cheap)
---
name: extract-urls
model:
  provider: openai
  name: gpt-3.5-turbo
---
Extract all URLs from /workspace/data/articles.txt
```

```yaml
# Step 2: Analyze content (expensive)
---
name: analyze-content
model:
  provider: anthropic
  name: claude-opus-4-6
---
Deep analysis of content from extracted URLs.
```

**Cost:**
- All-Opus: $0.50/run
- Turbo + Opus: $0.05 + $0.30 = $0.35/run
- Savings: 30%

## Performance Monitoring

### Track Token Usage

```bash
# View token usage over time
agentmd logs my-agent --verbose

# Sample output:
# 2026-03-11 09:00 | 1,234 tokens | $0.05
# 2026-03-11 10:00 | 1,456 tokens | $0.06
# 2026-03-11 11:00 | 8,901 tokens | $0.35  ← Spike!
```

### Set Usage Alerts

```bash
# Example monitoring script
#!/bin/bash
AGENT="my-agent"
MAX_TOKENS=5000

LATEST=$(agentmd logs $AGENT --format json | jq '.[0].total_tokens')

if [ $LATEST -gt $MAX_TOKENS ]; then
  echo "Alert: $AGENT used $LATEST tokens (max: $MAX_TOKENS)"
  # Send alert (email, Slack, etc.)
fi
```

### Measure Execution Time

```bash
# Time an execution
time agentmd run my-agent

# Output:
# real    0m23.456s
# user    0m1.234s
# sys     0m0.123s
```

### Benchmark Different Configurations

```bash
# Test 1: GPT-3.5 Turbo
agentmd run my-agent --model gpt-3.5-turbo --verbose

# Test 2: GPT-4
agentmd run my-agent --model gpt-4 --verbose

# Compare:
# - Token usage
# - Execution time
# - Output quality
# - Cost
```

## Optimization Checklist

- [ ] System prompt is concise (<200 tokens)
- [ ] Instructions are focused and specific
- [ ] Tool descriptions are brief
- [ ] `max_tokens` set appropriately for task
- [ ] `temperature` tuned for task type
- [ ] `max_history` limits conversation growth
- [ ] Schedule frequency matches data update rate
- [ ] Watch triggers used instead of polling where possible
- [ ] Batch operations used for multiple items
- [ ] Cheapest model that works is selected
- [ ] Timeout prevents runaway executions
- [ ] Token usage is monitored
- [ ] Examples in prompt are minimal (1-shot max)
- [ ] Full content is referenced, not embedded

## Real-World Optimization Example

**Before (expensive):**
```yaml
---
name: daily-summary
model:
  provider: openai
  name: gpt-4  # Expensive
  temperature: 0.9  # Unnecessary randomness
  max_tokens: 4000  # Too high
triggers:
  - type: schedule
    cron: "*/5 * * * *"  # Every 5 minutes (too frequent)
---

You are an expert AI assistant specialized in creating comprehensive
daily summaries of log files. Your task is to carefully read through
all the log entries, identify important events, errors, warnings,
and any unusual patterns. Then create a detailed summary report
that highlights the most critical information in a well-structured
format. Be thorough and don't miss any important details.

Please analyze the log files in /var/log/app/ and create a summary.
Include statistics, error counts, and recommendations for any issues
you find. Make the summary clear and actionable for the operations team.
```

**Cost:**
- Executions: 288/day (every 5 min)
- Tokens per execution: ~2,500
- Daily tokens: 720,000
- Daily cost: ~$25
- Monthly cost: ~$750

---

**After (optimized):**
```yaml
---
name: daily-summary
model:
  provider: openai
  name: gpt-3.5-turbo  # 10x cheaper
  temperature: 0.1  # Deterministic output
  max_tokens: 800  # Right-sized
triggers:
  - type: schedule
    cron: "0 8 * * *"  # Once daily at 8 AM
paths:
  - /var/log/app/*.log
  - /output/summaries/
---

Analyze logs in /var/log/app/ from last 24h. Output:
1. Error count by type
2. Top 3 warnings
3. Unusual patterns
4. Recommendations

Format as JSON.
```

**Cost:**
- Executions: 1/day
- Tokens per execution: ~600
- Daily tokens: 600
- Daily cost: ~$0.001
- Monthly cost: ~$0.03

**Savings: $750 → $0.03 = 99.996% reduction** 🎉

**Improvements:**
1. Switched to GPT-3.5 Turbo (10x cheaper)
2. Reduced temperature (0.9 → 0.1)
3. Lowered max_tokens (4000 → 800)
4. Changed schedule (every 5 min → daily)
5. Shortened prompt (200 → 50 tokens)
6. Made output structured (JSON)
