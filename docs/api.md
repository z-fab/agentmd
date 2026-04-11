# REST API Reference

AgentMD exposes an HTTP API over a Unix domain socket. The CLI uses this
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
| GET | `/agents` | List all agents |
| GET | `/agents/{name}` | Agent detail (config + last_run + next_run) |
| POST | `/agents/{name}/run` | Start execution, returns `{execution_id}` |
| GET | `/agents/{name}/runs` | Execution history for agent |
| POST | `/agents/reload` | Re-parse agent files from disk |

**Run request body:**
```json
{"args": ["arg1"], "message": "optional user message"}
```

When `message` is provided, it replaces the synthetic "Execute your task". This is how the CLI chat works — each chat turn is a `/run` with the user's message. The checkpointer handles conversation continuity.

### Executions

| Method | Path | Description |
|--------|------|-------------|
| GET | `/executions` | List executions (filters: `status`, `agent`, `limit`, `offset`) |
| GET | `/executions/{id}` | Execution detail |
| GET | `/executions/{id}/messages` | Full message log |
| GET | `/executions/{id}/stream` | SSE stream (catchup + live) |
| DELETE | `/executions/{id}` | Cancel running execution |

**SSE event types:** `message`, `meta`, `tool_call`, `tool_result`, `ai`, `final_answer`, `complete`

### Scheduler

| Method | Path | Description |
|--------|------|-------------|
| GET | `/scheduler` | Status + jobs with next_run |
| POST | `/scheduler/pause` | Pause scheduler |
| POST | `/scheduler/resume` | Resume scheduler |

## OpenAPI

Interactive docs available at `/docs` (Swagger) and `/redoc` when the backend is running.
