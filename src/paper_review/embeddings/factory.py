from __future__ import annotations

from paper_review.embeddings.providers import Embedder, OpenAIEmbedder
from paper_review.settings import settings


def get_embedder(provider: str | None = None) -> Embedder:
    if provider is not None and (provider or "").strip().lower() not in {"openai"}:
        raise ValueError("Embeddings provider is fixed to OpenAI (provider must be 'openai').")

    return OpenAIEmbedder(
        model=settings.openai_embed_model,
        batch_size=settings.openai_embed_batch_size,
        normalize=settings.embeddings_normalize,
    )
