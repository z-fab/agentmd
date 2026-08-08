# REST API Reference

Agentmd exposes an HTTP API over a Unix domain socket. The CLI uses this
API internally — you can also use it directly for integrations.

## Connection

**Unix socket (default):**
```bash
curl --unix-socket ~/.local/state/agentmd/agentmd.sock http://localhost/health
```

**TCP (opt-in):** Start with `agentmd start --port 4100 --api-key YOUR_KEY`, then:
```bash
curl -H "X-API-Key: YOUR_KEY" http://127.0.0.1:4100/health
```

## Endpoints

### Health & Info

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | No | Liveness check |
| GET | `/info` | Yes | Backend status (version, pid, uptime, agents, scheduler) |
| POST | `/shutdown` | Yes | Graceful shutdown |

### Agents

| Method | Path | Description |
|--------|------|-------------|
| GET | `/agents` | List all agents (`id`, `display_name`, …) |
| GET | `/agents/{id}` | Agent detail (config + last_run + next_run); `{id}` is the filename stem |
| POST | `/agents/{id}/run` | Start execution, returns `{execution_id}` |
| GET | `/agents/{id}/runs` | Execution history for agent |
| POST | `/agents/reload` | Re-parse agent files from disk |

Path segments with spaces must be URL-encoded (e.g. `/agents/Daily%20Processor`). Lookup is by **id only** — a distinct display name does not resolve.

**Agent list/detail fields:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Canonical filename stem |
| `display_name` | string | Frontmatter `name:` or id |
| `name` | string | Alias of `display_name` (compat; not a route key) |

**Run request body:**
```json
{
  "args": ["arg1"],
  "message": "optional user message",
  "context": "optional trigger context",
  "session_id": "optional conversation id"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `args` | string[] | Positional arguments substituted into the prompt |
| `message` | string | Replaces the synthetic "Execute your task" |
| `context` | string | Appended to the user turn as trigger context |
| `session_id` | string | Conversation this run belongs to (max 200 chars; blank is treated as absent) |

When `message` is provided, it replaces the synthetic "Execute your task". This is how the CLI chat works — each chat turn is a `/run` with the user's message.

`session_id` is what makes a run a **conversation turn**: it is persisted on the
execution, recorded with `trigger: "chat"` instead of `"manual"`, and it scopes
history seeding. With `history` enabled the runner seeds the next execution from
the most recent finished execution **of the same session**; a run without a
`session_id` only ever seeds from other sessionless runs of that agent. Two
clients chatting with the same agent under different `session_id`s therefore keep
independent conversations, and a scheduled run never inherits chat context (a
`session_id` sent with a `schedule` or `watch` run is ignored).

Generating and reusing the id is the client's job — the backend never invents one
and there is no endpoint to list or resume sessions. Any opaque string works; a
UUID per conversation is the intended shape.

### Executions

| Method | Path | Description |
|--------|------|-------------|
| GET | `/executions` | List executions (filters: `status`, `agent`, `limit`, `offset`) |
| GET | `/executions/{id}` | Execution detail |
| GET | `/executions/{id}/messages` | Full message log |
| GET | `/executions/{id}/stream` | SSE stream (catchup + live) |
| DELETE | `/executions/{id}` | Cancel running execution |

**Execution response fields:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Execution ID |
| `agent_id` | string | Canonical agent id (filename stem) |
| `status` | string | `running`, `waiting`, `success`, `error`, `aborted`, `timeout`, `orphaned` |
| `trigger` | string | `manual`, `chat`, `schedule`, `watch`, `agent` |
| `parent_execution_id` | int \| null | Parent execution ID when triggered by `run_agent` |
| `session_id` | string \| null | Conversation the execution belongs to (`null` outside a chat) |
| `started_at` | string | ISO 8601 timestamp |
| `finished_at` | string \| null | ISO 8601 timestamp |
| `duration_ms` | int \| null | Execution duration |
| `total_tokens` | int \| null | Total token usage |
| `cost_usd` | float \| null | Estimated cost |
| `error` | string \| null | Error message if failed |

The `agent` trigger type indicates the execution was started by another agent via the `run_agent` tool. Use `parent_execution_id` to trace delegation chains.

**SSE event types:** `message`, `meta`, `tool_call`, `tool_result`, `ai`, `final_answer`, `complete`, `waiting`

Per-execution stream payloads include identity fields:

| Field | Meaning |
|-------|---------|
| `agent_id` | Canonical stem |
| `display_name` | Human label |
| `agent_name` | Same as `agent_id` (compat alias; **not** the display label) |

### Scheduler

| Method | Path | Description |
|--------|------|-------------|
| GET | `/scheduler` | Status + jobs with next_run |
| POST | `/scheduler/pause` | Pause scheduler |
| POST | `/scheduler/resume` | Resume scheduler |

### Events

| Method | Path | Description |
|--------|------|-------------|
| GET | `/events/stream` | Global SSE event stream |

**Event types:**

| Event | When | Data fields |
|-------|------|-------------|
| `heartbeat` | 10s of inactivity | `timestamp` |
| `execution_started` | Execution begins | `execution_id`, `agent_id`, `display_name`, `agent_name` (= id), `trigger` |
| `execution_completed` | Execution finishes | `execution_id`, `agent_id`, `display_name`, `agent_name` (= id), `status`, `duration_ms` |
| `agents_changed` | Agent file added/modified/deleted | `event` (`loaded`/`updated`/`removed`), `agent_id`, `display_name`, `agent_name` (= id) |
| `scheduler_changed` | Scheduler paused/resumed | `status` (`paused`/`running`) |

**Connection:**
```bash
curl --unix-socket ~/.local/state/agentmd/agentmd.sock http://localhost/events/stream
```

**Notes:**
- No reconnection replay — on reconnect, use REST endpoints to sync state
- Heartbeat replaces `/health` polling — if the connection is alive, the backend is online
- The SSE connection keeps the backend alive (counts as active stream for idle timeout)

## OpenAPI

Interactive docs available at `/docs` (Swagger) and `/redoc` when the backend is running.
