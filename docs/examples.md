# Agent.md Examples

Copy-paste ready examples for common use cases. Each example is a complete, runnable agent file.

---

## 1. Hello World - Basic Agent

**Use case:** Learn agent basics, file writing, temperature control.

**Agent file:** `workspace/agents/hello-world.md`

```markdown
---
name: hello-world
description: A friendly greeting agent demonstrating basic functionality
model:
  provider: google
  name: gemini-2.5-flash
trigger:
  type: manual
settings:
  temperature: 0.7
  timeout: 30
enabled: true
---

You are a friendly assistant. Generate a creative greeting message including:
- A warm greeting
- Today's date
- An encouraging message

Keep it under 3 sentences. Save to 'greeting.txt'.
```

**What it does:**
1. Agent generates a creative greeting
2. Saves greeting to `greeting.txt`

**How to run:**
```bash
agentmd run hello-world
cat workspace/output/greeting.txt
```

**Expected output:**
```
Hello there! Today is March 11, 2026. Wishing you a fantastic day
filled with productivity and joy! May your code compile without
errors and your coffee stay hot. ☕
```

---

## 2. File Operations - Read & Process

**Use case:** Process documents, extract information, transform content.

**Setup:** First create input file:
```bash
mkdir -p workspace/output
cat > workspace/output/article.txt << 'EOF'
The Amazon Rainforest covers 5.5 million square kilometers with Brazil containing 60%.
Called "lungs of the Earth", it produces 6-9% of world's oxygen. Home to 10% of all species.
Deforestation: 17% lost between 2000-2020. Threat to climate system.
EOF
```

**Agent file:** `workspace/agents/text-processor.md`

```markdown
---
name: text-processor
description: Reads article and extracts key facts
model:
  provider: google
  name: gemini-2.5-flash
trigger:
  type: manual
settings:
  temperature: 0.3
  timeout: 60
enabled: true
---

You are an expert content analyst. Your task:

1. Read file at `article.txt` using file_read
2. Extract and organize:
   - Main topic
   - Key statistics (preserve all numbers)
   - Important concepts
   - Challenges/issues
3. Format as clear structured summary
4. Save to `article-facts.txt`

Be thorough and accurate.
```

**How to run:**
```bash
agentmd run text-processor
cat workspace/output/article-facts.txt
```

---

## 3. HTTP Request - Fetch API Data

**Use case:** Integrate with external APIs, fetch real-time data.

**Agent file:** `workspace/agents/quote-fetcher.md`

```markdown
---
name: quote-fetcher
description: Fetches random quote and saves to file
model:
  provider: google
  name: gemini-2.5-flash
trigger:
  type: manual
settings:
  temperature: 0.5
  timeout: 30
enabled: true
---

You are a helpful assistant. Your task:

1. Use http_request to fetch from https://api.quotable.io/random
2. Parse JSON response to extract:
   - Quote text
   - Author name
3. Format nicely with metadata
4. Save to `quote.txt`
```

**How to run:**
```bash
agentmd run quote-fetcher
cat workspace/output/quote.txt
```

**Expected output:**
```
"The only way to do great work is to love what you do."
— Steve Jobs

Source: quotable.io
Fetched: 2026-03-11 11:52:17
```

---

## 4. Scheduled Task - Interval-based Execution

**Use case:** Run agents automatically every N minutes/hours.

**Agent file:** `workspace/agents/health-check.md`

```markdown
---
name: health-check
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
enabled: true
---

You are a system monitor. Your task:

1. Use http_request to check endpoint: https://api.github.com/status
2. Extract status information:
   - API availability
   - Response time
   - Any warnings
3. Create brief status report
4. Save to `status-check-{timestamp}.txt`

Format timestamp as YYYYMMDD-HHMMSS.
```

**How to run:**
```bash
agentmd start  # Starts scheduler (runs every 30 minutes)
agentmd logs health-check  # View execution history
```

---

## 5. File Watcher - Watch for File Changes

**Use case:** Auto-process uploaded files, monitor directories.

**Setup:** Create watch directory:
```bash
mkdir -p workspace/uploads
```

**Agent file:** `workspace/agents/file-watcher.md`

```markdown
---
name: file-watcher
description: Auto-processes uploaded files
model:
  provider: google
  name: gemini-2.5-flash
trigger:
  type: watch
  paths:
    - workspace/uploads
settings:
  temperature: 0.3
  timeout: 60
enabled: true
---

You are a file processor. When a file is uploaded:

1. Read the uploaded file
2. Analyze its content (text/code/data)
3. Generate analysis report including:
   - File type detected
   - Content summary
   - Any issues or observations
4. Save report to `workspace/output/analysis-{filename}.txt`

Be thorough and helpful.
```

