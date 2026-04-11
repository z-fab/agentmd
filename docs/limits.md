# Execution Limits

AgentMD enforces hard limits to prevent runaway agents from consuming
unbounded resources. All limits are optional and configurable per agent.

## Configuration

In agent frontmatter:

```yaml
settings:
  timeout: 600             # wall-clock seconds (default: 300)
  max_tool_calls: 50       # max tool invocations (default: 50)
  max_execution_tokens: 500000  # input+output tokens combined (default: 500,000)
  max_cost_usd: 0.50       # estimated cost cap in USD (default: none)
  loop_detection: true      # abort on repeated errors (default: true)
```

Set any limit to `null` to disable it:

```yaml
settings:
  max_tool_calls: null  # no limit
```

## Global Defaults

Override defaults for all agents in `~/.config/agentmd/config.yaml`:

```yaml
defaults:
  provider: google
  model: gemini-3-flash-preview
  max_tool_calls: 25
  max_execution_tokens: 200000
  max_cost_usd: 1.00
  loop_detection: true
```

Priority: **agent frontmatter > config.yaml > hardcoded defaults**.

## Understanding token limits

- **`max_tokens`** (default: 4096) — Maximum tokens for a single LLM response. This is the per-call output limit sent to the provider.
- **`max_execution_tokens`** (default: 500,000) — Cumulative token budget for the entire execution. Counts all input + output tokens across every LLM call. When exceeded, the execution aborts.

Example: An agent that makes 10 tool calls will invoke the LLM 10+ times. Each call respects `max_tokens` for its individual response, but `max_execution_tokens` caps the total across all calls.

## How Limits Work

Limits are checked after every message in the execution stream:

- **max_tool_calls** — counts each tool invocation. Aborts after the Nth call.
- **max_execution_tokens** — sums input + output tokens across all LLM calls. Aborts when exceeded.
- **max_cost_usd** — estimates cost using built-in pricing data. Aborts when estimated cost exceeds the cap. If pricing data is unavailable for the model, a warning is logged and the limit is not enforced.
- **loop_detection** — tracks the last 3 tool error responses. If all 3 are identical (same tool, same error), aborts.
- **timeout** — wall-clock limit via `asyncio.wait_for`. Note: synchronous tools that block the event loop may delay cancellation.

When a limit is hit, the execution finishes with status `aborted` and the reason is recorded in the error field.

## Pricing

Cost estimation uses a built-in pricing table at `agent_md/core/pricing.yaml`.
To override or add models, create `~/.config/agentmd/pricing.yaml` with the same format:

```yaml
# USD per 1M tokens
google:
  my-custom-model:
    input: 1.00
    output: 5.00
```

User overrides merge with built-in prices (user values win).

## Ghost Cleanup

Executions that were interrupted without cleanup (OOM, `kill -9`) are
detected on the next startup. If the PID recorded in the execution no
longer exists, the status is changed to `orphaned`.

Statuses related to interruptions:
- `aborted` — limit or loop detection hit
- `timeout` — wall-clock timeout reached
- `orphaned` — detected on startup, PID no longer running
