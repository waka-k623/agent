import os

from app.providers.base import LLMProvider
from app.providers.openai_provider import OpenAIProvider
from app.providers.anthropic_provider import AnthropicProvider


def get_llm_provider() -> LLMProvider:
    provider = os.getenv("LLM_PROVIDER", "openai").lower()

    if provider == "openai":
        return OpenAIProvider()
    if provider in {"anthropic", "claude"}:
        return AnthropicProvider()

    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")
