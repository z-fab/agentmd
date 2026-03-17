# Memory System

Agent.md provides two complementary memory systems that allow agents to persist knowledge across executions:

1. **Session History** — Automatic conversation history via LangGraph checkpointing
2. **Long-term Memory** — Structured knowledge stored in `.memory.md` files via built-in tools

Both systems work independently and can be combined for powerful stateful agents.

---

## Session History

Session history uses LangGraph checkpointing with SQLite to automatically persist conversation messages between runs. When an agent runs again, it picks up where it left off.

### Configuration

Set the `history` field in your agent's frontmatter:

```yaml
---
name: my-agent
history: medium
---
```

| Level | Messages Sent to LLM | Best For |
|-------|----------------------|----------|
| `low` (default) | Last 10 | Short-lived tasks, simple agents |
| `medium` | Last 50 | Multi-session workflows, chat agents |
| `high` | Last 200 | Deep research, long-running projects |
| `off` | 0 (stateless) | One-shot tasks, no history needed |

### How It Works

- **All messages are saved** to a SQLite checkpoint database (`data/agentmd_checkpoints.db`)
- **Only the last N messages** are sent to the LLM (controlled by the history level), keeping costs and context window manageable
- **Thread ID = agent name** — all executions of the same agent share the same conversation thread
- **System message is always fresh** — date/time and memory sections are rebuilt on each run

### History in `run` Mode

Scheduled or manually triggered agents accumulate context over time:

```yaml
---
name: daily-monitor
description: Monitors system health and tracks trends
history: medium
trigger:
  type: schedule
  every: 1h
---

You are a system health monitor.

1. Check the API status at https://api.example.com/health
2. Compare with previous checks you remember
3. If you notice a trend (e.g., increasing latency), flag it
4. Save a status report to `health-{timestamp}.txt`

Use your memory of previous runs to identify patterns over time.
```

Each hourly run sees the last 50 messages from previous runs, enabling trend detection and contextual awareness.

### History in `chat` Mode

Chat sessions benefit the most from session history — the agent remembers previous chat sessions:

```yaml
---
name: project-assistant
description: Helps with project planning and tracking
history: high
paths:
  - output/
---

You are a project management assistant.

- Help the user plan tasks, track progress, and organize work
- Remember decisions, deadlines, and priorities from previous sessions
- When the user returns, proactively summarize what was discussed before
- Keep track of action items and follow up on them
```

```bash
# Session 1
agentmd chat project-assistant
> We need to ship the new auth module by Friday
> The team is Alice (backend) and Bob (frontend)
> /exit

# Session 2 (next day)
agentmd chat project-assistant
> Any updates on the auth module?
# Agent remembers: deadline is Friday, Alice does backend, Bob does frontend
```

### Disabling History

To make an agent fully stateless (no checkpointing), set `history: off`:

```yaml
---
name: one-shot-task
history: off
---

Generate a random joke and save it to `joke.txt`.
```

---

## Long-term Memory

Long-term memory gives agents three tools to read and write structured information in a persistent `.memory.md` file. Unlike session history (which stores raw conversation), long-term memory is **agent-curated** — the agent decides what to save, how to organize it, and when to summarize.

Memory tools are **always available** to all agents, regardless of the `history` setting.

### Memory Tools

#### `memory_save(section, content)`

Replaces the entire content of a named section. Use for:

- Storing new information
- Rewriting/summarizing a section that got too long
- Updating facts that changed

#### `memory_append(section, content)`

Appends content to a named section. Use for:

- Adding new entries to a log
- Accumulating observations over time
- Building up a knowledge base incrementally

!!! info "Digest Hint"
    When a section exceeds 50 lines, `memory_append` returns a hint suggesting the agent summarize the section using `memory_save`. This keeps memory files manageable.

#### `memory_retrieve(section)`

Reads the content of a named section. Use for:

- Recalling stored information before taking action
- Checking what was previously saved
- Loading context at the start of a session

### Memory File Format

Each agent's memory is stored in `agents/{agent-name}.memory.md`:

```markdown
# user_preferences

Prefers concise responses. Uses dark mode. Timezone: UTC-3.

# project_context

Working on the "Atlas" project — a data pipeline for ETL processing.
Tech stack: Python, PostgreSQL, Airflow.
Deadline: 2026-04-15.

# action_items

- Review PR #42 for the new transformer module
- Update the staging environment config
- Write tests for the date parser
```

Sections are delimited by `# SECTION_NAME` headers. The agent can create any sections it needs.

### System Prompt Integration

When an agent has a `.memory.md` file, the system prompt automatically lists available sections:

```
## Long-term Memory

You have the following memory sections available.
Use memory_retrieve to read their contents, memory_save to replace, and memory_append to add.

Available sections:
- user_preferences
- project_context
- action_items
```

