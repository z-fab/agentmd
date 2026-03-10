from __future__ import annotations

from langchain_core.language_models import BaseChatModel


def create_chat_model(provider: str, model: str, settings: dict) -> BaseChatModel:
    """Create a ChatModel instance for the given provider.

    Uses official LangChain integration packages. Provider credentials
    are read from environment variables (loaded via python-dotenv at boot).

    Args:
        provider: Provider identifier ('google', 'openai', 'ollama').
        model: Model name (e.g. 'gemini-2.5-flash').
        settings: Dict with temperature, max_tokens, etc.

    Returns:
        A configured BaseChatModel instance.

    Raises:
        ValueError: If the provider is not supported.
        ImportError: If the required provider package is not installed.
    """
    temperature = settings.get("temperature", 0.7)
    max_tokens = settings.get("max_tokens", 4096)

    match provider:
        case "google":
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
            except ImportError:
                raise ImportError(
                    "Provider 'google' requires langchain-google-genai. "
                    "Install with: pip install langchain-google-genai"
                )
            return ChatGoogleGenerativeAI(
                model=model,
                temperature=temperature,
                max_output_tokens=max_tokens,
            )

        case "openai":
            try:
                from langchain_openai import ChatOpenAI
            except ImportError:
                raise ImportError(
                    "Provider 'openai' requires langchain-openai. Install with: pip install langchain-openai"
                )
            return ChatOpenAI(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        case "ollama":
            try:
                from langchain_ollama import ChatOllama
            except ImportError:
                raise ImportError(
                    "Provider 'ollama' requires langchain-ollama. Install with: pip install langchain-ollama"
                )
            return ChatOllama(
                model=model,
                temperature=temperature,
                num_predict=max_tokens,
            )

        case _:
            supported = ["google", "openai", "ollama"]
            raise ValueError(f"Unsupported provider: '{provider}'. Supported: {supported}")
