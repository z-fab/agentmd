# Skills

Skills are reusable instruction packages that give agents specialized capabilities. Each skill is a directory with a `SKILL.md` file containing YAML frontmatter and markdown instructions, following the [Agent Skills](https://agentskills.io) standard.

## How Skills Work

Skills use a **two-tier loading** pattern for efficiency:

1. **Discovery** (at startup) — Only skill names and descriptions are loaded into the agent's system prompt
2. **Activation** (on demand) — When the agent calls `skill_use`, the full instructions are loaded with variable substitutions applied

This keeps the system prompt lightweight while giving agents access to detailed instructions when needed.

## Creating a Skill

### Directory Structure

```
workspace/agents/skills/
└── my-skill/
    ├── SKILL.md              # Required: instructions + metadata
    ├── scripts/              # Optional: executable scripts
    │   └── helper.py
    └── references/           # Optional: documentation files
        └── api-docs.md
```

### SKILL.md Format

```yaml
---
name: my-skill
description: What this skill does and when to use it
argument-hint: "[args]"
---

# Instructions

Your markdown instructions here...

Use $ARGUMENTS for user-provided arguments.
Use ${SKILL_DIR} for the skill directory path.
Dynamic data: !`shell command`
```

### Frontmatter Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | directory name | Skill identifier (alphanumeric, hyphens, underscores) |
| `description` | string | `""` | What the skill does — shown in the agent's system prompt |
| `argument-hint` | string | `""` | Hint shown to the agent (e.g., `"[issue-number]"`) |
| `user-invocable` | bool | `true` | Whether the skill is available for use |

!!! tip
    Write clear, assertive descriptions. The description is what the agent sees to decide when to use a skill.

## Enabling Skills on an Agent

Add the `skills` field to your agent's frontmatter:

```yaml
---
name: my-agent
skills:
  - analyze-pr
  - generate-report
---

You are an assistant. Use your skills when appropriate.
```

The agent's system prompt will include:

```
## Available Skills

- **analyze-pr** [pr-number]: Analyze a GitHub pull request
- **generate-report**: Generate a formatted report

Use the `skill_use` tool to load a skill's full instructions when needed.
```

## Variable Substitution

Skills support variable replacement in their instructions, processed when `skill_use` is called.

### `$ARGUMENTS`

Replaced with the full arguments string passed to `skill_use`:

```markdown
Analyze pull request #$ARGUMENTS
```

Calling `skill_use("my-skill", "123")` produces: `Analyze pull request #123`

### `$ARGUMENTS[N]` / `$N`

Access individual arguments by index (0-based):

```markdown
Compare $ARGUMENTS[0] with $ARGUMENTS[1]
```

Calling `skill_use("my-skill", "main develop")` produces: `Compare main with develop`

### `${SKILL_DIR}`

Replaced with the absolute path to the skill directory:

```markdown
Run: python ${SKILL_DIR}/scripts/analyze.py
```

### `` !`command` `` — Dynamic Context Injection

Shell commands are executed and their output injected before the agent sees the content:

```markdown
Current branch: !`git branch --show-current`
Last commit: !`git log -1 --oneline`
```

Commands run with the skill directory as working directory, with a 10-second timeout.

## Built-in Skill Tools

When an agent has skills enabled, three tools are automatically available:

### `skill_use`

Load a skill's full instructions.

```python
skill_use(skill_name: str, arguments: str = "") -> str
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `skill_name` | str | Yes | Name of the skill |
| `arguments` | str | No | Arguments for variable substitution |

Returns the processed instructions with all substitutions applied, plus lists of available scripts and references.

### `skill_read_file`

Read a supporting file from a skill's directory.

```python
skill_read_file(skill_name: str, file_path: str) -> str
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `skill_name` | str | Yes | Name of the skill |
| `file_path` | str | Yes | Relative path within skill directory |

Security: paths are validated to be within the skill directory — traversal attempts are blocked.

### `skill_run_script`

Execute a script from a skill's `scripts/` directory.

```python
skill_run_script(skill_name: str, script_name: str, script_args: str = "") -> str
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `skill_name` | str | Yes | Name of the skill |
| `script_name` | str | Yes | Script filename in `scripts/` |
| `script_args` | str | No | Arguments to pass to the script |

Supports `.py`, `.sh`, `.bash`, `.js` scripts. Runs with a 30-second timeout.

## Claude Code Compatibility

Skills follow the [Agent Skills](https://agentskills.io) standard and are compatible with Claude Code. To use a Claude Code skill:

1. Copy the skill directory from `.claude/skills/<name>/` to `workspace/agents/skills/<name>/`
2. Add the skill name to your agent's `skills` list
3. Run your agent — it should work with no changes

**Supported features:**

- `SKILL.md` format (YAML frontmatter + markdown)
- Directory structure (`scripts/`, `references/`)
- Variable substitution (`$ARGUMENTS`, `${SKILL_DIR}`)
- Dynamic context injection (`` !`command` ``)
- Hyphenated YAML keys (`argument-hint`, `user-invocable`)

## Example: Code Review Skill

```
workspace/agents/skills/review-code/
├── SKILL.md
├── scripts/
│   └── lint.sh
└── references/
    └── style-guide.md
```

**SKILL.md:**
```yaml
---
name: review-code
description: Review code for quality, style, and potential issues. Use when asked to review code or PRs.
argument-hint: "[file-or-pr]"
---

# Code Review

Review $ARGUMENTS for code quality.

## Steps

1. Read the style guide: `skill_read_file("review-code", "references/style-guide.md")`
2. Run the linter: `skill_run_script("review-code", "lint.sh", "$ARGUMENTS")`
3. Analyze the code for:
   - Correctness and edge cases
   - Style consistency
   - Performance concerns
   - Security issues
4. Provide a summary with actionable feedback
```

**Agent using it:**
```yaml
---
name: code-assistant
skills:
  - review-code
---

You are a senior developer. Use your skills to help with code tasks.
```

## Security

- Agents can only use skills listed in their `skills` field
- `skill_read_file` validates paths are within the skill directory (no traversal)
- `skill_run_script` only executes from `scripts/` subdirectory
- Shell commands in `` !`command` `` run with skill directory as cwd, with timeout

## Related Documentation

- [Built-in Tools](tools/built-in-tools.md) — All available tools
- [Agent Configuration](agent-configuration.md) — The `skills` field
- [Architecture](architecture.md) — How skills integrate
