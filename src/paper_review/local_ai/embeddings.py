from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence


@dataclass(slots=True)
class HuggingFaceEmbedder:
    """
    Thin wrapper around sentence-transformers for local embeddings.

    Notes:
    - Defaults are chosen to work well for retrieval models like E5.
    - This module intentionally keeps dependencies optional; callers should
      ensure `sentence-transformers` (and a compatible `torch`) are installed.
    """

    model_name: str = "intfloat/e5-base-v2"
    device: str | None = None
    batch_size: int = 32
    query_prefix: str = "query: "
    passage_prefix: str = "passage: "
    normalize: bool = True
    _model: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        try:
            import torch
            from sentence_transformers import SentenceTransformer
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(
                "Missing dependencies for local embeddings. "
                "Install `sentence-transformers` (and `torch`) to use HuggingFaceEmbedder."
            ) from e

        if self.device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"

        self._model = SentenceTransformer(self.model_name, device=self.device)

    def embed_passages(self, texts: Sequence[str]) -> "list[list[float]]":
        items = [f"{self.passage_prefix}{(t or '').strip()}" for t in texts]
        vecs = self._model.encode(
            items,
            batch_size=self.batch_size,
            normalize_embeddings=self.normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vecs.astype("float32").tolist()

    def embed_queries(self, queries: Sequence[str]) -> "list[list[float]]":
        items = [f"{self.query_prefix}{(q or '').strip()}" for q in queries]
        vecs = self._model.encode(
            items,
            batch_size=self.batch_size,
            normalize_embeddings=self.normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vecs.astype("float32").tolist()
