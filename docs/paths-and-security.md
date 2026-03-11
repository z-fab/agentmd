# Paths & Security

Complete guide to path configuration and file access control in Agent.md.

## Overview

Agent.md uses a two-level path system:

1. **Global paths (runtime)** — Configure where agents, outputs, and databases live
2. **Agent paths (frontmatter)** — Declare what each agent can read/write

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

Five paths can be configured at startup:

| Path | Description | Default |
|------|-------------|---------|
| `workspace` | Root directory for agents | `./workspace` |
| `agents_dir` | Where `.md` files live | `{workspace}/agents` |
| `output_dir` | Default output for all agents | `{workspace}/output` |
| `db_path` | SQLite execution history | `./data/agentmd.db` |
| `mcp_config` | MCP servers file | `{agents_dir}/mcp-servers.json` |

### Configuration Methods

#### CLI Arguments (Highest Priority)

```bash
agentmd start \
  --workspace /path/to/workspace \
  --agents-dir /path/to/agents \
  --output-dir /path/to/output \
  --db-path /path/to/db.db

# Available for: start, run, list
```

#### Environment Variables

```bash
export AGENTMD_WORKSPACE=/path/to/workspace
export AGENTMD_AGENTS_DIR=/path/to/agents
export AGENTMD_OUTPUT_DIR=/path/to/output
export AGENTMD_DB_PATH=/path/to/db.db
export AGENTMD_MCP_CONFIG=/path/to/mcp-servers.json
```

Or in `.env`:

```env
AGENTMD_WORKSPACE=/path/to/workspace
AGENTMD_AGENTS_DIR=/path/to/agents
AGENTMD_OUTPUT_DIR=/path/to/output
AGENTMD_DB_PATH=/path/to/db.db
AGENTMD_MCP_CONFIG=/path/to/mcp-servers.json
```

#### Defaults (Lowest Priority)

```
workspace     → ./workspace
agents_dir    → {workspace}/agents
output_dir    → {workspace}/output
db_path       → ./data/agentmd.db
mcp_config    → {agents_dir}/mcp-servers.json
```

### Resolution Examples

**Example 1: All defaults**
```
workspace  → ./workspace
agents_dir → ./workspace/agents
output_dir → ./workspace/output
db_path    → ./data/agentmd.db
```

**Example 2: Custom workspace via ENV**
```env
AGENTMD_WORKSPACE=/home/alice/my-agents
```
```
workspace  → /home/alice/my-agents
agents_dir → /home/alice/my-agents/agents
output_dir → /home/alice/my-agents/output
db_path    → ./data/agentmd.db
```

**Example 3: Mixed CLI + ENV (CLI wins)**
```env
AGENTMD_WORKSPACE=/home/alice/agents
AGENTMD_OUTPUT_DIR=/mnt/storage/output
```
```bash
agentmd start --db-path /var/lib/agentmd.db
```
```
workspace  → /home/alice/agents           (ENV)
output_dir → /mnt/storage/output          (ENV)
db_path    → /var/lib/agentmd.db          (CLI - highest)
```

## Agent Paths (Frontmatter Level)

Each agent declares allowed read/write paths in frontmatter.

### Read Paths

**Configuration:**

```yaml
read:
  - ./data
  - ./logs
```

**Defaults:** `[workspace_root]` (entire workspace)

**Behavior:**
- Directory: access all files within (recursive)
- File: access specific file only
- Relative paths resolve from `workspace_root`
- Absolute paths used as-is
- `~` expanded to home directory

**Examples:**

```yaml
# Read entire workspace (default, omit field)

# Read specific directory
read: ./data

# Read multiple locations
read:
  - ./data
  - ./logs
  - /var/log/app

# Read specific files
read:
  - ./config/settings.json
  - ./data/input.csv
```

### Write Paths

**Configuration:**

```yaml
write:
  - ./output
  - /tmp/cache
```

**Defaults:** `[output_dir]` (default output directory)

**Behavior:**
- Directory: write any file within (recursive)
- File: write specific file only
- Relative paths resolve from **first write directory** (default write dir)
- Absolute paths used as-is
- Falls back to global `output_dir` if no write field

**Examples:**

```yaml
# Write to default output (default, omit field)

# Write to specific directory
write: ./output

# Write to multiple locations
write:
  - ./reports
  - ./output

# Write specific files
write:
  - ./output/summary.txt
  - /var/log/custom.log
```

**Path resolution example:**

```yaml
write:
  - ./reports
  - ./output
```

When agent writes `summary.txt`:
- Resolves to: `./reports/summary.txt` (first write dir)

## Security Restrictions

File access is validated before every operation.

### Forbidden Read Paths

**Cannot read:**

1. **Agents directory** (`workspace/agents`)
   - Prevents reading other agents' code
   - Error: `"Access denied: cannot read from agents directory"`

2. **`.env` files** (any `.*env*`)
   - Prevents credential leakage
   - Error: `"Access denied: cannot read .env files"`

### Forbidden Write Paths

**Cannot write:**

1. **Agents directory** (`workspace/agents`)
   - Prevents modifying agent code
   - Error: `"Access denied: cannot write to agents directory"`

2. **`.db` files**
   - Prevents database corruption
   - Error: `"Access denied: cannot write to .db files"`

3. **`.env` files** (any `.*env*`)
   - Prevents credential modification
   - Error: `"Access denied: cannot write .env files"`

### Watch Triggers

Agents with `watch` triggers automatically gain read access:

```yaml
trigger:
  type: watch
  paths:
    - ./data/input.txt

# Implicit read permission for ./data/input.txt
```

Explicit `read` is combined with watch paths:

```yaml
trigger:
  type: watch
  paths:
    - ./data/input.txt
read:
  - ./config
# Can read both ./data/input.txt AND ./config
```

## Common Patterns

### Read-Only Access

```yaml
read:
  - ./data
# No write field = default output only
```

### Write-Only Access

```yaml
write:
  - ./output
# No read field = can read entire workspace
```

### Isolated Agent

```yaml
read:
  - ./data/input
write:
  - ./output/agent1
```

### Multi-Source Reader

```yaml
read:
  - ./data
  - ./logs
  - /var/log/app
write:
  - ./reports
```

### Specific File Access

```yaml
read:
  - ./config/settings.json
  - ./data/input.csv
write:
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
read: ./data/input
write: ./output/results

# ❌ Avoid: overly broad
read: /
write: /
```

### Separate Concerns

Use different directories per agent:

```yaml
# Agent 1
write: ./output/agent1

# Agent 2
write: ./output/agent2
```

### Use Relative Paths

Prefer relative for portability:

```yaml
# ✅ Portable
read: ./data
write: ./output

# ⚠️ Machine-specific
read: /Users/alice/data
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

### "Access denied: outside allowed read paths"

**Cause:** Agent tried to read unlisted path

**Fix:** Add to `read`:
```yaml
read:
  - ./data
  - ./logs  # Add missing
```

### "Access denied: outside allowed write paths"

**Cause:** Agent tried to write unlisted path

**Fix:** Add to `write`:
```yaml
write:
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
