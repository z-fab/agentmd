# Spec 4 — Reorganização do workspace e estrutura do projeto

**Data:** 2026-04-11
**Autor:** zfab (via brainstorming session)
**Status:** proposto
**Release alvo:** v0.9.0 (breaking)

## Contexto

Com a implementação dos Specs 1–3 (path model, observability, HTTP backend),
o projeto cresceu organicamente. O módulo `core/` acumula 15 arquivos com
responsabilidades distintas. A estrutura do workspace mistura agentes com
infraestrutura (tools, skills, MCP config, .env). O banco de dados vive
dentro do workspace como se fosse dado do usuário, quando é estado de runtime.
Código de migração e backward-compat se acumulou sem necessidade.

Este spec propõe uma reorganização limpa: workspace simplificado, `core/`
desmembrado em subpacotes semânticos, e remoção de código legado.

## Objetivos

1. Workspace limpo: agentes `.md` separados da infraestrutura
2. DB e estado de runtime fora do workspace (em `~/.local/state/agentmd/`)
3. `core/` desmembrado em `config/`, `execution/`, `workspace/`
4. Setup wizard repaginado com configuração de defaults
5. Comando `new` com prompt AI melhorado
6. Remoção de código de migração e backward-compat
7. Limpeza do repositório git (remover `workspace/` antigo)

## Não-objetivos

- Migração automática de workspaces existentes (usuário recria via `setup`)
- Mudanças na API HTTP (endpoints permanecem iguais)
- Mudanças no formato dos agentes `.md`
- Mudanças no graph/LangGraph

## Design

### 1. Nova estrutura do workspace

```
~/agentmd/                          ← workspace root
├── agents/
│   ├── hello-world.md              ← agentes (.md files)
│   ├── my-agent.md
│   └── _config/                    ← infraestrutura (bloqueada pelo sandbox)
│       ├── .env                    ← API keys (workspace-specific)
│       ├── mcp-servers.json        ← MCP server config
│       ├── tools/                  ← custom tools (.py)
│       └── skills/                 ← skills (diretórios com SKILL.md)

~/.config/agentmd/
├── config.yaml                     ← configuração global
├── .env                            ← API keys (global fallback)
└── pricing.yaml                    ← override de preços (opcional)

~/.local/state/agentmd/
├── agentmd.db                      ← banco de execuções + logs
├── agentmd_checkpoints.db          ← checkpointer LangGraph
├── agentmd.sock                    ← Unix socket do backend
├── backend.log                     ← log do backend
└── backend.pid                     ← PID do backend
```

**Mudanças:**

- `data/` removida do workspace — DB migra para `~/.local/state/agentmd/`
- `.env` vai para `agents/_config/.env` (workspace) e `~/.config/agentmd/.env` (global)
- `mcp-servers.json` vai para `agents/_config/`
- `tools/` e `skills/` vão para `agents/_config/`
- `output/` não é criado por default (agentes declaram seus paths)
- Sandbox bloqueia `_config/` inteiro em vez de bloquear items individualmente

**Precedência de `.env`:**

1. `agents/_config/.env` (workspace) — prevalece (mais específico)
2. `~/.config/agentmd/.env` (global) — fallback

Ambos são carregados via `python-dotenv`. O workspace .env é carregado
depois do global, sobrescrevendo variáveis duplicadas.

**Regra de segurança:** ferramentas de arquivo NUNCA acessam `.env`,
independente de onde esteja. O check por `.env` no nome do arquivo
permanece no sandbox (já existe em `path_context.py`).

**config.yaml atualizado:**

```yaml
workspace: ~/agentmd
agents_dir: agents

# Esses são os novos defaults — não precisam estar no yaml
# db_path: removido (default: ~/.local/state/agentmd/agentmd.db)
# mcp_config: agents/_config/mcp-servers.json
# tools_dir: agents/_config/tools
# skills_dir: agents/_config/skills

defaults:
  provider: google
  model: gemini-2.5-flash
  max_tool_calls: 50
  max_cost_usd:
  timeout: 300
```

### 2. Reorganização do `agent_md/`

O módulo `core/` (15 arquivos, 2580 linhas) é desmembrado em 3 subpacotes:

