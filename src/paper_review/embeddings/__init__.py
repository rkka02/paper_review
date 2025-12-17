from __future__ import annotations

from paper_review.embeddings.factory import get_embedder
from paper_review.embeddings.providers import Embedder, LocalEmbedder, OpenAIEmbedder

__all__ = [
    "Embedder",
    "LocalEmbedder",
    "OpenAIEmbedder",
    "get_embedder",
]

