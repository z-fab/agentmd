# Path Model

AgentMD agents declare the directories they need access to via the
`paths` field in the frontmatter. Each entry is a **named alias** that
the agent (and you, in the prompt) can reference using `{alias}` syntax.

## Declaring paths

Short form (string value, no description):

```yaml
paths:
  vault: /Users/zfab/FabBrain
  inbox: /Users/zfab/FabBrain/00_inbox
  output: ./output     # relative paths resolve from the workspace root
```

Full form (dict value with optional description):

```yaml
paths:
  vault:
    path: /Users/zfab/FabBrain
    description: main knowledge base
```

## Alias rules

- Aliases must match `[a-z][a-z0-9_]*`
- Reserved names: `workspace`, `skill_dir`, `today`, `now`, `agents`, `tools`, `skills`
- The `paths` field is the **sandbox** — file tools cannot access anything outside the union of declared paths

## Using aliases

In your agent prompt:

```markdown
Read the daily file at `{vault}/10_daily/2026-04-08.md` and save the
summary to `{vault}/30_notes/`.
```

In file tools (the LLM calls these — you don't have to):

```
file_read("{vault}/10_daily/2026-04-08.md")
file_write("{output}/summary.md", content)
file_glob("{vault}/**/*.md")
```

All file tools accept three forms:

| Form           | Example                                | Resolution                            |
|----------------|----------------------------------------|---------------------------------------|
| Alias          | `{vault}/x.md`                         | Expanded to the alias's absolute path |
| Absolute       | `/Users/zfab/FabBrain/x.md`            | Used as-is, sandbox-checked           |
| Relative       | `notes/x.md`                           | Resolved from the workspace root      |

## Migrating from the legacy list format

The list format used in v0.6.x is no longer accepted:

```yaml
# Old (v0.6.x) — NOT supported
paths:
  - /Users/zfab/FabBrain
  - /Users/zfab/FabBrain/00_inbox
```

Migrate to named aliases:

```yaml
# New (v0.7.0+)
paths:
  vault: /Users/zfab/FabBrain
  inbox: /Users/zfab/FabBrain/00_inbox
```

`agentmd validate` will detect the old format and print this hint.
