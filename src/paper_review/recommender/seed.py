from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Protocol


class SeedSelector(Protocol):
    name: str

    def select(self, papers: list[dict], k: int, *, rng: random.Random) -> list[dict]: ...


@dataclass(slots=True)
class RandomSeedSelector:
    name: str = "random"

    def select(self, papers: list[dict], k: int, *, rng: random.Random) -> list[dict]:
        items = [p for p in (papers or []) if isinstance(p, dict)]
        if not items or k <= 0:
            return []
        if len(items) <= k:
            rng.shuffle(items)
            return items
        return rng.sample(items, k)

