# Providers

Agent.md supports five LLM providers: Google, OpenAI, Anthropic, Ollama, and Local (self-hosted). Each provider is an optional dependency—install only what you need.

## Supported Providers

| Provider | Package | Default Model |
|----------|---------|---------------|
| `google` | `langchain-google-genai` | `gemini-2.5-flash` |
| `openai` | `langchain-openai` | `gpt-4o` |
| `anthropic` | `langchain-anthropic` | `claude-sonnet-4` |
| `ollama` | `langchain-ollama` | User-defined |
| `local` | `langchain-openai` | User-defined |

## Installation

### Core Installation

```bash
pip install agentmd
# or with uv:
uv pip install agentmd
```

### Provider-Specific Installation

```bash
# OpenAI
pip install agentmd[openai]

# Anthropic
pip install agentmd[anthropic]

# Ollama
pip install agentmd[ollama]

# All providers
pip install agentmd[all]
```

**Note:** The `local` provider uses the same package as OpenAI (`langchain-openai`).

## API Key Setup

Create a `.env` file in your project root:

```bash
GOOGLE_API_KEY=your-key-here
OPENAI_API_KEY=your-key-here
ANTHROPIC_API_KEY=your-key-here
```

Agent.md automatically loads `.env` at startup via `python-dotenv`.

### Get Your API Keys

