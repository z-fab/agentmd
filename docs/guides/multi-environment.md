# Multi-Environment Setup

Configure and manage Agent.md across development, staging, and production environments.

## Overview

Multi-environment setup enables:

1. **Safe testing** - Test changes in dev/staging before production
2. **Isolation** - Each environment has separate data, secrets, and configs
3. **Cost control** - Use cheaper models in dev, production models in prod
4. **Security** - Production secrets never exposed to dev
5. **Debugging** - Test with verbose logging in dev, silent in prod

## Environment Strategy

### Three-Environment Setup

```
Development (dev)
  ↓ Test and iterate
Staging (staging)
  ↓ Final validation
Production (prod)
  ↓ Live agents
```

**Characteristics:**

| Environment | Purpose | LLM Model | Schedule | Logging | Cost |
|-------------|---------|-----------|----------|---------|------|
| **Dev** | Rapid iteration | Cheap/local | Manual only | Verbose | Low |
| **Staging** | Pre-prod testing | Same as prod | Less frequent | Normal | Medium |
| **Prod** | Live operations | Best quality | As needed | Silent | High |

## Directory Structure

### Workspace Organization

```
agentmd/
├── .env.dev              # Dev environment vars
├── .env.staging          # Staging environment vars
├── .env.production       # Production environment vars (gitignored)
├── .env.example          # Template (committed)
│
├── workspace/
│   ├── dev/              # Development agents
│   │   ├── test-agent.md
│   │   └── experiment.md
│   ├── staging/          # Staging agents
│   │   ├── daily-report.md
│   │   └── log-monitor.md
│   └── production/       # Production agents
│       ├── daily-report.md
│       └── log-monitor.md
│
├── output/
│   ├── dev/              # Dev outputs
│   ├── staging/          # Staging outputs
│   └── production/       # Production outputs
│
└── data/
    ├── dev/              # Dev databases
    ├── staging/          # Staging databases
    └── production/       # Production databases
```

### Git Configuration

**`.gitignore`:**
```bash
# Environment files with secrets
.env.dev
.env.staging
.env.production

# Keep example template
!.env.example

# Environment-specific outputs
output/dev/
output/staging/
output/production/

# Environment-specific data
data/dev/
data/staging/
data/production/
```

**`.env.example` (committed):**
```bash
# LLM Provider
OPENAI_API_KEY=sk-proj-your-key-here
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Agent.md Runtime
WORKSPACE_DIR=/workspace/production
OUTPUT_DIR=/output/production
DATABASE_PATH=/data/production/executions.db

# Environment
ENVIRONMENT=production
LOG_LEVEL=INFO
```

## Environment Configuration Files

### Development (`.env.dev`)

```bash
# Environment
ENVIRONMENT=dev
LOG_LEVEL=DEBUG

# Paths
WORKSPACE_DIR=/workspace/dev
OUTPUT_DIR=/output/dev
DATABASE_PATH=/data/dev/executions.db

# LLM - Use cheap/local models
OPENAI_API_KEY=sk-proj-dev-key
DEFAULT_PROVIDER=ollama
DEFAULT_MODEL=llama3.1:8b

# External services - Point to dev/mock APIs
API_BASE_URL=http://localhost:3000
SLACK_WEBHOOK=https://hooks.slack.com/services/DEV/WEBHOOK

# Limits - Generous for testing
MAX_ITERATIONS=20
TIMEOUT=600
MAX_TOKENS=4000

# Cost control
ENABLE_EXPENSIVE_MODELS=false
```

### Staging (`.env.staging`)

```bash
# Environment
ENVIRONMENT=staging
LOG_LEVEL=INFO

# Paths
WORKSPACE_DIR=/workspace/staging
OUTPUT_DIR=/output/staging
DATABASE_PATH=/data/staging/executions.db

# LLM - Use production models but with reduced usage
OPENAI_API_KEY=sk-proj-staging-key
DEFAULT_PROVIDER=openai
DEFAULT_MODEL=gpt-3.5-turbo

# External services - Point to staging APIs
API_BASE_URL=https://staging-api.example.com
SLACK_WEBHOOK=https://hooks.slack.com/services/STAGING/WEBHOOK

# Limits - Same as prod
MAX_ITERATIONS=10
TIMEOUT=300
MAX_TOKENS=2000

# Cost control
ENABLE_EXPENSIVE_MODELS=true
```

### Production (`.env.production`)

