"""API-key env resolution for every provider.

One rule: use ``api_key_env`` when the agent gives one, otherwise derive
``<PROVIDER>_API_KEY``. Every provider package's own default already follows
that pattern, so there is nothing to tabulate.

There is deliberately no third, global fallback (an ``AGENTMD_API_KEY``): a
global key is the only step in the chain that can send the *wrong* credential
to a third-party endpoint — an OpenAI key travelling to api.groq.com because
GROQ_API_KEY was never set.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

SENTINEL_API_KEY = "not-needed"

# Default endpoint for provider ``local`` — shared by key resolution and the factory
# so both agree that an omitted base_url is loopback and needs no credential.
DEFAULT_LOCAL_BASE_URL = "http://localhost:11434/v1"

# Providers whose adapter takes no credential at all.
_KEYLESS_PROVIDERS = frozenset({"ollama"})

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def derive_key_env(provider: str) -> str:
    """``groq`` -> ``GROQ_API_KEY``; ``together-ai`` -> ``TOGETHER_AI_API_KEY``."""
    return provider.replace("-", "_").upper() + "_API_KEY"


def is_loopback(base_url: str | None) -> bool:
    """True when the endpoint is on this machine, and so needs no credential."""
    if not base_url:
        return False
    host = urlparse(base_url).hostname
    return host in _LOOPBACK_HOSTS


def api_key_env_for(
    provider: str,
    base_url: str | None = None,
    api_key_env: str | None = None,
) -> str | None:
    """Env var holding this model's key, or None when no key is needed."""
    if api_key_env:
        return api_key_env
    if provider in _KEYLESS_PROVIDERS:
        return None
    if provider == "local" and not base_url:
        base_url = DEFAULT_LOCAL_BASE_URL
    if is_loopback(base_url):
        return None
    return derive_key_env(provider)


def resolve_api_key(
    provider: str,
    base_url: str | None = None,
    api_key_env: str | None = None,
) -> str:
    """Return the credential, or the sentinel when none is needed.

    Raises ValueError at config time rather than letting a scheduled run fail
    against the provider's 401 hours later.
    """
    env_var = api_key_env_for(provider, base_url, api_key_env)
    if env_var is None:
        return SENTINEL_API_KEY
    key = os.environ.get(env_var)
    if not key:
        raise ValueError(
            f"{env_var} is not set (required by provider '{provider}'). "
            f"Set it in your .env, or point `api_key_env` at the variable that holds the key."
        )
    return key