- **Google**: [Google AI Studio](https://aistudio.google.com/app/apikey)
- **OpenAI**: [OpenAI Platform](https://platform.openai.com/api-keys)
- **Anthropic**: [Anthropic Console](https://console.anthropic.com/settings/keys)

Ollama and Local providers don't require API keys.

## Google

Fast, cost-effective, multimodal—best for high-frequency tasks.

**Installation:**
```bash
pip install agentmd
# Google is included by default
```

**Configuration:**

```yaml
model:
  provider: google
  name: gemini-2.5-flash
```

**Available models:**
- `gemini-2.5-flash` — Fast, multimodal (recommended)
- `gemini-2.5-pro` — More capable, larger context
- `gemini-2.0-flash-exp` — Experimental

**Example:**

```yaml
---
name: quick-summarizer
model:
  provider: google
  name: gemini-2.5-flash
trigger:
  type: manual
settings:
  temperature: 0.3
---

Summarize the file at `input.txt` and save to `summary.txt`.
```

## OpenAI

Versatile, excellent reasoning—industry standard for complex tasks.

**Installation:**
```bash
pip install agentmd[openai]
```

**Configuration:**

```yaml
model:
  provider: openai
  name: gpt-4o
```

**Available models:**
- `gpt-4o` — Latest flagship
- `gpt-4o-mini` — Faster, cheaper
- `gpt-4-turbo` — Previous generation
- `o1` / `o1-mini` — Advanced reasoning

**Example:**

```yaml
---
name: research-assistant
model:
  provider: openai
  name: gpt-4o
trigger:
  type: manual
settings:
  temperature: 0.7
  max_tokens: 8192
---

Research the topic in `query.txt` and write a comprehensive report.
```

## Anthropic

Long context (200K+ tokens), excellent for detailed analysis.

**Installation:**
```bash
pip install agentmd[anthropic]
```

**Configuration:**

```yaml
model:
  provider: anthropic
  name: claude-sonnet-4
```

**Available models:**
- `claude-sonnet-4` — Balanced performance
- `claude-opus-4` — Highest capability
- `claude-haiku-4` — Fast and efficient

**Example:**

```yaml
---
name: document-analyzer
model:
  provider: anthropic
  name: claude-sonnet-4
trigger:
  type: manual
settings:
  temperature: 0.5
  max_tokens: 4096
---

Analyze the legal document in `contract.txt` and extract key terms.
```

## Ollama

Local, offline, privacy-first. No API key required.

**Setup:**

1. Install Ollama: [ollama.com/download](https://ollama.com/download)
2. Pull a model: `ollama pull llama3.2`
3. Ollama runs at `http://localhost:11434` by default

**Installation:**
```bash
pip install agentmd[ollama]
```

**Configuration:**

```yaml
model:
  provider: ollama
  name: llama3.2
```

**Popular models:**
- `llama3.2` — Meta's Llama (3B, 7B, 70B variants)
- `mistral` — Mistral 7B
- `phi3` — Microsoft Phi-3 (small)
- `gemma2` — Google Gemma 2

Browse all: [ollama.com/library](https://ollama.com/library)

**Example:**

```yaml
---
name: private-summarizer
model:
  provider: ollama
  name: llama3.2
trigger:
  type: manual
settings:
  temperature: 0.7
---

Summarize confidential files without sending data to external APIs.
```

## Local (OpenAI-Compatible)

Self-hosted or third-party OpenAI-compatible endpoints (vLLM, LM Studio, LocalAI).

**Installation:**
```bash
pip install agentmd[openai]
```

**Configuration:**

```yaml
model:
  provider: local
  name: your-model-name
  base_url: http://localhost:8000
```

The `base_url` is automatically normalized (e.g., `http://localhost:8000` becomes `http://localhost:8000/v1`).

**Common endpoints:**
- **vLLM**: `http://localhost:8000`
- **LM Studio**: `http://localhost:1234`
- **LocalAI**: `http://localhost:8080`

**Example:**

```yaml
---
name: custom-model-agent
model:
  provider: local
  name: my-fine-tuned-model
  base_url: http://localhost:8000
trigger:
  type: manual
---

Use your custom fine-tuned model hosted on vLLM.
```

## Common Settings

All providers support:

```yaml
settings:
  temperature: 0.7      # 0.0 = deterministic, 1.0 = creative
  max_tokens: 4096      # Maximum output tokens
  timeout: 300          # Execution timeout in seconds
```

### Temperature Guide

- `0.0` — Deterministic (data extraction, structured outputs)
- `0.3` — Focused (summaries, factual tasks)
- `0.7` — Balanced (general-purpose, default)
- `0.9` — Creative (writing, brainstorming)

## Provider Features

| Feature | Google | OpenAI | Anthropic | Ollama | Local |
|---------|--------|--------|-----------|--------|-------|
| Online API | ✓ | ✓ | ✓ | — | — |
| Local/Offline | — | — | — | ✓ | ✓ |
| Long context (200K+) | — | — | ✓ | Depends | Depends |
| Multimodal | ✓ | ✓ | Partial | Some | Depends |
| Reasoning models | — | ✓ | — | — | — |
| No API cost | — | — | — | ✓ | ✓ |

## Switching Providers

Change providers by editing the agent file:

```yaml
# Before
model:
  provider: openai
  name: gpt-4o

# After
model:
  provider: google
  name: gemini-2.5-flash
```

Save and run—the next execution uses the new provider.

## Troubleshooting

### Provider Package Not Installed

```
ImportError: Provider 'openai' requires langchain-openai.
```

**Solution:**
```bash
pip install agentmd[openai]
```

### API Key Not Found

```
Error: OPENAI_API_KEY not found
```

**Solution:**
1. Create `.env` in project root
2. Add: `OPENAI_API_KEY=your-key`
3. Restart the runtime

### Ollama Connection Error

```
Error: Could not connect to Ollama at http://localhost:11434
```

**Solution:**
1. Install Ollama: [ollama.com/download](https://ollama.com/download)
2. Start Ollama: `ollama serve`
3. Pull a model: `ollama pull llama3.2`

### Local Provider 404 Error

```
Error: 404 Not Found at http://localhost:8000/v1/chat/completions
```

**Solution:**
- Verify your server is running
- Check the correct port (vLLM: 8000, LM Studio: 1234)
- Ensure `/v1` is in the path (auto-added by Agent.md)

### Token Limit Exceeded

```
Error: maximum context length exceeded
```

**Solution:**
- Reduce `max_tokens` in settings
- Use a model with a larger context window
- Split large inputs into smaller chunks

## Quick Start

1. **For development:** Use Google Gemini Flash (fast, free tier available)
2. **For sensitive data:** Use Ollama (local, no API calls)
3. **For complex tasks:** Use OpenAI GPT-4o or Anthropic Claude
4. **Test locally first** with Ollama before deploying to cloud APIs
