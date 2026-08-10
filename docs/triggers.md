# Triggers Guide

Triggers define when an agent executes. Agentmd supports three trigger types: **Manual**, **Schedule**, and **Watch**.

---

## Overview

A trigger controls the execution timing of an agent:

- **Manual** - Run via CLI command (default, most common)
- **Schedule** - Run automatically on a fixed interval or cron schedule
- **Watch** - Run automatically when files change in watched directories

Every agent must have a trigger. If not specified, `type: manual` is the default.

---

## Manual Trigger

Execute agents on-demand via CLI. Best for one-time tasks, testing, and user-initiated workflows.

### When to use
- Processing uploaded files
- Running reports on-demand
- Testing and development

### Configuration

```yaml
trigger:
  type: manual
```

The `manual` trigger requires only the `type` field.

### Execution

```bash
# Run a manual trigger agent
agentmd run my-agent

# View execution history
agentmd logs my-agent
```

### Example: On-Demand File Analyzer

```yaml
---
name: file-analyzer
description: Analyzes files on demand
model:
  provider: google
  name: gemini-2.5-flash
trigger:
  type: manual
settings:
  temperature: 0.3
  timeout: 60
paths:
  - ./uploads
  - ./output
---

Analyze the uploaded file and provide:
1. File type and size
2. Content summary
3. Key information extracted
4. Any recommendations
```

Run with: `agentmd run file-analyzer`

---

## Schedule Trigger

Run agents automatically on a fixed schedule. Supports both interval-based (`every`) and cron-based (`cron`) scheduling.

### When to use
- Periodic monitoring and health checks
- Daily/weekly/monthly reports
- Regular data collection and processing
- Maintenance tasks

### Interval-Based Scheduling

Execute every N minutes, hours, or days.

#### Configuration

```yaml
trigger:
  type: schedule
  every: <duration>
```

#### Duration Format

- Minutes: `5m`, `30m`, `60m`
- Hours: `1h`, `2h`, `12h`
- Days: `1d`, `7d`
- Seconds (rare): `30s`, `300s`

#### Examples

```yaml
# Every 5 minutes
trigger:
  type: schedule
  every: 5m

# Every 30 minutes
trigger:
  type: schedule
  every: 30m

# Every 2 hours
trigger:
  type: schedule
  every: 2h

# Every day
trigger:
  type: schedule
  every: 1d
```

### Cron-Based Scheduling

Use standard cron expressions for precise scheduling.

#### Configuration

```yaml
trigger:
  type: schedule
  cron: "<cron-expression>"
```

#### Cron Format

Standard 5-field format: `minute hour day month day-of-week`

```
*      *      *      *      *
│      │      │      │      │
│      │      │      │      └─ Day of week (0-6, 0=Sunday)
│      │      │      └─────── Month (1-12)
│      │      └──────────── Day of month (1-31)
│      └─────────────────── Hour (0-23)
└────────────────────────── Minute (0-59)
```

#### Common Cron Examples

```yaml
# Daily at 9:00 AM
cron: "0 9 * * *"

# Every Monday at 8:00 AM
cron: "0 8 * * 1"

# Every weekday (Mon-Fri) at 5:00 PM
cron: "0 17 * * 1-5"

# 1st of month at midnight
cron: "0 0 1 * *"

# Every 6 hours (0, 6, 12, 18)
cron: "0 0,6,12,18 * * *"

# Every 30 minutes
cron: "*/30 * * * *"

# Last day of month at 11:59 PM
cron: "59 23 L * *"
```

### Execution

Schedule triggers require `agentmd start` to activate the scheduler:

```bash
# Start runtime with scheduler and file watcher
agentmd start

# View execution history in another terminal
agentmd logs my-agent
```

### Example 1: Interval-Based Health Check

```yaml
---
name: api-health-check
description: Checks API health every 30 minutes
model:
  provider: google
  name: gemini-2.5-flash
trigger:
  type: schedule
  every: 30m
settings:
  temperature: 0.2
  timeout: 45
---

Check the GitHub API status endpoint and report:
1. API availability (up/down)
2. Response time
3. Any ongoing incidents
4. Timestamp of check

Format clearly and save to 'health-{timestamp}.txt'
```