```
agent_md/
├── config/                    ← "o que" — configuração e modelos
│   ├── __init__.py
│   ├── settings.py            (Settings, load .env, config.yaml)
│   ├── models.py              (AgentConfig, ModelConfig, TriggerConfig, etc)
│   ├── pricing.py             (estimate_cost, load_pricing)
│   ├── env.py                 (resolve_env_vars)
│   └── substitutions.py       (apply_substitutions)
│
├── execution/                 ← "roda" — runtime de execução
│   ├── __init__.py
│   ├── runner.py              (AgentRunner, LimitExceeded, _check_limits)
│   ├── logger.py              (ExecutionLogger — renomeado de execution_logger)
│   ├── event_bus.py           (EventBus)
│   └── lifecycle.py           (LifecycleManager)
│
├── workspace/                 ← "gerencia" — gestão do workspace
│   ├── __init__.py
│   ├── bootstrap.py           (bootstrap(), Runtime dataclass)
│   ├── registry.py            (AgentRegistry)
│   ├── parser.py              (parse_agent_file, is_agent_file)
│   ├── path_context.py        (PathContext, sandbox validation)
│   ├── scheduler.py           (AgentScheduler, watchers)
│   └── services.py            (run_agent, validate_agent, chat_session, etc)
│
├── api/                       (sem mudanças estruturais)
├── cli/                       (imports atualizados)
├── db/                        (sem mudanças estruturais)
├── graph/                     (sem mudanças estruturais)
├── mcp/                       (sem mudanças estruturais)
├── providers/                 (sem mudanças estruturais)
├── skills/                    (sem mudanças estruturais)
└── tools/                     (sem mudanças estruturais)
```

**Sem backward-compat:** `agent_md/core/` é removido completamente.
Todos os imports são atualizados. É breaking change documentada na v0.9.0.

**Impacto nos imports (exemplos):**

| Antes | Depois |
|---|---|
| `agent_md.core.runner` | `agent_md.execution.runner` |
| `agent_md.core.models` | `agent_md.config.models` |
| `agent_md.core.settings` | `agent_md.config.settings` |
| `agent_md.core.bootstrap` | `agent_md.workspace.bootstrap` |
| `agent_md.core.path_context` | `agent_md.workspace.path_context` |
| `agent_md.core.execution_logger` | `agent_md.execution.logger` |
| `agent_md.core.event_bus` | `agent_md.execution.event_bus` |
| `agent_md.core.scheduler` | `agent_md.workspace.scheduler` |
| `agent_md.core.services` | `agent_md.workspace.services` |
| `agent_md.core.registry` | `agent_md.workspace.registry` |
| `agent_md.core.parser` | `agent_md.workspace.parser` |
| `agent_md.core.pricing` | `agent_md.config.pricing` |
| `agent_md.core.env` | `agent_md.config.env` |
| `agent_md.core.substitutions` | `agent_md.config.substitutions` |
| `agent_md.core.lifecycle` | `agent_md.execution.lifecycle` |

### 3. Setup wizard repaginado

Fluxo em 4 passos com UI limpa:

**Passo 1/4 — Workspace:** onde criar o workspace (default `~/agentmd`)

**Passo 2/4 — LLM Provider:** seleção de provider com model default
(google, openai, anthropic, ollama)

**Passo 3/4 — API Key:** input da key, validação opcional. Pular se ollama.

**Passo 4/4 — Defaults:** configuração opcional de limites de execução.
Exibe valores default e permite alterar:
- Max tool calls per run (default: 50)
- Max cost per run em USD (default: none)
- Timeout em seconds (default: 300)

**Pós-setup:**
- Cria estrutura do workspace: `agents/`, `agents/_config/tools/`,
  `agents/_config/skills/`
- Escreve `config.yaml` em `~/.config/agentmd/`
- Escreve `.env` em `agents/_config/.env` (workspace) E
  `~/.config/agentmd/.env` (global, para primeira instalação)
- Cria `agents/_config/mcp-servers.json` vazio
- Cria `agents/hello-world.md` com agente de exemplo
- Sugere `agentmd new my-first-agent` como próximo passo

**Remove:** pergunta sobre auto-start (feature pouco usada)

### 4. Comando `new` melhorado

**Prompt AI:**

O prompt atual lista tools específicas (`file_read`, `file_write`, etc).
Substituir por descrição de **capacidades**:

