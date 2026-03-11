# Guides

Practical guides for using Agent.md effectively.

## Essential Guides

- **[Security Best Practices](security-best-practices.md)** — Keep your agents secure
- **[Debugging](debugging.md)** — Troubleshoot common issues
- **[Performance](performance.md)** — Optimize token usage and speed
- **[Versioning & GitOps](versioning-gitops.md)** — Version control your prompts
- **[Multi-Environment](multi-environment.md)** — Dev/staging/prod setup

## Quick Tips

**Security:**
- Never put API keys in frontmatter
- Use `read`/`write` fields to restrict file access
- Set timeouts to prevent runaway costs

**Performance:**
- Use lower temperature for deterministic tasks
- Adjust `max_tokens` based on expected output
- Monitor token usage with `agentmd logs`

**GitOps:**
- Commit agents to version control
- Use `git diff` to review prompt changes
- Roll back with `git checkout`
