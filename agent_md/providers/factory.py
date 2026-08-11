from __future__ import annotations

from langchain_core.language_models import BaseChatModel


def create_chat_model(
    provider: str,
    model: str,
    settings: dict,
    base_url: str | None = None,
    api_key_env: str | None = None,
    stream_usage: bool = True,
) -> BaseChatModel:
    """Create a ChatModel instance for the given provider.

    Uses official LangChain integration packages. Provider credentials
    are read from environment variables (loaded via python-dotenv at boot).

    Args:
        provider: Provider identifier ('google', 'openai', 'anthropic', 'ollama', 'local',
            or any name with a ``base_url`` for an OpenAI-compatible endpoint).
        model: Model name (e.g. 'gemini-2.5-flash').
        settings: Dict with temperature, max_tokens, timeout, etc.
        base_url: Optional base URL for openai/ollama/local/OpenAI-compatible providers.
        api_key_env: Optional env var name holding the API key (defaults to ``<PROVIDER>_API_KEY``).
        stream_usage: Whether to request streaming token usage on OpenAI-compatible endpoints.

    Returns:
        A configured BaseChatModel instance.

    Raises:
        ValueError: If the provider is not supported.
        ImportError: If the required provider package is not installed.
    """
    temperature = settings.get("temperature", 0.7)
    max_tokens = settings.get("max_tokens", 4096)
    timeout = settings.get("timeout")

    match provider:
        case "google":
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
            except ImportError:
                raise ImportError(
                    "Provider 'google' requires langchain-google-genai. "
                    "Install with: pip install langchain-google-genai"
                )
            from agent_md.providers.keys import resolve_api_key

            kwargs: dict = {
                "model": model,
                "temperature": temperature,
                "max_output_tokens": max_tokens,
                "api_key": resolve_api_key(provider, base_url, api_key_env),
            }
            if timeout is not None:
                kwargs["timeout"] = timeout
            return ChatGoogleGenerativeAI(**kwargs)

        case "openai":
            try:
                from langchain_openai import ChatOpenAI
            except ImportError:
                raise ImportError(
                    "Provider 'openai' requires langchain-openai. Install with: pip install langchain-openai"
                )
            from agent_md.providers.keys import resolve_api_key

            kwargs = {
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "api_key": resolve_api_key(provider, base_url, api_key_env),
            }
            if base_url:
                kwargs["base_url"] = base_url
                # langchain-openai turns stream_usage off whenever base_url is
                # set; without it usage_metadata stays empty and the token/cost
                # limits silently never fire. Honour an explicit False for older
                # endpoints that reject stream_options.
                kwargs["stream_usage"] = stream_usage
            if timeout is not None:
                kwargs["timeout"] = timeout
            return ChatOpenAI(**kwargs)

        case "anthropic":
            try:
                from langchain_anthropic import ChatAnthropic
            except ImportError:
                raise ImportError(
                    "Provider 'anthropic' requires langchain-anthropic. Install with: pip install langchain-anthropic"
                )
            from agent_md.providers.keys import resolve_api_key

            kwargs = {
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "api_key": resolve_api_key(provider, base_url, api_key_env),
            }
            if timeout is not None:
                kwargs["timeout"] = timeout
            if base_url:
                kwargs["base_url"] = base_url
            return ChatAnthropic(**kwargs)

        case "ollama":
            try:
                from langchain_ollama import ChatOllama
            except ImportError:
                raise ImportError(
                    "Provider 'ollama' requires langchain-ollama. Install with: pip install langchain-ollama"
                )
            kwargs = {
                "model": model,
                "temperature": temperature,
                "num_predict": max_tokens,
            }
            if base_url:
                kwargs["base_url"] = base_url
            if timeout is not None:
                kwargs["timeout"] = timeout
            return ChatOllama(**kwargs)

        case "local":
            from agent_md.providers.keys import DEFAULT_LOCAL_BASE_URL, resolve_api_key
            from agent_md.providers.openai_compat import build_openai_compatible

            resolved_url = base_url or DEFAULT_LOCAL_BASE_URL
            return build_openai_compatible(
                model=model,
                settings=settings,
                base_url=resolved_url,
                api_key=resolve_api_key(provider, resolved_url, api_key_env),
                stream_usage=stream_usage,
            )

        case "openrouter":
            from agent_md.providers.keys import resolve_api_key
            from agent_md.providers.openrouter import build_openrouter

            return build_openrouter(
                model=model,
                settings=settings,
                api_key=resolve_api_key(provider, base_url, api_key_env),
            )

        case _:
            # Family B — any OpenAI-compatible endpoint, driven by config alone.
            if not base_url:
                raise ValueError(
                    f"Unsupported provider: '{provider}'. Supply a `base_url` to use it "
                    f"as an OpenAI-compatible endpoint."
                )
            from agent_md.providers.keys import resolve_api_key
            from agent_md.providers.openai_compat import build_openai_compatible

            return build_openai_compatible(
                model=model,
                settings=settings,
                base_url=base_url,
                api_key=resolve_api_key(provider, base_url, api_key_env),
                stream_usage=stream_usage,
            )