- Ler, escrever e editar arquivos dentro dos paths declarados
- Buscar arquivos por padrão glob
- Fazer requisições HTTP
- Memória persistente entre execuções (save, append, retrieve por seção)

Os nomes e assinaturas das tools já são injetados no system prompt pelo
builder — o prompt do `new` não precisa duplicar.

Incluir no prompt:
- Que o default de `history` é `"low"` (10 mensagens entre runs)
- Que `paths` define os diretórios que o agente pode acessar
- Que custom tools ficam em `agents/_config/tools/`

**Template interativo (`--template`):**

Simplificar para 3 perguntas:
1. Descrição (o que o agente faz)
2. Trigger (manual/schedule/watch)
3. Paths (diretórios que precisa acessar)

Não perguntar provider/model — usa o default do config.yaml.
Gerar prompt com instruções claras baseadas na descrição.

### 5. Sandbox (path_context.py)

**Regra simplificada:** bloquear `agents/_config/` inteiro.

```python
def _check_security(self, resolved: Path) -> str | None:
    config_dir = self.agents_dir / "_config"
    if self._is_within(resolved, config_dir):
        return "Access denied: cannot access _config directory"
    if resolved.name.startswith(".env"):
        return "Access denied: cannot access .env files"
    if resolved.suffix == ".db":
        return "Access denied: cannot access .db files"
    return None
```

Remove checks separados para `agents_dir` e `data/` directory.
O `.env` check permanece como safety net (mesmo fora de `_config/`).
O `.db` check permanece (mesmo que DB esteja fora do workspace agora).

### 6. Remoção de código legado

**database.py:**
- Remover `MIGRATIONS` list e o loop de ALTER TABLE no `connect()`
- Schema direto com todas as colunas (cost_usd, pid já estão no CREATE TABLE)

**skills/loader.py:**
- Remover backward-compat shim (`skill_dir` → `cwd` mapping)

**cli/commands.py:**
- Remover backward compat para args com `/` ou `.md` no comando `validate`

**core/models.py:**
- Remover mensagem de migração no validador de `paths` (rejeitar lista
  sem instruções de "Migrate from")

### 7. Limpeza do repositório git

- `git rm -r workspace/` — remove pasta antiga do GitHub
- Limpar `.gitignore`: remover entradas de `workspace/output/`,
  `workspace/config.yaml`, `workspace/agents/*`,
  `!workspace/agents/hello-world.md`
- Manter `.env` e `*.env*` no `.gitignore`

### 8. Testes

Pré-requisito: garantir cobertura de testes antes do refactor de imports.

- Rodar `pytest` completo antes e depois do refactor
- Atualizar todos os imports nos testes existentes
- Novos testes:
  - `.env` precedence (workspace > global)
  - Sandbox bloqueia `_config/` inteiro
  - `setup` cria estrutura nova corretamente
  - DB path resolve para `~/.local/state/agentmd/`
  - `new` gera agente válido com o prompt atualizado

## Arquivos tocados

**Novos:**
- `agent_md/config/__init__.py`
- `agent_md/execution/__init__.py`
- `agent_md/workspace/__init__.py`

**Movidos (de `agent_md/core/` para subpacotes):**
- Todos os 15 arquivos de `core/` → redistribuídos conforme seção 2

**Removidos:**
- `agent_md/core/` (inteiro)
- `workspace/` (do git)

**Modificados:**
- Todos os arquivos que importam de `agent_md.core.*` (~30 arquivos)
- `agent_md/cli/setup.py` (wizard repaginado)
- `agent_md/cli/commands.py` (comando `new`, remoção de compat)
- `agent_md/db/database.py` (remoção de MIGRATIONS)
- `agent_md/workspace/path_context.py` (sandbox simplificado)
- `agent_md/config/settings.py` (novos defaults, .env loading)
- `.gitignore` (limpeza)
- `pyproject.toml` (version bump 0.9.0)
- `CHANGELOG.md`
- `README.md`
- `docs/migration-0.9.md` (novo)

## Riscos

- **Import breakage massivo** — mitigação: rodar pytest antes e depois,
  usar grep para encontrar todos os imports
- **DB migration perdida** — mitigação: usuários recriam via `setup`,
  documentado no migration guide
- **Skills/tools em novo path** — mitigação: `agentmd validate` avisa
  se tools não forem encontrados no novo path
