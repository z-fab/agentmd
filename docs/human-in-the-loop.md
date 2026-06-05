# Human-in-the-Loop

Agentmd supports pausing an execution mid-run to ask the user a question, then resuming from exactly where it left off — even after a backend restart. This is called a **HILT interaction** (Human-In-The-Loop).

## Concept

When an agent reaches a point that requires human input, the execution **pauses** (status `waiting`). It stays paused until you respond. When a response arrives, the execution resumes from the checkpoint where it stopped — the full conversation state is preserved.

Key properties:

- **Restart-safe**: paused executions survive a backend restart. The LangGraph checkpointer stores state on disk; responding later simply re-loads the checkpoint and continues.
- **Non-blocking**: waiting for a response does not hold up other agents or the scheduler. A paused execution is fully suspended.
- **Non-fatal denial**: if you deny a confirmation (or a timeout fires), the guarded tool returns `"Action denied by user"` as its result and the agent continues. It is not a hard abort.

---

## The Four Ways a Request Is Raised

### 1. Default-confirm built-in tools

`file_delete` and `file_write` ask for confirmation before running. This is the default behavior — no agent configuration required. The global list of default-guarded tools is configurable in `config.yaml` (see [Global defaults](#global-defaults)).

```
▶ Running cleaner  google/gemini-2.5-flash

17:03:12 cleaner 🔧 file_delete → {"path": "output/old-report.txt"}
? Confirm file_delete {"path": "output/old-report.txt"} [y/N]:
```

### 2. Agent config `confirm:` and `auto_approve:`

Use `confirm:` in the agent frontmatter to guard additional tools by name — built-in, custom, or MCP tools. Use `auto_approve:` to remove tools from the confirm set (including defaults).

```yaml
confirm: [file_edit]          # also require confirmation for file_edit
auto_approve: [file_write]    # skip the file_write confirmation
```

The effective confirm set is: **(global defaults ∪ `confirm`) − `auto_approve`**

To disable confirmation for all guarded tools at once, set `auto_approve: "*"` (or `"all"`):

```yaml
auto_approve: "*"   # never ask for confirmation for any guarded tool
```

> **Note:** `auto_approve` only affects guarded-tool confirmation. It does not suppress `ask_user` calls or SDK `request_*` calls made directly by the agent or a custom tool.

### 3. The `ask_user` built-in tool

The agent itself can request input by calling `ask_user`. This is always available and is not affected by `auto_approve`.

```
17:05:44 cleaner 🔧 ask_user → {"question": "Which environment should I target?", "kind": "choice", "options": ["staging", "production"]}
? Which environment should I target?
  1. staging
  2. production
Choice:
```

The agent uses `ask_user` for **dynamic** questions it can only formulate at runtime — for example, "I found 3 matching files, which one should I delete?"

### 4. SDK primitives for custom tools

Custom tools can raise any of the three request kinds by calling primitives from `agent_md.sdk`. See [SDK primitives](#sdk-primitives) below.

---

## Request Kinds

| Kind | Description | CLI appearance |
|------|-------------|----------------|
| `confirm` | Yes / no approval, with optional reason | `[y/N]:` prompt |
| `input` | Free-text entry | Open text prompt |
| `choice` | Select from a list of options | Numbered menu |

---

## Configuration

### Frontmatter fields

Add these to any agent's YAML frontmatter:

#### `confirm`

| Property | Value |
|----------|-------|
| **Type** | string[] |
| **Required** | No |
| **Default** | `[]` |

Additional tool names to guard with a confirmation step, on top of the global defaults. Accepts built-in tool names, custom tool names, and MCP tool names.

```yaml
confirm: [file_edit, send_email]
```

#### `auto_approve`

| Property | Value |
|----------|-------|
| **Type** | string[] or `"*"` |
| **Required** | No |
| **Default** | `[]` |

Tool names to remove from the effective confirm set. Cancels the default guard for those tools. Use `"*"` (or `"all"`) to clear the entire confirm set for this agent.

```yaml
auto_approve: [file_write]          # skip the file_write default confirmation
auto_approve: "*"                   # never confirm any guarded tool
```

#### `on_pending`

| Property | Value |
|----------|-------|
| **Type** | string |
| **Allowed values** | `skip`, `parallel` |
| **Default** | `skip` |

Controls whether a new execution can start while a previous one is `waiting`:

- `skip` (default): the scheduler and file-watcher will not trigger a new run while an execution for this agent is paused. The skipped trigger is logged.
- `parallel`: allows multiple concurrent waiting sessions (each paused run is independent — isolated checkpoint threads).

```yaml
on_pending: parallel
```

#### `confirm_timeout`

| Property | Value |
|----------|-------|
| **Type** | string |
| **Accepted values** | `30s`, `5m`, `2h`, `1d`, … or `none` |
| **Default** | `none` (wait indefinitely) |

How long to wait for a response before auto-denying. On expiry, the pending request is treated as denied: the guarded tool returns `"Action denied by user (timeout)"` and the agent continues.

```yaml
confirm_timeout: 1h    # auto-deny if unanswered for 1 hour
confirm_timeout: none  # wait forever (default)
```

Duration grammar: a number followed by `s` (seconds), `m` (minutes), `h` (hours), or `d` (days).

### Complete frontmatter example

```yaml
---
name: Cleaner
model: { provider: google, name: gemini-2.5-flash }
confirm: [file_edit]          # also guard file_edit (file_delete/file_write are guarded by default)
auto_approve: [file_write]    # never ask for file_write
on_pending: skip              # don't fire again while one session waits
confirm_timeout: 1h           # auto-deny if unanswered for 1h (default: none = wait forever)
---
You clean up files. Always ask the user before deleting anything important.
```

### Global defaults

These keys under `defaults:` in `config.yaml` apply to all agents and can be overridden per agent in frontmatter:

```yaml
# config.yaml
defaults:
  confirm_tools: [file_delete, file_write]  # built-in tools guarded by default (default: [file_delete, file_write])
  on_pending: skip                          # default concurrency mode (default: skip)
  confirm_timeout: none                     # default timeout (default: none)
  checkpoint_retention_days: 30             # see Checkpoint storage below
```

`confirm_tools` defines the baseline confirm set before any per-agent `confirm:` or `auto_approve:` adjustments.

---

## CLI Usage

### During `agentmd run` and `agentmd chat`

HILT works in **both** `agentmd run` (one-shot) and `agentmd chat` (interactive sessions). When a guarded tool fires or `ask_user` is called, Agentmd pauses the stream and prompts inline — in a chat session the prompt appears mid-turn, and the agent continues the turn once you answer:

```
▶ Running cleaner  google/gemini-2.5-flash

17:03:12 cleaner 🔧 file_delete → {"path": "output/stale.log"}
? Confirm file_delete {"path": "output/stale.log"} [y/N]: y

17:03:15 cleaner 📎 file_delete ← File deleted: output/stale.log
17:03:16 cleaner ✅ Done.
```

If you are not watching the terminal (for example, the agent was started in the background or triggered by a scheduler), the execution enters `waiting` state and you can respond later.

### `agentmd pending`

List all executions currently waiting for a response:

```bash
agentmd pending
```

Output:

```
 #   Agent      Question
 ──────────────────────────────────────────────────────────────────────
 42  cleaner    Confirm file_delete {"path": "output/stale.log"}
 51  reporter   Enter the report title:
```

### `agentmd respond <id>`

Respond to a waiting execution interactively or with flags:

```bash
# Interactive (prompts for the response)
agentmd respond 42

# Approve a confirmation
agentmd respond 42 --yes

# Deny a confirmation with an optional reason
agentmd respond 42 --no --reason "file is still needed"

# Provide text for an input request
agentmd respond 51 --text "Monthly Summary"

# Select a choice
agentmd respond 55 --choice staging
```

After a successful response, the execution resumes automatically.

---

## Restart Behavior

Paused executions survive a backend restart:

1. When `POST .../respond` arrives and there is no live resume task (e.g., after a restart), the endpoint re-loads the agent config from the registry, re-attaches to the on-disk checkpoint, and spawns a fresh resume task.
2. The resume picks up at the exact node where the interrupt fired — no messages are lost.

The `history` setting and the always-on checkpointer are independent:
- The checkpointer is **always active** regardless of `history`. It is the durability substrate for HILT.
- `history` controls only how much prior context is fed to the LLM at the **start** of a new, non-HILT run (see [Memory](memory.md)).

### Limitations

**`confirm_timeout` across restarts.** The timeout countdown runs in memory. If the backend restarts while an execution is waiting for a response, the timeout task is not re-armed — the execution will wait indefinitely until it is answered or cancelled. This only affects agents that set an explicit `confirm_timeout`; the default (`none`) is unaffected.

**Limits are per-resume, not cumulative.** `max_cost_usd`, `max_execution_tokens`, and `max_tool_calls` are enforced independently within each `run()` and each `resume()` call. They are not accumulated across the full pause/resume history of a single execution. For example, an agent with `max_tool_calls: 5` may call up to 5 tools before the pause *and* up to 5 more after each resume. The LangGraph recursion limit still caps tool calls within a single resume drive.

---

## SDK Primitives

Custom tools can raise HILT requests using three functions from `agent_md.sdk`:

```python
request_confirmation(message: str, *, tool_name: str | None = None, tool_args: dict | None = None) -> bool
request_input(message: str) -> str
request_choice(message: str, options: list[str], *, multi: bool = False) -> list[str] | str
```

All three are thin wrappers over `langgraph.types.interrupt()` — they pause the execution and return the user's response once it arrives.

### `request_confirmation`

Ask yes/no before proceeding. Returns `True` if approved, `False` if denied.

```python
from langchain_core.tools import tool
from agent_md.sdk import request_confirmation, request_choice


@tool
def cleanup(folder: str) -> str:
    """Delete temp files in a folder."""
    if not request_confirmation(f"Clean {folder}?", tool_name="cleanup", tool_args={"folder": folder}):
        return "User declined."
    # ... do the cleanup ...
    return "Cleaned."
```

### `request_input`

Ask for free text. Returns the string the user typed.

```python
from langchain_core.tools import tool
from agent_md.sdk import request_input

@tool
def create_report(topic: str) -> str:
    """Generate a report."""
    title = request_input(f"Enter a title for the '{topic}' report:")
    # ... generate with title ...
    return f"Report '{title}' created."
```

### `request_choice`

Ask the user to pick from a list. Returns the selected option (or a list if `multi=True`).

```python
from langchain_core.tools import tool
from agent_md.sdk import request_choice

@tool
def deploy(artifact: str) -> str:
    """Deploy an artifact to an environment."""
    env = request_choice("Deploy to which environment?", ["staging", "production"])
    # ... deploy to env ...
    return f"Deployed {artifact} to {env}."
```

> **Note:** SDK primitives are always available to custom tools and are not affected by `auto_approve`. They are distinct from the guarded-tool mechanism — use them for dynamic, in-code decisions that cannot be expressed as a static "this tool needs approval".

---

## Checkpoint Storage

The LangGraph checkpointer is **always on** and stores one checkpoint thread per execution in `agentmd_checkpoints.db`.

### Automatic cleanup

A sweep runs on startup (alongside other maintenance tasks). It removes old checkpoint threads, subject to these retention rules:

- The **latest execution per agent** is always kept (needed to seed `history` on the next run).
- Any **`waiting` execution** is always kept (needed to resume the paused run).
- All other finished threads older than `defaults.checkpoint_retention_days` (default: 30 days) are eligible for removal.

Configure the retention window in `config.yaml`:

```yaml
defaults:
  checkpoint_retention_days: 30   # 0 or none to disable automatic cleanup
```

### `agentmd checkpoint` command

Inspect and manage the checkpoint database manually:

```bash
# Show size and thread count, grouped per agent
agentmd checkpoint --stats

# Delete eligible checkpoint threads (respects the keep-set: latest + waiting)
agentmd checkpoint --purge

# Delete eligible threads for a specific agent only
agentmd checkpoint --purge --agent cleaner

# Delete ALL threads, ignoring the keep-set (also removes latest/waiting)
agentmd checkpoint --purge --force
```

`--purge` without `--force` never removes the latest-per-agent thread or any `waiting` thread, so it is safe to run without disrupting history seeding or a pending resume. Use `--force` only when you want a complete wipe.

---

## Related Documentation

- [Agent Configuration](agent-configuration.md) — full frontmatter reference including `confirm`, `auto_approve`, `on_pending`, `confirm_timeout`
- [Custom Tools](tools/custom-tools.md) — building custom tools and using the SDK
- [CLI Reference](cli-reference.md) — full command reference
- [Memory](memory.md) — session history and how the checkpointer relates to `history`
