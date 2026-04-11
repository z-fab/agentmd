# Migration Guide: v0.7.x → v0.8.0

## Breaking Changes

### Backend replaces daemon

The `agentmd start` command now runs a FastAPI HTTP backend instead of
the old foreground daemon. The CLI communicates with it via Unix socket.

**What changed:**

- `agentmd start` runs the backend in **foreground** (was background)
- Use `agentmd start -d` for background (daemon) mode
- `agentmd run` auto-starts the backend if needed
- `agentmd stop` sends a shutdown request via HTTP (was SIGTERM)
- `agentmd status` queries the backend API (was PID file check)

**What didn't change:**

- Agent `.md` files — same format, same location
- Custom tools — same `@tool` interface
- CLI commands — same names and arguments
- `agentmd list`, `logs`, `validate` — still work without backend

### New dependencies

`fastapi`, `uvicorn`, and `httpx` are now core dependencies.

### Database

The backend is the sole writer. CLI read-only commands (`list`, `logs`,
`validate`) open the DB in read-only mode with WAL, so they work even
while the backend is running.

### PID files

Old PID files at `workspace/data/agentmd.pid` are ignored. The new
backend stores its PID at `~/.local/state/agentmd/backend.pid`.

### Environment variable

Set `AGENTMD_NO_AUTOSPAWN=1` to prevent auto-starting the backend in
CI/container environments.