The agent can then use `memory_retrieve` to load any section on demand, keeping the context window efficient.

### Example: Personal Assistant with Memory

```yaml
---
name: assistant
description: Personal assistant that remembers preferences and context
history: medium
paths:
  - output/
---

You are a personal assistant with long-term memory.

## Memory Management

- When the user tells you something about themselves (name, preferences, role),
  save it to the "user_profile" memory section
- When the user mentions a project or ongoing work,
  save key details to the "projects" memory section
- When given action items or todos,
  append them to the "action_items" section
- At the start of each session, retrieve relevant memory sections
  to personalize your responses

## Behavior

- Be proactive: if you remember something relevant, mention it
- Keep memory sections concise — summarize when they get long
- Always confirm when you save something to memory
```

**Session 1:**
```
> I'm a data engineer at Acme Corp. I work mostly with Python and Spark.
Agent: Noted! I've saved your profile. You're a data engineer at Acme Corp,
working with Python and Spark. How can I help?

> We're building a new ETL pipeline called "Phoenix". Deadline is end of April.
Agent: Saved to projects. I'll keep track of Phoenix. What do you need help with?
```

**Session 2 (days later):**
```
> Hey, how's it going?
Agent: Welcome back! Last time we talked about the Phoenix ETL pipeline
(deadline: end of April). How's it progressing? Need help with anything?
```

### Example: Learning Agent for Scheduled Tasks

```yaml
---
name: news-curator
description: Curates news and learns user interests over time
history: low
trigger:
  type: schedule
  every: 6h
paths:
  - output/
---

You are a news curator that learns from feedback.

1. Retrieve your "interests" memory section to know what topics to focus on
2. Fetch news from https://api.example.com/news
3. Filter and rank articles based on remembered interests
4. Save a curated digest to `news-{date}.txt`
5. Append today's curation stats to the "curation_log" memory section

If no interests are saved yet, start with general tech news and save
default interests to memory.
```

### Example: Research Agent with Knowledge Base

```yaml
---
name: researcher
description: Researches topics and builds a knowledge base
history: medium
paths:
  - output/
---

You are a research assistant that builds a persistent knowledge base.

## When asked to research a topic:
1. Check if you have existing notes on this topic using memory_retrieve
2. Conduct research using http_request
3. Save or update findings using memory_save (for the main summary)
   or memory_append (for new sources and quotes)
4. Write a comprehensive report to a file

## Memory organization:
- One section per research topic (e.g., "quantum_computing", "rust_language")
- Each section contains: summary, key findings, sources
- When a section exceeds 50 lines, summarize it to keep it focused

## When asked "what do you know about X?":
- Retrieve the relevant section and respond from memory
- No need to re-research if you already have recent notes
```

---

## Combining Session History + Long-term Memory

The two systems are complementary:

| Aspect | Session History | Long-term Memory |
|--------|----------------|-----------------|
| **Storage** | Raw messages (automatic) | Curated sections (agent-controlled) |
| **Granularity** | Every message | Key facts and summaries |
| **Growth** | Trimmed by level | Managed by agent (digest hints) |
| **Access** | Transparent (automatic) | Explicit (via tools) |
| **Best for** | Conversation continuity | Knowledge persistence |

**Best practice:** Use `history: medium` for conversation flow and memory tools for important facts. The agent can extract key information from the conversation and save it to long-term memory, ensuring critical knowledge survives even when old messages are trimmed.

```yaml
---
name: smart-agent
history: medium
---

You have both session history and long-term memory.

- Session history gives you recent conversation context automatically
- Use memory tools to save important facts that should persist indefinitely
- At the start of each session, retrieve your memory sections for full context
- Periodically save key conversation insights to memory before they get trimmed
```

---

## Validation

The `agentmd validate` command shows memory configuration:

```bash
agentmd validate my-agent
```

```
  ✓ my-agent

  Model          google / gemini-2.5-flash         ✓ API key set
  History        medium (last 50 messages)
  Trigger        manual                      ✓ Valid
  Prompt         450 chars

  Tools
    ✓ file_read (built-in)
    ✓ file_write (built-in)
    ✓ http_request (built-in)
    ✓ memory_append (built-in)
    ✓ memory_retrieve (built-in)
    ✓ memory_save (built-in)
```

---

## Tips

- **Start with defaults** — `history: low` is on by default; add memory tools to your prompt only when the agent needs them
- **Be explicit in prompts** — Tell the agent _when_ and _what_ to save to memory for best results
- **Organize by topic** — Use meaningful section names like `"user_preferences"`, not `"data"`
- **Summarize proactively** — Instruct agents to summarize long sections to keep memory focused
- **Memory is per-agent** — Each agent has its own `.memory.md` file; agents don't share memory
