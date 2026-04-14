# Agent-to-Agent Delegation

The `run_agent` tool lets one agent execute another and use its result. Configure which agents can be called via the `agents` field in frontmatter.

## Configuration

Add an `agents` allowlist to the calling agent's frontmatter:

```yaml
---
name: orchestrator
agents:
  - web-researcher
  - summarizer
---

Research the topic, then summarize the findings.
```

Agents are referenced by their `name` field (not filename). Only agents listed in `agents` can be called.

## Tool Signature

```python
def run_agent(agent_name: str, arguments: str = "") -> dict
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `agent_name` | `str` | Yes | Name of the target agent (must be in `agents` allowlist) |
| `arguments` | `str` | No | Arguments passed to the target agent |

## Return Value

**Success:**
```json
{
  "status": "success",
  "output": "The agent's final answer text",
  "execution_id": 42,
  "duration_ms": 3200,
  "total_tokens": 1580,
  "cost_usd": 0.002
}
```

**Error:**
```json
{
  "error": "Agent 'unknown' is not in the allowed agents list"
}
```

Possible errors:

| Error | Cause |
|---|---|
| `not in the allowed agents list` | Agent not in `agents` frontmatter |
| `Agent cannot call itself` | Self-call attempted |
| `Maximum agent call depth (N) reached` | Nesting too deep |
| `Agent 'X' not found` | Target not registered |
| `Agent 'X' is not enabled` | Target has `enabled: false` |

## Depth Limit

Agent calls can be nested (A calls B calls C). The default maximum depth is **3**, configurable in `config.yaml`:

```yaml
defaults:
  max_agent_depth: 5
```

## Execution Model

- Each delegated agent runs as an **independent execution** with its own sandbox, tools, and token tracking
- The trigger type is recorded as `agent` (visible in logs and API)
- Executions are linked via `parent_execution_id` for traceability
- Token usage and cost are tracked separately per execution

## Restrictions

- **Allowlist only** — agents can only call agents listed in their `agents` field
- **No self-calls** — an agent cannot call itself
- **Own sandbox** — the target agent uses its own `paths`, tools, and model config
- **Name-based** — agents are referenced by their frontmatter `name`, not by filename

## Example: Orchestrator Pattern

**orchestrator.md:**
```yaml
---
name: orchestrator
agents:
  - web-researcher
  - summarizer
settings:
  temperature: 0.3
---

You coordinate research tasks.

1. Call `web-researcher` with the research topic as arguments
2. Pass the research output to `summarizer` for a concise summary
3. Save the final summary to `output/research-summary.md`
```

**web-researcher.md:**
```yaml
---
name: web-researcher
mcp:
  - fetch
---

Research the given topic using web tools. Return detailed findings.
```

**summarizer.md:**
```yaml
---
name: summarizer
settings:
  temperature: 0.2
  max_tokens: 2048
---

Summarize the provided text into 3-5 key bullet points.
```
