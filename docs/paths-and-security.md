# Paths & Security

Complete guide to path configuration and file access control in Agent.md.

## Overview

Agent.md uses a two-level path system:

1. **Global paths (runtime)** — Configure where agents, outputs, and databases live
2. **Agent paths (frontmatter)** — Declare what each agent can access

**Resolution order:** CLI → ENV → Defaults

## Workspace Structure

Default layout with both levels:

```
workspace/
├── agents/
│   ├── agent1.md
│   ├── agent2.md
│   └── mcp-servers.json (optional)
└── output/
    └── results.txt

data/
└── agentmd.db
```

## Global Paths (Runtime Level)

Four paths can be configured at startup:

| Path | Description | Default |
|------|-------------|---------|
| `workspace` | Root directory for agents and data | `~/agentmd` |
| `agents_dir` | Where `.md` files live | `{workspace}/agents` |
| `db_path` | SQLite execution history | `{workspace}/data/agentmd.db` |
| `mcp_config` | MCP servers file | `{agents_dir}/mcp-servers.json` |

**Note:** There is no global `output_dir`. Agents define their own writable paths via the `paths` field in frontmatter.

### Configuration Methods

#### CLI Arguments (Highest Priority)

```bash
agentmd start \
  --workspace /path/to/workspace \
  --agents-dir /path/to/agents \
  --db-path /path/to/db.db

# Available for: start, run, list
```

#### Defaults (Lowest Priority)

These defaults are automatically created in `~/.config/agentmd/config.yaml` on first run:

```
workspace     → ~/agentmd
agents_dir    → agents (relative to workspace)
db_path       → data/agentmd.db (relative to workspace)
mcp_config    → agents/mcp-servers.json (relative to workspace)
```

### Resolution Examples

**Example 1: All defaults (auto-created config)**
```
Config file: ~/.config/agentmd/config.yaml
workspace  → ~/agentmd
agents_dir → ~/agentmd/agents
db_path    → ~/agentmd/data/agentmd.db
```

**Example 2: Custom workspace in config**
Edit `~/.config/agentmd/config.yaml`:
```yaml
workspace: /home/alice/my-agents
```
Result:
```
workspace  → /home/alice/my-agents
agents_dir → /home/alice/my-agents/agents
db_path    → /home/alice/my-agents/data/agentmd.db
```

**Example 3: Override via CLI**
```bash
agentmd start --workspace /data/agents --db-path /var/lib/agentmd.db
```
```
workspace  → /data/agents               (CLI)
agents_dir → /data/agents/agents        (derived from workspace)
db_path    → /var/lib/agentmd.db        (CLI - highest)
```

## Agent Paths (Frontmatter Level)

Each agent declares allowed paths in frontmatter. The `paths` field controls which directories and files the agent can access for reading, writing, and listing.

### Configuration

```yaml
paths:
  - ./data
  - ./output
```

**Defaults:** `[workspace_root]` (entire workspace)

**Behavior:**
- Directory: access all files within (recursive)
- File: access specific file only
- Relative paths resolve from `workspace_root`
- Absolute paths used as-is
- `~` expanded to home directory
- First directory in array is the default write location for `file_write`
- If no `paths` field defined: agent can access entire workspace

**Examples:**

```yaml
# Access entire workspace (default, omit field)

# Single directory
paths: ./data

# Multiple locations
paths:
  - ./data
  - ./logs
  - /var/log/app
  - ./output

# Specific files
paths:
  - ./config/settings.json
  - ./data/input.csv
  - ./output/result.txt
```

**Path resolution example:**

```yaml
paths:
  - ./reports
  - ./data
```

When agent writes `summary.txt`:
- Resolves to: `./reports/summary.txt` (first path is default write location)

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
  - ./config
  - ./output
# Can access ./data/input.txt, ./config, AND ./output
```

## Common Patterns

### Minimal Access

```yaml
paths: ./data
# Can only access ./data; writes default to ./data
```

### Isolated Agent

```yaml
paths:
  - ./data/input
  - ./results/agent1
# Reads from data/input, writes to results/agent1 (first writable path)
```

### Multi-Source Agent

```yaml
paths:
  - ./data
  - ./logs
  - /var/log/app
  - ./reports
```

### Specific File Access

```yaml
paths:
  - ./config/settings.json
  - ./data/input.csv
  - ./output/result.txt
```

## Setup Examples

### Development

Use defaults:

```bash
agentmd start
```

**Structure:**
```
workspace/
├── agents/
└── output/
data/
└── agentmd.db
```

### Production

Separate data directories:

```env
AGENTMD_WORKSPACE=/srv/agentmd/workspace
AGENTMD_OUTPUT_DIR=/var/lib/agentmd/output
AGENTMD_DB_PATH=/var/lib/agentmd/db.db
```

**Structure:**
```
/srv/agentmd/workspace/agents/
/var/lib/agentmd/output/
/var/lib/agentmd/db.db
```

### Multi-Workspace

```bash
agentmd start --workspace ~/projects/project1/agents
agentmd start --workspace ~/projects/project2/agents
```

### Shared Output

```bash
agentmd start --workspace /team/workspace1 --output-dir /shared/output
agentmd start --workspace /team/workspace2 --output-dir /shared/output
```

### Docker

```bash
docker run -v ./workspace:/workspace -v ./data:/data agentmd start
```

## Best Practices

### Principle of Least Privilege

Grant minimum necessary access:

```yaml
# ✅ Good: specific paths
paths:
  - ./data/input
  - ./output/results

# ❌ Avoid: overly broad
paths: /
```

### Separate Concerns

Use different directories per agent:

```yaml
# Agent 1
paths:
  - ./data/agent1
  - ./output/agent1

# Agent 2
paths:
  - ./data/agent2
  - ./output/agent2
```

### Use Relative Paths

Prefer relative for portability:

```yaml
# ✅ Portable
paths:
  - ./data
  - ./output

# ⚠️ Machine-specific
paths: /Users/alice/data
```

### Keep Workspace Self-Contained

```
workspace/
├── agents/
├── output/
└── config/
```

## Troubleshooting

### "No agents found"

**Cause:** Wrong `agents_dir`

**Fix:** Check path:
```bash
ls -la workspace/agents
agentmd start --agents-dir /correct/path
```

### "Access denied: outside allowed paths"

**Cause:** Agent tried to access an unlisted path

**Fix:** Add to `paths`:
```yaml
paths:
  - ./data
  - ./logs    # Add missing
  - ./output
  - /tmp/cache  # Add missing
```

### "Access denied: cannot read from agents directory"

**Cause:** Tried to read `workspace/agents`

**Fix:** Move files to readable location:
```bash
mv workspace/agents/file.txt workspace/data/
```

### "Database error"

**Cause:** `db_path` directory missing

**Fix:** Create parent:
```bash
mkdir -p data
agentmd start --db-path ./data/agentmd.db
```

### "Permission denied"

**Cause:** No write access to paths

**Fix:** Use accessible paths:
```bash
agentmd start \
  --workspace ~/agentmd/workspace \
  --output-dir ~/agentmd/output
```

## Related Documentation

- [Agent Configuration](agent-configuration.md) - All YAML fields and configuration
- [Triggers](triggers.md) - Watch and schedule triggers
- [Quick Start](quick-start.md) - Setup and installation
