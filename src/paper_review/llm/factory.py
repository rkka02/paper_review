from __future__ import annotations

from paper_review.llm.providers import JsonLLM, OllamaJsonLLM, OpenAIJsonLLM
from paper_review.settings import settings


def get_llm(provider: str | None) -> JsonLLM:
    p = (provider or "").strip().lower()
    if p == "openai":
        return OpenAIJsonLLM(model=settings.openai_model)
    if p in {"ollama", "local"}:
        return OllamaJsonLLM(model=settings.local_llm_model)
    raise ValueError(
        f"Unknown LLM provider: {provider!r} (expected openai/ollama/local)."
    )


def get_query_llm(provider: str | None = None) -> JsonLLM:
    return get_llm(provider or settings.recommender_query_llm_provider)


def get_decider_llm(provider: str | None = None) -> JsonLLM:
    return get_llm(provider or settings.recommender_decider_llm_provider)
