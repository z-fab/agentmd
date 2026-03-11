# Security Best Practices

Practical security guidelines for building and deploying Agent.md agents safely.

## Core Principles

### 1. Least Privilege

Only grant the minimum permissions needed for an agent to function.

**Bad:**
```yaml
---
name: daily-quote
paths:
  read: ["/"]  # Can read everything!
  write: ["/"]  # Can write anywhere!
---
```

**Good:**
```yaml
---
name: daily-quote
paths:
  read: ["/workspace/data/quotes.txt"]
  write: ["/output/daily-quote.txt"]
---
```

**Real-world example:**
```yaml
---
name: log-analyzer
paths:
  read:
    - "/var/log/app/*.log"
    - "/workspace/config/patterns.yml"
  write: ["/output/reports/"]
# Can't read config files, can't write to workspace
---
```

### 2. Never Store Secrets in Frontmatter

API keys, passwords, and tokens belong in environment variables, never in `.md` files.

**NEVER do this:**
```yaml
---
name: slack-bot
model:
  provider: openai
  api_key: sk-proj-abc123...  # WRONG!
settings:
  slack_webhook: https://hooks.slack.com/services/T00/B00/xxx  # WRONG!
---
```

**Always do this:**
```yaml
---
name: slack-bot
model:
  provider: openai
  # API key loaded from OPENAI_API_KEY env var
settings:
  env:
    SLACK_WEBHOOK: ${SLACK_WEBHOOK}  # Loaded from .env
---
```

`.env` file:
```bash
OPENAI_API_KEY=sk-proj-abc123...
SLACK_WEBHOOK=https://hooks.slack.com/services/T00/B00/xxx
```

### 3. Use Environment Variables

Store all sensitive data in `.env` files and reference them in frontmatter.

**Directory structure:**
```
/Users/zfab/repos/agentmd/
├── .env                    # Local dev (gitignored)
├── .env.production         # Production secrets (gitignored)
├── .env.example            # Template (committed)
└── workspace/
    └── my-agent.md
```

**`.env.example` (commit this):**
```bash
# LLM Provider
OPENAI_API_KEY=sk-proj-your-key-here
ANTHROPIC_API_KEY=sk-ant-your-key-here
GOOGLE_API_KEY=your-key-here

# External Services
SLACK_WEBHOOK=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
DATABASE_URL=postgresql://user:pass@localhost:5432/db

# Agent.md Settings
WORKSPACE_DIR=/workspace
OUTPUT_DIR=/output
MAX_ITERATIONS=10
```

**Access in agents:**
```yaml
---
name: api-poller
settings:
  env:
    API_TOKEN: ${API_TOKEN}
    API_BASE_URL: ${API_BASE_URL}
---

You have access to an API. Use the API_TOKEN and API_BASE_URL from settings to make requests.
```

### 4. Set Timeouts and Limits

Prevent runaway costs and infinite loops.

```yaml
---
name: research-agent
model:
  provider: openai
  name: gpt-4
  temperature: 0.7
  max_tokens: 2000  # Limit output length
settings:
  max_iterations: 5  # Prevent infinite loops
  timeout: 300       # 5 minute timeout
  recursion_limit: 10
---
```

**Real-world example for expensive operations:**
```yaml
---
name: web-scraper
model:
  provider: anthropic
  name: claude-opus-4-6
  max_tokens: 4000    # Opus is expensive
settings:
  max_iterations: 3   # Limit tool calls
  timeout: 180        # 3 minute hard stop
triggers:
  - type: schedule
    cron: "0 9 * * *"  # Once daily, not every minute
---
```

### 5. File Watcher Debouncing

Prevent watch triggers from firing repeatedly during file edits.

**Without debouncing (fires multiple times):**
```yaml
triggers:
  - type: watch
    paths: ["/workspace/data/input.json"]
    # Will fire on every keystroke during editing!
```

**With debouncing:**
```yaml
triggers:
  - type: watch
    paths: ["/workspace/data/input.json"]
    debounce: 2.0  # Wait 2 seconds after last change
```

**Real-world example:**
```yaml
---
name: code-reviewer
triggers:
  - type: watch
    paths:
      - "/workspace/src/**/*.py"
      - "/workspace/src/**/*.js"
    debounce: 3.0    # Wait for user to finish typing
    ignore_patterns:
      - "**/__pycache__/**"
      - "**/node_modules/**"
      - "**/.git/**"
---
```

### 6. Pre-Validation

Validate inputs before expensive LLM calls.

**Example agent with validation:**
```yaml
---
name: email-processor
paths:
  read: ["/workspace/data/emails/*.json"]
  write: ["/output/processed/"]
---

Before processing emails:
1. Validate JSON structure
2. Check required fields: from, to, subject, body
3. Skip if already processed (check /output/processed/)
4. Only process emails from the last 24 hours

This prevents wasting tokens on invalid data.
```

**Validation in prompt:**
```markdown
You are an email processor. Follow these steps:

1. **Validate input** - Check that the email JSON contains:
   - `from` (email address)
   - `to` (email address)
   - `subject` (non-empty string)
   - `body` (non-empty string)
   - `timestamp` (ISO 8601 format)

2. **Skip if invalid** - If validation fails, write an error to `/output/errors/` and stop. Do not proceed.

3. **Process valid emails only** - Continue with your task.
```

### 7. Token Monitoring

Track and limit token usage to prevent cost overruns.

**Check token usage:**
```bash
# View token usage for all executions
agentmd logs research-agent --verbose

# Output shows:
# Execution: abc123
# Input tokens: 1,234
# Output tokens: 567
# Total tokens: 1,801
# Estimated cost: $0.05
```

