# Migration Guide: v0.15.x → v0.16.0

## Breaking change: filename stem is the agent id

Agent identity is now the **filename stem**, not the frontmatter `name:` field.

| Before (≤0.15) | After (0.16) |
|----------------|--------------|
| `name:` was the canonical key | Stem of `agents/pesquisador.md` → id `pesquisador` |
| Filename was irrelevant to identity | Renaming the **file** changes identity |
| Memory at `{name}.memory.md` | Memory at `{id}.memory.md` |
| Routes `/agents/{name}` | Routes `/agents/{id}` (URL-encode spaces) |
| Allowlist `agents:` used display names | Allowlist `agents:` must list **ids** (stems) |
| SSE `agent_name` was the display name | SSE `agent_name` mirrors **id**; human label is `display_name` |

`name:` is now an **optional display label**. If omitted, it defaults to the id. Declaring `id:` in frontmatter is **rejected**.

**There is no migration command.** 0.16 does not rewrite your data. Existing execution history and memory files keyed by an old display name are simply not found under the new id — you decide whether to discard them or re-key them by hand.

## Do you need to do anything?

Only if some agent's `name:` differs from its filename. Check before upgrading:

```bash
agentmd list          # on 0.15.x: the Name column shows `name:`
ls agents/            # compare against the filenames
```

- **`name:` equals the stem, or is absent** → nothing to do. History and memory keep working.
- **`name:` differs from the stem** → that agent's history and memory become orphaned. Follow the steps below.

## Upgrade procedure

### 1. Stop the backend

```bash
agentmd stop
```

**Do not skip this.** A backend started before the upgrade keeps the *old* registry in memory, keyed by display name. If it is still running you get:

- `agentmd run <id>` → `Agent '<id>' not found.` — the new CLI asks the old backend for a stem it has never heard of.
- Scheduled agents keep writing `executions.agent_id` under the **old display name**.

`agentmd status` shows the running version; if it is 0.15.x, stop it before going further.

### 2. Back up

```bash
cp -a ~/agentmd/agents /tmp/agents-backup
cp ~/.local/state/agentmd/agentmd.db /tmp/agentmd.db.bak   # or your config.yaml db_path
```

`agentmd info` prints the database path in use.

### 3. Deal with orphaned history — discard or re-key

**Option A — discard (simplest).** Execution history is a log, not content. Delete the database and let 0.16 recreate it:

```bash
rm ~/.local/state/agentmd/agentmd.db
rm ~/.local/state/agentmd/agentmd_checkpoints.db   # conversation checkpoints
```

You lose past run records and conversation continuity. Agent definitions, memory files, tools and skills are untouched.

**Option B — re-key (keep history).** Rewrite the key by hand, one agent at a time:

```bash
sqlite3 ~/.local/state/agentmd/agentmd.db \
  "UPDATE executions SET agent_id = 'pesquisador' WHERE agent_id = 'Research Bot';"
```

Verify no id collides with another agent's display name before running this. If two agents shared the same `name:`, their rows are indistinguishable — pick an owner or discard.

### 4. Rename memory files

**Deleting the database does not cover this.** Memory lives on disk, next to your agents:

```bash
mv "agents/Research Bot.memory.md" agents/pesquisador.memory.md
```

Skip if the agent had no memory file. Left unrenamed, the agent silently starts with empty memory and the old file lingers.

### 5. Fix allowlists by hand

Agents that delegate via `agents:` must list **filename stems**:

```yaml
# was "Research Bot", file is pesquisador.md → id pesquisador
agents:
  - pesquisador
```

Delegation to an unknown id fails at call time, not at load time — so this is worth checking rather than discovering later.

### 6. Verify

```bash
agentmd list          # Id + Display Name columns
agentmd validate
agentmd run <id>      # use the stem, not the old display name
```

`agentmd list` is a good smoke test: an agent whose history is still filed under an old key shows **Last Run: never**.

If `agentmd run <id>` reports the agent as not found while `agentmd validate <id>` succeeds, a stale backend is serving the old registry — go back to step 1.

## What stays the same

- Agent `.md` layout (YAML frontmatter + Markdown body)
- Triggers, tools, skills, MCP, HILT
- Workspaces where every `name:` already equals the filename stem need **no action**

## Renaming an agent after upgrade

```bash
mv agents/old-id.md agents/new-id.md
```

Hot-reload unschedules `old-id` and registers `new-id` without a backend restart.

**History and memory do not follow a `mv`.** Executions stay under the previous `agent_id` and `{old-id}.memory.md` is left behind — same manual steps as above. A dedicated `--rename old new` helper is not part of 0.16.

Editing only `name:` in frontmatter changes the **label** (CLI, `display_name`, banners). Identity, schedule job id (`agent_{id}`), memory path, and execution history stay on the stem.

## SSE / API client notes

| Field | Meaning in 0.16 |
|-------|-----------------|
| `agent_id` | Canonical stem |
| `display_name` | Human label (`name:` or id) |
| `agent_name` | Same as `agent_id` (breaking if you treated it as the label) |

Update clients that filtered or displayed `agent_name` as a pretty title to use `display_name` instead.