```bash
# Environment
ENVIRONMENT=production
LOG_LEVEL=WARNING

# Paths
WORKSPACE_DIR=/workspace/production
OUTPUT_DIR=/output/production
DATABASE_PATH=/data/production/executions.db

# LLM - Use production keys and models
OPENAI_API_KEY=sk-proj-prod-key-REAL-SECRET
ANTHROPIC_API_KEY=sk-ant-prod-key-REAL-SECRET
DEFAULT_PROVIDER=openai
DEFAULT_MODEL=gpt-4

# External services - Live APIs
API_BASE_URL=https://api.example.com
SLACK_WEBHOOK=https://hooks.slack.com/services/PROD/WEBHOOK
DATABASE_URL=postgresql://prod-user:REAL-SECRET@prod-db:5432/agents

# Limits - Strict
MAX_ITERATIONS=5
TIMEOUT=180
MAX_TOKENS=1000

# Security
ENABLE_EXPENSIVE_MODELS=true
REQUIRE_APPROVAL=true
```

## Environment-Specific Agent Configurations

### Development Agent

**`workspace/dev/test-agent.md`:**
```yaml
---
name: test-agent
model:
  provider: ollama
  name: llama3.1:8b  # Free local model
  temperature: 0.5
  max_tokens: 4000   # High limit for testing
settings:
  max_iterations: 20  # Allow more iterations for debugging
  timeout: 600        # 10 minute timeout
  log_level: DEBUG    # Verbose logging
paths:
  read: ["/workspace/dev/data/"]
  write: ["/output/dev/"]
triggers:
  - type: manual  # Only run manually in dev
---

Test agent for development. This can have verbose instructions
and detailed logging. Cost doesn't matter here.

Use this to test new features, iterate on prompts, and debug issues.
```

### Staging Agent

**`workspace/staging/daily-report.md`:**
```yaml
---
name: daily-report
model:
  provider: openai
  name: gpt-3.5-turbo  # Cheaper than prod but still cloud-based
  temperature: 0.3
  max_tokens: 1500
settings:
  max_iterations: 10
  timeout: 300
  log_level: INFO
paths:
  read: ["/workspace/staging/data/"]
  write: ["/output/staging/reports/"]
triggers:
  - type: schedule
    cron: "0 10 * * *"  # Run once daily in staging (different time than prod)
---

Generate daily report. This is the staging version - same prompt
as production, but running against staging data and APIs.
```

### Production Agent

**`workspace/production/daily-report.md`:**
```yaml
---
name: daily-report
model:
  provider: openai
  name: gpt-4  # Best quality for production
  temperature: 0.1
  max_tokens: 1000  # Strict limit
settings:
  max_iterations: 5
  timeout: 180
  log_level: WARNING  # Only log warnings/errors
paths:
  read: ["/workspace/production/data/"]
  write: ["/output/production/reports/"]
triggers:
  - type: schedule
    cron: "0 8 * * *"  # 8 AM daily in production
---

Generate daily report. Concise prompt, optimized for cost and reliability.
```

## CLI Environment Overrides

### Load Specific Environment

```bash
# Development
export ENV_FILE=.env.dev
source .env.dev
agentmd start

# Staging
export ENV_FILE=.env.staging
source .env.staging
agentmd start

# Production
export ENV_FILE=.env.production
source .env.production
agentmd start
```

### Override Workspace Directory

```bash
# Run dev agent
agentmd run test-agent --workspace /workspace/dev

# Run staging agent
agentmd run daily-report --workspace /workspace/staging

# Run production agent
agentmd run daily-report --workspace /workspace/production
```

### Override Model at Runtime

```bash
# Test production agent with dev model
agentmd run daily-report \
  --workspace /workspace/production \
  --model ollama \
  --model-name llama3.1:8b

# Test with verbose logging
agentmd run daily-report \
  --workspace /workspace/production \
  --verbose \
  --debug
```

### One-Time Environment Variable

```bash
# Override API key for single run
OPENAI_API_KEY=sk-test-key agentmd run test-agent

# Override output directory
OUTPUT_DIR=/tmp/test-output agentmd run test-agent
```

## Database Separation

### Separate Databases per Environment

**Development database:**
```bash
DATABASE_PATH=/data/dev/executions.db
```

**Staging database:**
```bash
DATABASE_PATH=/data/staging/executions.db
```

**Production database:**
```bash
DATABASE_PATH=/data/production/executions.db
```

### Why Separate Databases?

1. **Isolation** - Dev experiments don't pollute prod logs
2. **Performance** - Prod database stays small and fast
3. **Debugging** - Clear separation of test vs real executions
4. **Compliance** - Production audit trail is separate

### Backup Production Database

```bash
# Backup production database
sqlite3 /data/production/executions.db ".backup /backups/executions-$(date +%Y%m%d).db"

# Restore from backup
sqlite3 /data/production/executions.db ".restore /backups/executions-20260311.db"
```

### Copy Staging to Dev

