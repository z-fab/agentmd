"""Setup wizard provider curation must stay in sync with key resolution.

``PROVIDERS`` is deliberate product curation (which providers the wizard offers,
and a sane default model for each). The env-var name for each is not — that
comes from ``api_key_env_for``. Embedding both in the same dict was a fourth
restatement that drifted from the rest of the codebase.
"""

from __future__ import annotations

from agent_md.cli.setup import PROVIDERS, _build_env_content
from agent_md.providers.keys import api_key_env_for


def test_providers_includes_openrouter():
    assert "openrouter" in PROVIDERS
    assert "default_model" in PROVIDERS["openrouter"]
    assert "/" in PROVIDERS["openrouter"]["default_model"]


def test_providers_does_not_embed_env_var():
    for name, meta in PROVIDERS.items():
        assert "env_var" not in meta, (
            f"PROVIDERS[{name!r}] still carries env_var={meta.get('env_var')!r}; "
            "derive it with api_key_env_for(provider) instead"
        )


def test_build_env_content_covers_every_keyed_provider():
    content = _build_env_content(None, None)
    for name in PROVIDERS:
        env_var = api_key_env_for(name)
        if env_var is None:
            # Keyless providers (ollama) must not get a placeholder line.
            assert f"{name.upper()}_API_KEY" not in content
            continue
        assert env_var in content, f"expected a template line for {env_var} ({name})"
