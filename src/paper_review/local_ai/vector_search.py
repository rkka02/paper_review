from __future__ import annotations

from typing import Sequence


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return float(sum(x * y for x, y in zip(a, b, strict=False)))


def top_k_cosine(query_vec: Sequence[float], matrix: list[list[float]], k: int = 10) -> list[tuple[int, float]]:
    """
    Returns [(index, score), ...] sorted by descending score.

    Assumes vectors are already L2-normalized (so cosine == dot).
    """
    if k <= 0:
        return []
    scores = [(i, _dot(query_vec, v)) for i, v in enumerate(matrix)]
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:k]