**How to run:**
```bash
agentmd start  # Starts file watcher
# In another terminal:
echo "Sample content" > workspace/uploads/test.txt
# Agent automatically processes it
cat workspace/output/analysis-test.txt.txt
```

---

## 6. Custom Tools Integration

**Use case:** Add custom Python functions beyond built-in tools.

**Setup:** Create tools file:
```bash
mkdir -p workspace/tools
cat > workspace/tools/my_tools.py << 'EOF'
from agent_md.tools.registry import tool

@tool
def analyze_text(text: str) -> str:
    """Analyze text and return word count and reading time."""
    words = len(text.split())
    reading_time = max(1, words // 200)
    return f"Words: {words}, Reading time: ~{reading_time} min"

@tool
def format_json(data: str) -> str:
    """Parse and pretty-print JSON data."""
    import json
    parsed = json.loads(data)
    return json.dumps(parsed, indent=2)
EOF
```

**Agent file:** `workspace/agents/text-analyzer.md`

```markdown
---
name: text-analyzer
description: Analyzes text using custom tools
model:
  provider: google
  name: gemini-2.5-flash
trigger:
  type: manual
custom_tools:
  module: workspace.tools.my_tools
settings:
  temperature: 0.3
  timeout: 60
enabled: true
---

You are a text analyst. Your task:

1. Read file at `document.txt`
2. Use analyze_text tool to get statistics
3. Create analysis report including:
   - Word count and reading time
   - Key themes
   - Writing quality assessment
4. Save to `analysis.txt`
```

**How to run:**
```bash
echo "Your text here..." > workspace/output/document.txt
agentmd run text-analyzer
cat workspace/output/analysis.txt
```

---

## 7. Multiple API Integration - Data Aggregation

**Use case:** Combine data from multiple APIs, create dashboards.

**Agent file:** `workspace/agents/market-dashboard.md`

```markdown
---
name: market-dashboard
description: Creates dashboard from multiple APIs
model:
  provider: anthropic
  name: claude-3-5-sonnet-20241022
trigger:
  type: schedule
  cron: "0 9 * * MON-FRI"  # Daily at 9 AM weekdays
settings:
  temperature: 0.2
  timeout: 90
enabled: true
---

You are a market analyst. Create daily dashboard:

1. FETCH WEATHER
   - http_request to api.open-meteo.com
   - Extract: temperature, conditions, wind

2. FETCH NEWS
   - http_request to api.example.com/news
   - Extract: top 3 headlines

3. FETCH MARKET DATA
   - http_request to api.coindesk.com/v1/bpi/currentprice.json
   - Extract: Bitcoin price and trend

4. COMPILE REPORT
   - Combine all data
   - Add analysis and insights
   - Format for readability

5. SAVE
   - Save to `dashboard-{DDMMYY}.txt`
   - Include timestamps and sources
```

**How to run:**
```bash
agentmd start  # Scheduler runs at 9 AM
agentmd logs market-dashboard
```

---

## 8. Complex Workflow - Multi-step Processing

**Use case:** Process data through multiple transformation steps.

**Setup:** Create sample CSV:
```bash
cat > workspace/output/sales-data.csv << 'EOF'
date,product,revenue,units
2026-03-01,Widget,1500,50
2026-03-02,Gadget,2000,40
2026-03-03,Widget,1200,40
2026-03-04,Gadget,2500,50
2026-03-05,Widget,1800,60
EOF
```

**Agent file:** `workspace/agents/data-pipeline.md`

```markdown
---
name: data-pipeline
description: Complete data processing pipeline
model:
  provider: anthropic
  name: claude-3-5-sonnet-20241022
trigger:
  type: manual
settings:
  temperature: 0.1
  timeout: 120
enabled: true
---

You are a data analyst. Complete multi-step pipeline:

STEP 1: LOAD
- Read file at `sales-data.csv`
- Parse CSV format

STEP 2: ANALYZE
- Calculate total revenue
- Find top performing product
- Calculate average units sold
- Identify trends

STEP 3: VALIDATE
- Check all data is numeric
- Flag any anomalies
- Verify date format

STEP 4: ENRICH
- Add running totals
- Calculate growth rates
- Add insights

STEP 5: GENERATE REPORTS
- Save summary to `report-summary.txt`
- Save detailed analysis to `report-detailed.txt`
- Save JSON export to `report-data.json`

Be thorough, accurate, and professional.
```

**How to run:**
```bash
agentmd run data-pipeline
ls -la workspace/output/report-*
cat workspace/output/report-summary.txt
```

---

## 9. Chat Assistant with Memory

**Use case:** Interactive assistant that remembers context across sessions using both session history and long-term memory.

**Agent file:** `workspace/agents/smart-assistant.md`

