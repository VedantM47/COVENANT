"""LLM provider factory."""
from __future__ import annotations

from app.llm_providers.base import LLMProvider


def get_provider(provider_name: str, settings=None) -> LLMProvider:
    if settings is None:
        from app.settings import get_settings
        settings = get_settings()

    name = provider_name or settings.llm_provider

    if name == "mock":
        from app.llm_providers.mock import MockLLMProvider
        return MockLLMProvider()
    elif name == "mock_replay":
        from app.llm_providers.mock_replay import MockReplayProvider
        import os
        fixture = os.environ.get("MOCK_REPLAY_FIXTURE", "firstbank")
        return MockReplayProvider(fixture_name=fixture)
    elif name == "gemini":
        from app.llm_providers.gemini import GeminiProvider
        return GeminiProvider(api_key=settings.google_api_key)
    elif name == "anthropic":
        from app.llm_providers.anthropic import AnthropicProvider
        return AnthropicProvider(api_key=settings.anthropic_api_key)
    elif name == "bedrock":
        from app.llm_providers.bedrock import BedrockProvider
        return BedrockProvider(
            region=settings.aws_region,
            access_key=settings.aws_access_key_id,
            secret_key=settings.aws_secret_access_key,
        )
    elif name == "openrouter":
        from app.llm_providers.openrouter import OpenRouterProvider
        return OpenRouterProvider(api_key=settings.openrouter_api_key)
    else:
        raise ValueError(f"Unknown LLM provider: {name}")
