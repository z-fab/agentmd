# Paths & Security

Complete guide to path configuration and file access control in Agent.md.

## Overview

Agent.md uses a two-level path system:

1. **Global paths (runtime)** — Configure where agents and databases live
2. **Agent paths (frontmatter)** — Declare what each agent can access

**Resolution order:** CLI → ENV → Defaults

## Workspace Structure

Default layout:

```
~/.config/agentmd/
└── config.yaml         # Application settings (auto-created on first run)

~/agentmd/
├── .env                # API keys (secrets)
├── agents/
│   ├── agent1.md
│   ├── agent2.md
│   └── mcp-servers.json (optional)
└── data/
    └── agentmd.db
```

## Global Paths (Runtime Level)

Four paths can be configured:

| Path | Description | Default |
|------|-------------|---------|
| `workspace` | Root directory for agents | `~/agentmd` |
| `agents_dir` | Where `.md` files live | `{workspace}/agents` |
| `db_path` | SQLite execution history | `{workspace}/data/agentmd.db` |
| `mcp_config` | MCP servers file | `{agents_dir}/mcp-servers.json` |

### Configuration File

Runtime settings live in `~/.config/agentmd/config.yaml` (XDG standard). This file is **auto-created with defaults on first run** — no manual setup needed.

```yaml
# ~/.config/agentmd/config.yaml
workspace: ~/agentmd
agents_dir: agents          # relative to workspace

defaults:
  provider: google
  model: gemini-2.5-flash
```

### CLI Arguments (Highest Priority)

```bash
agentmd start \
  --workspace /path/to/workspace \
  --agents-dir /path/to/agents \
  --db-path /path/to/db.db

# Available for: start, run, list
```

#### Defaults (Lowest Priority)

```
workspace     → ~/agentmd
agents_dir    → {workspace}/agents
db_path       → {workspace}/data/agentmd.db
mcp_config    → {agents_dir}/mcp-servers.json
```

### Resolution Examples

**Example 1: All defaults**
```
config     → ~/.config/agentmd/config.yaml
workspace  → ~/agentmd
agents_dir → ~/agentmd/agents
db_path    → ~/agentmd/data/agentmd.db
```

**Example 2: Custom workspace via config.yaml**
```yaml
workspace: /home/alice/my-agents
```
```
workspace  → /home/alice/my-agents
agents_dir → /home/alice/my-agents/agents
db_path    → /home/alice/my-agents/data/agentmd.db
```

**Example 3: Config + CLI (CLI wins)**
```yaml
# config.yaml
workspace: /home/alice/agents
```
```bash
agentmd start --db-path /var/lib/agentmd.db
```
```
workspace  → /home/alice/agents           (config.yaml)
db_path    → /var/lib/agentmd.db          (CLI - highest)
```

## Agent Paths (Frontmatter Level)

Each agent declares allowed paths in frontmatter. The `paths` field is a **dict of named aliases** that controls which directories and files the agent can access for reading, writing, and listing.

### Configuration

```yaml
paths:
  data: ./data
  output: ./output
```

**Defaults:** `[workspace_root]` (entire workspace)

**Behavior:**
- Each key is an alias name, each value is the path
- Directory: access all files within (recursive)
- File: access specific file only
- Relative paths resolve from `workspace_root` (for both reads and writes)
- Absolute paths used as-is
- `~` expanded to home directory
- All file tools accept `{alias}` syntax: `file_read("{data}/input.csv")`

**Resolution order:** alias → absolute → relative

**Examples:**

```yaml
# Access entire workspace (default, omit field)

# Single directory
paths:
  data: ./data

# Multiple locations
paths:
  data: ./data
  logs: ./logs
  app_logs: /var/log/app
  output: ./output

# Specific files
paths:
  settings: ./config/settings.json
  input: ./data/input.csv
  result: ./output/result.txt
```

**Path resolution example:**

```yaml
paths:
  reports: ./reports
  data: ./data
```

When agent calls `file_write("{reports}/summary.txt", content)`:
- `{reports}` resolves to workspace root + `reports/`
- Final path: `workspace_root/reports/summary.txt`

## Security Restrictions

File access is validated before every operation.