**Set alerts in production:**
```yaml
---
name: production-agent
model:
  provider: openai
  name: gpt-4
  max_tokens: 1000  # Hard limit per response
settings:
  max_iterations: 5  # Max 5 tool calls = max ~5000 tokens
---
```

**Calculate maximum possible cost:**
```
Max tokens per iteration: 1000 output + ~500 input = 1500
Max iterations: 5
Total max tokens: 7,500

GPT-4 pricing (example):
- Input: $0.03 / 1K tokens
- Output: $0.06 / 1K tokens

Max cost per execution:
- Input: 2,500 * $0.03 / 1000 = $0.075
- Output: 5,000 * $0.06 / 1000 = $0.30
- Total: ~$0.38 per execution
```

## Path Security

### Workspace Isolation

Keep agents isolated to their designated directories.

**Secure setup:**
```yaml
---
name: report-generator
paths:
  read:
    - "/workspace/data/reports/"
    - "/workspace/config/templates/"
  write: ["/output/reports/"]
# Cannot read from /etc/, /home/, other sensitive paths
---
```

**Multiple agents with isolation:**
```yaml
# Agent 1: Customer data processor
---
name: customer-processor
paths:
  read: ["/workspace/data/customers/"]
  write: ["/output/customers/"]
---

# Agent 2: Analytics reporter
---
name: analytics-reporter
paths:
  read: ["/output/customers/aggregated.json"]  # Only reads aggregated data
  write: ["/output/reports/"]
# Cannot read raw customer data from /workspace/data/customers/
---
```

### Sensitive Path Patterns

Never grant access to these paths:

```yaml
# DANGEROUS - Never do this:
paths:
  read:
    - "/etc/**"              # System config
    - "/home/**"             # User directories
    - "~/.ssh/**"            # SSH keys
    - "~/.aws/**"            # AWS credentials
    - "**/.env"              # Environment files
    - "**/secrets.yml"       # Secret files
```

## Schedule Security

### Avoid Expensive Frequent Schedules

```yaml
# EXPENSIVE - $$$
triggers:
  - type: schedule
    cron: "* * * * *"  # Every minute with GPT-4!

# REASONABLE
triggers:
  - type: schedule
    cron: "0 */6 * * *"  # Every 6 hours
```

**Calculate schedule costs:**
```
Schedule: Every hour (24x per day)
Cost per execution: $0.10
Daily cost: 24 * $0.10 = $2.40
Monthly cost: $2.40 * 30 = $72.00

vs.

Schedule: Every 6 hours (4x per day)
Cost per execution: $0.10
Daily cost: 4 * $0.10 = $0.40
Monthly cost: $0.40 * 30 = $12.00
```

### Rate Limiting External APIs

Respect API rate limits in scheduled agents.

```yaml
---
name: api-poller
triggers:
  - type: schedule
    cron: "*/15 * * * *"  # Every 15 minutes
---

The API has a rate limit of 100 requests/hour.
- Each run makes ~4 requests
- Schedule: 4 runs/hour * 4 requests = 16 requests/hour
- Well within 100 req/hour limit ✓
```

## Tool Security

### HTTP Request Tool

Restrict allowed domains and methods.

```yaml
---
name: news-fetcher
tools:
  - name: http_request
    config:
      allowed_domains:
        - "api.newsapi.org"
        - "rss.nytimes.com"
      allowed_methods: ["GET"]  # No POST/PUT/DELETE
      timeout: 10
      max_redirects: 2
---
```

### File Write Tool

Prevent overwriting important files.

```yaml
---
name: log-processor
paths:
  write: ["/output/processed/"]
  # Explicitly NOT allowed to write to:
  # - /workspace/ (source data)
  # - /etc/ (system files)
  # - ~ (home directory)
---

Never overwrite files in /workspace/. Only write to /output/.
```

## MCP Security

### Restrict MCP Tool Access

Only enable needed MCP servers and tools.

```yaml
---
name: filesystem-agent
mcp:
  servers:
    filesystem:
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-filesystem", "/workspace/data"]
      # Filesystem server is sandboxed to /workspace/data only
  allowed_tools:
    - "read_file"
    - "list_directory"
    # NOT allowed: write_file, delete_file, move_file
---
```

## Checklist

Before deploying an agent to production:

- [ ] No secrets in frontmatter
- [ ] All secrets in `.env` file
- [ ] `.env` file is in `.gitignore`
- [ ] `paths.read` and `paths.write` follow least privilege
- [ ] `max_tokens` set appropriately
- [ ] `max_iterations` set to prevent loops
- [ ] `timeout` set to prevent hangs
- [ ] Schedule frequency is cost-effective
- [ ] Watch triggers have `debounce` configured
- [ ] HTTP tools have `allowed_domains` set
- [ ] Token usage monitored and alerted
- [ ] Pre-validation in prompt to skip invalid inputs
- [ ] Tested with invalid/malicious inputs

## Security Incident Response

If an agent is compromised or leaking data:

1. **Stop execution immediately:**
   ```bash
   # Kill the runtime
   pkill -f agentmd

   # Or stop specific agent
   # (disable trigger in frontmatter and restart)
   ```

2. **Rotate secrets:**
   ```bash
   # Rotate all API keys in .env
   # Update OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.
   ```

3. **Audit logs:**
   ```bash
   # Check what the agent did
   agentmd logs <agent-name> --verbose

   # Check file system
   ls -la /output/
   ```

4. **Review and fix:**
   - Add missing path restrictions
   - Add missing input validation
   - Reduce permissions

5. **Test and redeploy:**
   ```bash
   agentmd validate workspace/agent.md
   agentmd run agent.md --dry-run  # Test without executing
   ```
