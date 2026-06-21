from app.config import settings
from .base import LLMProvider


def create_provider(
    provider_override: str | None = None,
    model_override: str | None = None,
) -> LLMProvider:
    """
    Instantiate an LLM provider.
    Per-run overrides take precedence over environment defaults.
    """
    provider = (provider_override or settings.llm_provider).lower()

    if provider == "anthropic":
        from .anthropic_provider import AnthropicProvider
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required when using Anthropic")
        return AnthropicProvider(
            api_key=settings.anthropic_api_key,
            model=model_override or settings.anthropic_model,
        )

    if provider == "gemini":
        from .gemini_provider import GeminiProvider
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is required when using Gemini")
        return GeminiProvider(
            api_key=settings.gemini_api_key,
            model=model_override or settings.gemini_model,
        )

    raise ValueError(
        f"Unknown provider '{provider}'. Choose 'anthropic' or 'gemini'."
    )
