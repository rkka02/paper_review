from __future__ import annotations

from paper_review.embeddings.factory import get_embedder
from paper_review.embeddings.providers import Embedder, OpenAIEmbedder

__all__ = [
    "Embedder",
    "OpenAIEmbedder",
    "get_embedder",
]
