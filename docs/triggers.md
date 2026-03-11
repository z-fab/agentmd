# Triggers Guide

Triggers define when an agent executes. Agent.md supports three trigger types: **Manual**, **Schedule**, and **Watch**.

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
read: ./uploads
write: ./output
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
read:
  - ./logs
  - ./data
write: ./reports
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
```

### Paths

- **Relative paths:** Resolve from workspace root (e.g., `./uploads`, `./data`)
- **Absolute paths:** Used as-is (e.g., `/var/log/app`)
- **Home expansion:** Use `~` for home directory

### Events

Watch triggers activate on:

- File creation

- File modification

- File deletion (optional, not triggered by default)

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
read: ./uploads
write: ./output
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
read:
  - ./inbox
  - ./staging
  - /tmp/uploads
write: ./processed
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
read: ./uploads
write: ./output
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
write: ./reports
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
read: ./logs
write: ./reports
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
read: ./inbox
write: ./processed
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

**Problem:** Agent runs too many times when files are modified

**Workaround:** Use file extensions to filter:
```yaml
# Monitor specific files only
trigger:
  type: watch
  paths:
    - ./inbox/*.csv    # Only CSV files
    - ./uploads/*.pdf  # Only PDF files
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
