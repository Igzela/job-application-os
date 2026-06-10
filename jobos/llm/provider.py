from .base import LLMAdapter
from .mock import MockLLMAdapter


def get_llm_adapter(config: dict | None = None) -> LLMAdapter:
    if config is None:
        return MockLLMAdapter.create()

    provider = config.get("provider", "mock")

    if provider == "mock":
        return MockLLMAdapter.create()

    if provider == "openai":
        raise NotImplementedError("LLM provider not yet implemented")

    raise ValueError(f"Unknown provider: {provider}")