Run with: `agentmd start` (runs every 30 minutes)

### Example 2: Daily Cron-Based Report

```yaml
---
name: daily-report
description: Generates daily summary report
model:
  provider: anthropic
  name: claude-sonnet-4-5
trigger:
  type: schedule
  cron: "0 9 * * *"  # 9 AM daily
settings:
  temperature: 0.5
  max_tokens: 8192
  timeout: 180
paths:
  - ./logs
  - ./data
  - ./reports
---

Generate a daily summary report including:
1. Key events from the past 24 hours
2. Performance metrics
3. Error summary
4. Notable patterns or anomalies
5. Recommendations for tomorrow

Save as 'daily-{YYYY-MM-DD}.md'
```

Runs automatically at 9:00 AM every day when `agentmd start` is active.

---

## Watch Trigger

Monitor directories and run agents automatically when files change. Perfect for processing uploaded files, monitoring data directories, and automated workflows.

### When to use
- Processing uploaded files in real-time
- Monitoring log directories
- Auto-processing incoming data
- File transformation pipelines
- Directory-based workflows

### Configuration

```yaml
trigger:
  type: watch
  paths:
    - <path1>
    - <path2>
    - ...
  # optional:
  input: "Process {path}."
  debounce: 0.5          # seconds (default 500ms); also accepts "2s" / "500ms"
  filters:
    include: ["*.pdf"]   # if set, path must match at least one
    exclude: [".DS_Store", "*.tmp"]
```

### Paths

- **Relative paths:** Resolve from workspace root (e.g., `./uploads`, `./data`)
- **Absolute paths:** Used as-is (e.g., `/var/log/app`)
- **Home expansion:** Use `~` for home directory

### Filters

`filters.include` / `filters.exclude` are glob lists matched against the event path (basename and absolute path). Exclude wins over include. Matching happens in the watch handler — an excluded file never becomes a trigger, so the admission gate never sees it. Without `filters`, every file under `paths` still fires (including `.DS_Store`); declare an exclude when you want those dropped.

### Debounce

`debounce` (default `0.5` seconds) collapses rapid events for the same path into one trigger. Declare a larger window for downloads or editors that write many times in a burst.

### Custom input

