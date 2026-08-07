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

## What stays the same

- Agent `.md` layout (YAML frontmatter + Markdown body)
- Triggers, tools, skills, MCP, HILT
- Workspaces where every `name:` already equals the filename stem need **no action**

## Upgrade procedure

### 1. Back up

```bash
cp -a ~/agentmd/agents /tmp/agents-backup
cp ~/.local/state/agentmd/agentmd.db /tmp/agentmd.db.bak   # or your config.yaml db_path
```

### 2. Upgrade Agentmd

Install 0.16.x (pip/uv as you normally do). Do **not** skip the migrate step if any agent has `name:` ≠ filename stem, or if history/memory were keyed by the old display name.

### 3. Dry-run first

```bash
agentmd migrate --dry-run
```

Review the report. It plans:

- `UPDATE executions SET agent_id = <stem> WHERE agent_id = <old display name>`
- Rename `{display}.memory.md` → `{stem}.memory.md` when they differ
- **Warnings** for `agents:` allowlist entries that still use display names (those `.md` files are **never** edited automatically)
- **Errors** when two agents share the same display name (rekey would be ambiguous — resolve by making display names unique or aligning them with stems, then re-run)

### 4. Apply

```bash
agentmd migrate
```

Safe to re-run: a second pass should report nothing left to change.

### 5. Fix allowlists by hand

If migrate warned about `agents:` entries, edit those agent files so the allowlist lists **filename stems**, then reload:

```bash
# example: was "Research Bot", file is pesquisadores.md → id pesquisadores
agents:
  - pesquisadores
```

### 6. Verify

```bash
agentmd list          # Id + Display Name columns
agentmd validate
agentmd run <id>      # use the stem, not the old display name
```

API: `GET /agents` returns `id` and `display_name`. `GET /agents/{display_name}` no longer resolves when display name ≠ id.

## Renaming an agent after upgrade

```bash
mv agents/old-id.md agents/new-id.md
```

Hot-reload unschedules `old-id` and registers `new-id` without a backend restart.

**History and memory do not follow a later `mv`.** Executions stay under the previous `agent_id`; `{old-id}.memory.md` is left behind. To re-key, rename/copy memory yourself and update DB rows, or reuse `agentmd migrate` patterns manually. A dedicated `--rename old new` helper is not part of 0.16.

Editing only `name:` in frontmatter changes the **label** (CLI, `display_name`, banners). Identity, schedule job id (`agent_{id}`), memory path, and execution history stay on the stem.

## SSE / API client notes

| Field | Meaning in 0.16 |
|-------|-----------------|
| `agent_id` | Canonical stem |
| `display_name` | Human label (`name:` or id) |
| `agent_name` | Same as `agent_id` (breaking if you treated it as the label) |

Update clients that filtered or displayed `agent_name` as a pretty title to use `display_name` instead.