```bash
# Copy staging database to dev for testing
cp /data/staging/executions.db /data/dev/executions.db

# Now dev has staging's execution history
```

## Environment Promotion Workflow

### 1. Develop in Dev

```bash
# Switch to dev environment
source .env.dev

# Create agent
cat > workspace/dev/new-feature.md << 'EOF'
---
name: new-feature
model:
  provider: ollama
  name: llama3.1:8b
---
New feature under development.
EOF

# Test
agentmd run new-feature --verbose
```

### 2. Promote to Staging

```bash
# Copy agent to staging
cp workspace/dev/new-feature.md workspace/staging/new-feature.md

# Update for staging
vim workspace/staging/new-feature.md
# Change model to gpt-3.5-turbo
# Update paths to /workspace/staging/
# Update schedule if needed

# Switch to staging environment
source .env.staging

# Test in staging
agentmd run new-feature --verbose

# If tests pass, commit
git add workspace/staging/new-feature.md
git commit -m "Add new-feature agent to staging"
git push origin staging
```

### 3. Promote to Production

```bash
# Copy agent to production
cp workspace/staging/new-feature.md workspace/production/new-feature.md

# Update for production
vim workspace/production/new-feature.md
# Change model to gpt-4 (or appropriate prod model)
# Update paths to /workspace/production/
# Set strict limits (max_tokens, timeout, max_iterations)
# Reduce log_level to WARNING

# Switch to production environment
source .env.production

# Dry run
agentmd run new-feature --dry-run

# If dry run passes, commit
git add workspace/production/new-feature.md
git commit -m "Deploy new-feature agent to production"
git push origin main

# Deploy (see deployment section)
```

## Environment Switcher Script

**`scripts/env.sh`:**
```bash
#!/bin/bash
# Usage: source scripts/env.sh dev|staging|production

ENV=$1

if [ -z "$ENV" ]; then
  echo "Usage: source scripts/env.sh dev|staging|production"
  return 1
fi

case $ENV in
  dev)
    export ENV_FILE=.env.dev
    ;;
  staging)
    export ENV_FILE=.env.staging
    ;;
  production)
    export ENV_FILE=.env.production
    ;;
  *)
    echo "Unknown environment: $ENV"
    return 1
    ;;
esac

# Load environment
set -a
source $ENV_FILE
set +a

echo "Switched to $ENV environment"
echo "  WORKSPACE_DIR: $WORKSPACE_DIR"
echo "  OUTPUT_DIR: $OUTPUT_DIR"
echo "  DATABASE_PATH: $DATABASE_PATH"
echo "  DEFAULT_MODEL: $DEFAULT_MODEL"
```

**Usage:**
```bash
# Switch to dev
source scripts/env.sh dev

# Switch to staging
source scripts/env.sh staging

# Switch to production
source scripts/env.sh production
```

## Testing Across Environments

### Validation Script

**`scripts/validate-all.sh`:**
```bash
#!/bin/bash
# Validate agents in all environments

echo "Validating dev agents..."
for agent in workspace/dev/*.md; do
  agentmd validate "$agent" || exit 1
done

echo "Validating staging agents..."
for agent in workspace/staging/*.md; do
  agentmd validate "$agent" || exit 1
done

echo "Validating production agents..."
for agent in workspace/production/*.md; do
  agentmd validate "$agent" || exit 1
done

echo "All agents validated successfully!"
```

### Integration Tests

**`scripts/test-staging.sh`:**
```bash
#!/bin/bash
# Run all staging agents and check for errors

source .env.staging

for agent in workspace/staging/*.md; do
  agent_name=$(basename "$agent" .md)
  echo "Testing $agent_name..."

  agentmd run "$agent_name" --workspace /workspace/staging

  if [ $? -ne 0 ]; then
    echo "FAILED: $agent_name"
    exit 1
  fi
done

echo "All staging agents passed!"
```

### Smoke Tests

**`scripts/smoke-test-prod.sh`:**
```bash
#!/bin/bash
# Quick smoke test of production agents

source .env.production

# Test each agent with dry-run
for agent in workspace/production/*.md; do
  agent_name=$(basename "$agent" .md)
  echo "Smoke testing $agent_name..."

  agentmd run "$agent_name" --dry-run

  if [ $? -ne 0 ]; then
    echo "FAILED: $agent_name"
    exit 1
  fi
done

echo "Production smoke tests passed!"
```

## Cost Monitoring

### Track Costs by Environment

```bash
# Dev costs (should be $0 with local models)
agentmd logs --workspace /workspace/dev --format json | \
  jq '[.[].total_tokens] | add'

# Staging costs
agentmd logs --workspace /workspace/staging --format json | \
  jq '[.[].total_tokens] | add'

# Production costs
agentmd logs --workspace /workspace/production --format json | \
  jq '[.[].total_tokens] | add'
```