```markdown
---
name: smart-assistant
description: Personal assistant with persistent memory
history: medium
paths:
  - output/
---

You are a personal assistant with long-term memory capabilities.

## On first interaction:
- Introduce yourself and ask the user how you can help
- Save any user details they share to the "user_profile" memory section

## On returning sessions:
- Retrieve the "user_profile" and "projects" memory sections
- Greet the user by name if you know it
- Proactively mention any pending action items

## Memory management:
- Save user preferences and facts to "user_profile"
- Save project details and deadlines to "projects"
- Append tasks to "action_items"
- When a section gets long, summarize it

## General behavior:
- Be concise and helpful
- Always confirm when saving to memory
- Use file_write for any reports or documents the user requests
```

**How to run:**
```bash
# Session 1 — get to know the user
agentmd chat smart-assistant
> Hi, I'm Alice. I'm a data scientist working on a churn prediction model.
> The deadline is March 30th.
> /exit

# Session 2 — agent remembers everything
agentmd chat smart-assistant
> What do you remember about my project?
# Agent retrieves memory and responds with full context
```

---

## 10. Learning Monitor — Scheduled Agent with Memory

**Use case:** A scheduled agent that learns patterns over time by accumulating observations in long-term memory.

**Agent file:** `workspace/agents/uptime-monitor.md`

```markdown
---
name: uptime-monitor
description: Monitors API uptime and learns failure patterns
history: low
trigger:
  type: schedule
  every: 30m
paths:
  - output/
---

You are an uptime monitor that learns from past observations.

## Each run:
1. Retrieve the "failure_patterns" memory section (if it exists)
2. Check https://api.example.com/health using http_request
3. If the check fails:
   - Append the failure details (timestamp, error, status code) to the "incident_log" memory section
   - Check if this matches any known failure patterns
   - If a new pattern emerges, save it to "failure_patterns"
4. If the check succeeds:
   - If there was a recent failure, note the recovery time
5. Every 10 runs, summarize the "incident_log" section to keep it concise

## Output:
- Save status to `uptime/status-{timestamp}.txt`
- Include trend analysis based on your memory of past checks
```

**How to run:**
```bash
agentmd start  # Scheduler runs every 30 minutes
agentmd logs uptime-monitor  # View history

# Check what the agent has learned:
cat workspace/agents/uptime-monitor.memory.md
```

---

## Quick Reference

### File Locations

| Item | Location |
|------|----------|
| Agent files | `workspace/agents/*.md` |
| Input files | `workspace/output/*.txt` |
| Output files | `workspace/output/*.txt` |
| Custom tools | `workspace/tools/*.py` |

### Common Triggers

```yaml
# Manual (one-shot)
trigger:
  type: manual

# Scheduled interval
trigger:
  type: schedule
  every: 30m

# Scheduled cron
trigger:
  type: schedule
  cron: "0 9 * * *"  # Daily at 9 AM

# File watcher
trigger:
  type: watch
  paths:
    - workspace/uploads
```

### Built-in Tools

| Tool | Usage |
|------|-------|
| `file_read` | Read files: `Read file at 'name.txt'` |
| `file_write` | Write files: `Save to 'output.txt'` |
| `file_edit` | Edit files: `Update line X in 'config.txt'` |
| `file_glob` | Find files: `Find all '*.csv' files in 'data/'` |
| `http_request` | Call APIs: `Use http_request to fetch...` |
| `memory_save` | Store/replace: `Save to "notes" memory section` |
| `memory_append` | Append: `Append to "log" memory section` |
| `memory_retrieve` | Read: `Retrieve the "context" memory section` |

### Temperature Settings

| Range | Behavior | Use Case |
|-------|----------|----------|
| 0.0-0.3 | Deterministic | Analysis, summaries, facts |
| 0.4-0.6 | Balanced | Most tasks |
| 0.7-0.9 | Creative | Writing, content generation |
| 0.9-1.0 | Very creative | Brainstorming |

### Common Commands

```bash
# Run single agent (one-shot)
agentmd run agent-name

# Interactive chat with agent
agentmd chat agent-name

# List all agents
agentmd list

# View execution history
agentmd logs agent-name

# Validate agent file
agentmd validate workspace/agents/agent.md

# Start scheduler + watcher
agentmd start

# Get help
agentmd --help
```

---

## Next Steps

1. Choose an example that matches your use case
2. Copy the agent file to `workspace/agents/`
3. Customize the prompt for your needs
4. Run with `agentmd run <name>`
5. Check output in `workspace/output/`

For more details, see:
- [Agent Configuration](agent-configuration.md)
- [Memory System](memory.md)
- [Tool Reference](tools/built-in-tools.md)
- [Paths & Security](paths-and-security.md)
