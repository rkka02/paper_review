from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

import httpx

from paper_review.settings import settings


class Embedder(Protocol):
    provider: str
    model: str

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]: ...
    def embed_queries(self, queries: Sequence[str]) -> list[list[float]]: ...


def _openai_headers() -> dict[str, str]:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    return {"Authorization": f"Bearer {settings.openai_api_key}"}


def _openai_timeout() -> httpx.Timeout:
    seconds = float(settings.openai_timeout_seconds)
    return httpx.Timeout(connect=30.0, read=seconds, write=seconds, pool=30.0)


@dataclass(slots=True)
class OpenAIEmbedder:
    model: str
    batch_size: int = 96
    normalize: bool = True

    provider: str = "openai"

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed(list(texts))

    def embed_queries(self, queries: Sequence[str]) -> list[list[float]]:
        return self._embed(list(queries))

    def _embed(self, items: list[str]) -> list[list[float]]:
        if not items:
            return []

        url = "https://api.openai.com/v1/embeddings"
        out: list[list[float]] = []
        bs = max(1, int(self.batch_size))

        def l2_normalize(vec: list[float]) -> list[float]:
            s = 0.0
            for v in vec:
                s += v * v
            if s <= 0:
                return vec
            inv = (s ** 0.5) ** -1
            return [x * inv for x in vec]

        with httpx.Client(timeout=_openai_timeout()) as client:
            for i in range(0, len(items), bs):
                chunk = [str(x or "") for x in items[i : i + bs]]
                r = client.post(
                    url,
                    headers={**_openai_headers(), "Content-Type": "application/json"},
                    json={"model": self.model, "input": chunk},
                )
                r.raise_for_status()
                data = r.json()
                rows = data.get("data") or []
                if len(rows) != len(chunk):
                    raise RuntimeError("OpenAI embeddings response length mismatch.")
                for row in rows:
                    emb = row.get("embedding")
                    if not isinstance(emb, list) or not emb:
                        raise RuntimeError("OpenAI embeddings response missing embedding.")
                    vec = [float(v) for v in emb]
                    if self.normalize:
                        vec = l2_normalize(vec)
                    out.append(vec)

        return out