### Forbidden Paths

**Cannot access:**

1. **Agents directory** (`workspace/agents`)
   - Prevents reading or modifying agent code
   - Error: `"Access denied: cannot access agents directory"`

2. **`.env` files** (any `.*env*`)
   - Prevents credential leakage or modification
   - Error: `"Access denied: cannot access .env files"`

3. **`.db` files** (write only)
   - Prevents database corruption
   - Error: `"Access denied: cannot write to .db files"`

### Watch Triggers

Agents with `watch` triggers automatically gain access to watched paths:

```yaml
trigger:
  type: watch
  paths:
    - ./data/input.txt

# Implicit access to ./data/input.txt
```

Explicit `paths` is combined with watch paths:

```yaml
trigger:
  type: watch
  paths:
    - ./data/input.txt
paths:
  config: ./config
  output: ./output
# Can access ./data/input.txt, ./config, AND ./output
```

## Common Patterns

### Minimal Access

```yaml
paths:
  data: ./data
# Can only access ./data via {data}
```

### Isolated Agent

```yaml
paths:
  input: ./data/input
  output: ./output/agent1
```

### Multi-Source Agent

```yaml
paths:
  data: ./data
  logs: ./logs
  app_logs: /var/log/app
  reports: ./reports
```

### Specific File Access

```yaml
paths:
  settings: ./config/settings.json
  input: ./data/input.csv
  result: ./output/result.txt
```

## Setup Examples

### Development

Use defaults (zero-config):

```bash
agentmd start
```

**Structure:**
```
~/.config/agentmd/config.yaml
~/agentmd/
├── .env
├── agents/
└── data/agentmd.db
```

### Production

Custom workspace via config:

```yaml
# ~/.config/agentmd/config.yaml
workspace: /srv/agentmd
```

**Structure:**
```
/srv/agentmd/agents/
/srv/agentmd/data/agentmd.db
```

### Multi-Workspace

```bash
agentmd start --workspace ~/projects/project1
agentmd start --workspace ~/projects/project2
```

### Docker

```bash
docker run -v ./agentmd:/root/agentmd agentmd start
```

## Best Practices

### Principle of Least Privilege

Grant minimum necessary access:

```yaml
# ✅ Good: specific paths
paths:
  input: ./data/input
  results: ./output/results

# ❌ Avoid: overly broad
paths:
  root: /
```

### Separate Concerns

Use different directories per agent:

```yaml
# Agent 1
paths:
  data: ./data/agent1
  output: ./output/agent1

# Agent 2
paths:
  data: ./data/agent2
  output: ./output/agent2
```

### Use Relative Paths

Prefer relative for portability:

```yaml
# ✅ Portable
paths:
  data: ./data
  output: ./output

# ⚠️ Machine-specific
paths:
  data: /Users/alice/data
```

### Keep Workspace Self-Contained

```
workspace/
├── agents/
├── data/
└── config/
```

## Troubleshooting

### "No agents found"

**Cause:** Wrong `agents_dir`

**Fix:** Check path:
```bash
ls -la ~/agentmd/agents
agentmd start --agents-dir /correct/path
```

### "Access denied: outside allowed paths"

**Cause:** Agent tried to access an unlisted path

**Fix:** Add to `paths`:
```yaml
paths:
  data: ./data
  logs: ./logs         # Add missing
  output: ./output
  cache: /tmp/cache    # Add missing
```

### "Access denied: cannot read from agents directory"

**Cause:** Tried to read `workspace/agents`

**Fix:** Move files to readable location:
```bash
mv workspace/agents/file.txt workspace/data/
```

### "Database error"

**Cause:** `db_path` directory missing

**Fix:** Create parent or use a custom path:
```bash
mkdir -p ~/agentmd/data
agentmd start --db-path ~/agentmd/data/agentmd.db
```

### "Permission denied"

**Cause:** No write access to paths

**Fix:** Use accessible paths:
```bash
agentmd start --workspace ~/agentmd
```

## Related Documentation

- [Agent Configuration](agent-configuration.md) - All YAML fields and configuration
- [Triggers](triggers.md) - Watch and schedule triggers
- [Quick Start](quick-start.md) - Setup and installation
