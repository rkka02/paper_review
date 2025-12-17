from __future__ import annotations

from paper_review.embeddings.providers import Embedder, LocalEmbedder, OpenAIEmbedder
from paper_review.settings import settings


def get_embedder(provider: str | None = None) -> Embedder:
    p = (provider or settings.embeddings_provider or "").strip().lower()
    if p == "local":
        return LocalEmbedder(
            model=settings.local_embed_model,
            device=settings.local_embed_device,
            batch_size=settings.local_embed_batch_size,
            normalize=settings.embeddings_normalize,
        )
    if p == "openai":
        return OpenAIEmbedder(
            model=settings.openai_embed_model,
            batch_size=settings.openai_embed_batch_size,
            normalize=settings.embeddings_normalize,
        )
    raise ValueError(f"Unknown embeddings provider: {p!r} (expected 'local' or 'openai').")