`input` replaces the hardcoded watch prompt. Use `{event}`, `{path}` / `{file}`, and `{context}` for the raw event string. See [Agent Configuration](./agent-configuration.md#trigger) for how this composes with run `context` on manual/chat triggers.

### Self-writes do not retrigger the agent

A watch agent may write into the directory it watches — in fact it usually must, since watch paths are automatically part of the agent's allowed write paths. Its own writes do **not** trigger it again.

Every built-in write tool (`file_write`, `file_edit`, `file_delete`, `file_move`, `memory_save`, `memory_append`) records the path it touched, the resulting modification time, and the agent that wrote it. The watch handler drops an event when all three of these hold:

1. the path was written by **this** agent (another agent's write still triggers — see below);
2. the file on disk still carries the exact mtime that write left behind;
3. less than **2 seconds** have passed.

Nothing is configurable here, and nothing needs to be: the check is about *identity of the change*, not about timing.

**A user's edit is never swallowed.** Saving the file yourself right after the agent gives it a new modification time, so condition 2 fails and the agent runs — even one millisecond after its own write. The 2 s window is not there to tell you apart from the agent; it exists because filesystem events do not arrive instantly (up to one second on network mounts, where watchdog falls back to polling), and because a *deletion* records only "this path is absent", which is too coarse a fingerprint to trust indefinitely.

**Only the writer is suppressed.** Agent B writing into a directory agent A watches still triggers A. A hand-off pipeline is the point, not a loop:

```yaml
# collector.md — trigger: schedule, writes ./inbox
# processor.md — trigger: watch ./inbox, still fires on every file the collector drops
```

#### Known limits

This is a best-effort layer with a declared boundary. In each case below the agent **does** retrigger itself, by design rather than by oversight — covering them would mean intercepting arbitrary third-party code:

| Write path | Retriggers? | Why |
|---|---|---|
| Built-in file and memory tools | no | records its own writes |
| **MCP server tool** | **yes** | writes inside another process, which agentmd never sees |
| **Custom tool** (`_config/tools/`) | **yes** | writes with plain Python; use `agent_md.sdk.resolve_path` and the built-in tools if you need suppression |
| **Sub-agent** invoked via `run_agent` | **yes** | the write is recorded under the sub-agent's id, not the caller's |
| External process, another agentmd instance, `git checkout` | yes | correct — these are genuine outside changes |

If an agent must write through one of the "yes" rows, keep it out of the loop the plain way: write to a directory the agent does not watch, or narrow `filters` so the produced files never match. A watch agent that writes into its own watched path via an MCP tool will run continuously.

One limit runs the other way — the only case where **your** edit can be swallowed. Telling your save apart from the agent's write relies on the filesystem timestamping the two differently. APFS and ext4 record nanoseconds, so they always do. Filesystems that store whole seconds (HFS+, ext3) do not: a save landing in the same second as the agent's write to the same file carries an identical mtime and is dropped. Bounded to that 2 s window and to a file the agent just wrote, so at worst you save again.

Causal tracking (execution depth, "which run caused this event") cannot substitute for any of this: a filesystem event carries no link back to the write that caused it, so every watch callback arrives as a fresh root.

### Events

Watch triggers activate on:

- File creation

- File modification

- File deletion

- File move

### Execution

Watch triggers require `agentmd start`:

```bash
# Start runtime with file watcher
agentmd start

# In another terminal, trigger by creating/modifying files
echo "data" > workspace/uploads/file.txt

# View execution history
agentmd logs my-watcher
```

### Example 1: Simple File Processor

```yaml
---
name: upload-processor
description: Processes uploaded files
model:
  provider: google
  name: gemini-2.5-flash
trigger:
  type: watch
  paths:
    - ./uploads
settings:
  temperature: 0.3
  timeout: 60
paths:
  - ./uploads
  - ./output
---

When a file is uploaded:
1. Read and analyze the file
2. Extract key information
3. Generate a processing report
4. Save report to './output/processed-{filename}.txt'

Be helpful and thorough.
```

Triggers automatically when files appear in `workspace/uploads/`.

### Example 2: Multi-Directory Watch

```yaml
---
name: data-ingestion
description: Processes data from multiple directories
model:
  provider: openai
  name: gpt-4
trigger:
  type: watch
  paths:
    - ./inbox
    - ./staging
    - /tmp/uploads
settings:
  temperature: 0.2
  timeout: 120
paths:
  - ./inbox
  - ./staging
  - /tmp/uploads
  - ./processed
---

Process incoming data files:
1. Identify file type (CSV, JSON, TXT, etc.)
2. Validate format and content
3. Transform to standard format
4. Save to './processed/{filename}.processed'
5. Create validation report

Handle errors gracefully.
```

Monitors all three directories simultaneously.

---

## Complete Examples

### Setup

Create workspace directories:

```bash
mkdir -p workspace/uploads workspace/inbox workspace/logs workspace/reports
```

### Agent 1: Manual File Processor (One-Off)

```yaml
---
name: text-summarizer
description: Summarizes text files on demand
model:
  provider: google
  name: gemini-2.5-flash
trigger:
  type: manual
settings:
  temperature: 0.4
  max_tokens: 2048
  timeout: 60
paths:
  - ./uploads
  - ./output
---

Summarize the provided text file:
1. Read the entire file
2. Create a concise summary (3-5 bullet points)
3. Extract key themes or main ideas
4. Save summary to 'summary-{filename}.txt'

Be clear and accurate.
```

Usage:
```bash
echo "Long text content..." > workspace/uploads/document.txt
agentmd run text-summarizer
cat workspace/output/summary-document.txt.txt
```

### Agent 2: Hourly Monitoring (Interval Schedule)

```yaml
---
name: system-monitor
description: Monitors system health every hour
model:
  provider: anthropic
  name: claude-sonnet-4-5
trigger:
  type: schedule
  every: 1h
settings:
  temperature: 0.2
  timeout: 45
paths:
  - ./reports
---

Create a system health report:
1. Check current date and time
2. Estimate system load (high/medium/low)
3. List any common issues to watch for
4. Provide recommendations
5. Save to 'health-{timestamp}.txt'

Format: clear, concise, actionable.
```

Runs every hour automatically when scheduler is active.

### Agent 3: Weekly Report (Cron Schedule)

```yaml
---
name: weekly-summary
description: Generates weekly summary every Monday
model:
  provider: openai
  name: gpt-4
trigger:
  type: schedule
  cron: "0 6 * * 1"  # Monday at 6 AM
settings:
  temperature: 0.5
  max_tokens: 4096
  timeout: 120
paths:
  - ./logs
  - ./reports
---

Generate a comprehensive weekly summary:
1. Identify key events from the week
2. Summarize performance metrics
3. Highlight achievements and challenges
4. Note patterns and trends
5. Provide recommendations for next week
6. Save as 'weekly-report-{YYYY-W##}.md'

Be thorough and insightful.
```

Runs every Monday at 6:00 AM automatically.

### Agent 4: Real-Time File Processing (Watch)

```yaml
---
name: incoming-processor
description: Processes files as they arrive
model:
  provider: google
  name: gemini-2.5-flash
trigger:
  type: watch
  paths:
    - ./inbox
settings:
  temperature: 0.3
  timeout: 90
paths:
  - ./inbox
  - ./processed
---

When new files arrive in inbox:
1. Determine file type
2. Parse and validate content
3. Extract structured data
4. Generate processing log
5. Save processed file to './processed/{filename}.done'
6. Create processing report

Ensure quality and accuracy.
```

Triggers automatically when files are added to `workspace/inbox/`.

---

## Troubleshooting

### Schedule Trigger Not Running

**Problem:** Scheduled agent never executes

**Cause:** Scheduler not active. Solution:
```bash
# Scheduler requires 'agentmd start'
agentmd start  # Keep this running in terminal or background
```

**Check:** View logs with `agentmd logs <agent-name>`

### Watch Trigger Not Triggering

**Problem:** File changes don't trigger agent

**Causes:**
1. Watcher not active (need `agentmd start`)
2. Wrong paths configured
3. Files in subdirectories (watch is not recursive by default)

**Solutions:**
```bash
# Ensure watcher is running
agentmd start

# Verify paths exist
ls -la workspace/uploads

# Use absolute paths if relative paths don't work
trigger:
  type: watch
  paths:
    - /Users/username/repos/agentmd/workspace/uploads
```

### Cron Expression Not Working

**Problem:** Cron trigger with syntax errors

**Solutions:**
- Test cron expressions at [crontab.guru](https://crontab.guru)
- Use 5-field format: `minute hour day month day-of-week`
- Remember: Sunday is 0, Monday is 1

**Valid:** `0 9 * * *` (9 AM daily)
**Invalid:** `0 9 * *` (missing day-of-week)

### Agent Runs Too Frequently or Too Rarely

**Interval trigger:**
```yaml
# Too frequent?
trigger:
  type: schedule
  every: 5m  # Change to 30m, 1h, etc.

# Too rare?
trigger:
  type: schedule
  every: 1d  # Change to 1h, 30m, etc.
```

**Cron trigger:**
- Use [crontab.guru](https://crontab.guru) to verify timing
- Remember timezone considerations
- Test with `agentmd logs <agent-name>` to see execution history

### Watch Trigger Triggers on Every Change

**Problem:** Agent runs too many times when files are modified (or fires on `.DS_Store`)

**Solution:** Use `filters` and raise `debounce`:
```yaml
trigger:
  type: watch
  paths:
    - ./inbox
  debounce: 2s
  filters:
    include: ["*.csv", "*.pdf"]
    exclude: [".DS_Store", "*.tmp", "**/.git/**"]
```

---

## Quick Reference

| Trigger Type | When to Use | Execution |
|---|---|---|
| **Manual** | On-demand tasks, testing | `agentmd run <name>` |
| **Schedule (every)** | Periodic monitoring, 5m-hourly tasks | `agentmd start` |
| **Schedule (cron)** | Daily/weekly/monthly reports | `agentmd start` |
| **Watch** | Real-time file processing | `agentmd start` |

---

## Related Documentation

- [Agent Configuration](./agent-configuration.md) - Complete config reference
- [CLI Reference](./cli-reference.md) - Command reference
- [Examples](./examples.md) - More agent examples