### Cost Alert Script

**`scripts/cost-alert.sh`:**
```bash
#!/bin/bash
# Alert if production costs exceed threshold

source .env.production

# Get total tokens from last 24 hours
TOKENS=$(agentmd logs --since "24 hours ago" --format json | \
  jq '[.[].total_tokens] | add')

# Calculate cost (example: $0.03/1K input + $0.06/1K output for GPT-4)
# Simplified: assume 50/50 input/output split
COST=$(echo "scale=2; $TOKENS * 0.045 / 1000" | bc)

# Alert threshold: $10/day
THRESHOLD=10

if (( $(echo "$COST > $THRESHOLD" | bc -l) )); then
  echo "ALERT: Production costs exceeded threshold!"
  echo "  Tokens: $TOKENS"
  echo "  Cost: \$$COST"
  echo "  Threshold: \$$THRESHOLD"

  # Send alert (Slack, email, etc.)
  # curl -X POST $SLACK_WEBHOOK -d "{'text': 'Production costs: \$$COST'}"
fi
```

## Deployment

### Dev Deployment (Local)

```bash
# No deployment needed - run locally
source .env.dev
agentmd start
```

### Staging Deployment

```bash
# Deploy to staging server
rsync -avz workspace/staging/ user@staging-server:/opt/agentmd/workspace/
rsync -avz .env.staging user@staging-server:/opt/agentmd/.env

# Restart staging runtime
ssh user@staging-server 'systemctl restart agentmd'
```

### Production Deployment

```bash
# 1. Validate locally
source .env.production
for agent in workspace/production/*.md; do
  agentmd validate "$agent" || exit 1
done

# 2. Backup production
ssh user@prod-server 'cp -r /opt/agentmd/workspace /opt/agentmd/workspace.backup'

# 3. Deploy
rsync -avz workspace/production/ user@prod-server:/opt/agentmd/workspace/
rsync -avz .env.production user@prod-server:/opt/agentmd/.env

# 4. Restart (with health check)
ssh user@prod-server 'systemctl restart agentmd && sleep 5 && systemctl status agentmd'

# 5. Smoke test
ssh user@prod-server 'agentmd validate /opt/agentmd/workspace/*.md'
```

### Rollback Production

```bash
# Restore from backup
ssh user@prod-server 'cp -r /opt/agentmd/workspace.backup /opt/agentmd/workspace'
ssh user@prod-server 'systemctl restart agentmd'
```

## Monitoring

### Health Check Endpoints

```bash
# Dev
curl http://localhost:8000/health

# Staging
curl https://staging-agentmd.example.com/health

# Production
curl https://agentmd.example.com/health
```

### Log Aggregation

```bash
# Collect logs from all environments
ssh user@staging-server 'agentmd logs --since "1 hour ago"' > staging-logs.txt
ssh user@prod-server 'agentmd logs --since "1 hour ago"' > prod-logs.txt

# Compare
diff staging-logs.txt prod-logs.txt
```

## Secrets Management

### Use Secret Manager (Production)

Instead of `.env` files in production, use a secret manager:

**AWS Secrets Manager:**
```bash
# Store secret
aws secretsmanager create-secret \
  --name agentmd/production/openai-api-key \
  --secret-string "sk-proj-REAL-SECRET"

# Retrieve in production startup script
export OPENAI_API_KEY=$(aws secretsmanager get-secret-value \
  --secret-id agentmd/production/openai-api-key \
  --query SecretString --output text)
```

**Vault:**
```bash
# Store secret
vault kv put secret/agentmd/production \
  openai_api_key="sk-proj-REAL-SECRET"

# Retrieve
export OPENAI_API_KEY=$(vault kv get -field=openai_api_key secret/agentmd/production)
```

## Environment Checklist

Before promoting to next environment:

**Dev → Staging:**
- [ ] Agent works in dev
- [ ] All paths updated to staging paths
- [ ] Model switched from local to cloud (if applicable)
- [ ] Schedule adjusted if needed
- [ ] Committed to git

**Staging → Production:**
- [ ] Agent tested in staging for 24+ hours
- [ ] No errors in staging logs
- [ ] Token usage is acceptable
- [ ] Paths updated to production paths
- [ ] Model is production-grade
- [ ] Strict limits set (max_tokens, timeout, max_iterations)
- [ ] Log level reduced (WARNING or ERROR)
- [ ] Secrets are in secret manager (not .env)
- [ ] Code review completed
- [ ] Deployment plan documented
- [ ] Rollback plan ready
- [ ] Committed to git (main branch)
