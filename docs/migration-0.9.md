# Migration Guide: v0.8.x → v0.9.0

## Breaking Changes

### Workspace restructured

Tools, skills, MCP config, and .env are now inside `agents/_config/`:

```
agents/
├── my-agent.md
└── _config/
    ├── .env
    ├── mcp-servers.json
    ├── tools/
    └── skills/
```

### Database moved

The database is now stored in `~/.local/state/agentmd/` instead of `workspace/data/`. Previous execution history is not migrated.

### Import paths changed

All `agent_md.core.*` imports have been reorganized:

| Old | New |
|-----|-----|
| `agent_md.core.runner` | `agent_md.execution.runner` |
| `agent_md.core.models` | `agent_md.config.models` |
| `agent_md.core.settings` | `agent_md.config.settings` |
| `agent_md.core.bootstrap` | `agent_md.workspace.bootstrap` |
| `agent_md.core.services` | `agent_md.workspace.services` |
| `agent_md.core.execution_logger` | `agent_md.execution.logger` |
| `agent_md.core.path_context` | `agent_md.workspace.path_context` |
| `agent_md.core.scheduler` | `agent_md.workspace.scheduler` |
| `agent_md.core.event_bus` | `agent_md.execution.event_bus` |

### All defaults configurable

`config.yaml` now supports all agent defaults:

```yaml
defaults:
  provider: google
  model: gemini-2.5-flash
  temperature: 0.7
  max_tokens: 4096
  timeout: 300
  max_tool_calls: 50
  max_execution_tokens: 500000
  loop_detection: true
  history: low
```

### How to upgrade

1. Back up your agents: `cp ~/agentmd/agents/*.md /tmp/backup/`
2. Run `agentmd setup`
3. Copy agents back: `cp /tmp/backup/*.md ~/agentmd/agents/`
4. Move custom tools: `cp -r /old/tools/ ~/agentmd/agents/_config/tools/`
5. Move skills: `cp -r /old/skills/ ~/agentmd/agents/_config/skills/`
