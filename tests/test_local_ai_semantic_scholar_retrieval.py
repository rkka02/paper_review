from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from paper_review.local_ai.embeddings import HuggingFaceEmbedder
from paper_review.local_ai.vector_search import top_k_cosine
from paper_review.semantic_scholar import search_papers


def _env_flag(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "y", "on"}


RUN = _env_flag("RUN_LOCAL_AI_TESTS")


@dataclass(frozen=True)
class FieldSpec:
    seed_query: str
    eval_query: str


FIELDS: dict[str, FieldSpec] = {
    "ai": FieldSpec(
        seed_query="transformer attention deep learning neural network",
        eval_query="transformer attention model for deep learning",
    ),
    "biology": FieldSpec(
        seed_query="gene expression transcription ribosome protein",
        eval_query="gene expression regulation transcription factors",
    ),
    "optics": FieldSpec(
        seed_query="laser interferometer photonics optical cavity",
        eval_query="laser interferometer photonics optical systems",
    ),
}

TARGET_PER_FIELD = 20


def _cache_path() -> Path:
  return Path(".pytest_cache") / "local_ai" / "semantic_scholar_seed.json"


def _save_cache(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_cache(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _paper_text(p: dict) -> str:
    title = (p.get("title") or "").strip()
    abstract = (p.get("abstract") or "").strip()
    year = p.get("year")
    venue = (p.get("venue") or "").strip()
    doi = (p.get("doi") or "").strip()

    authors = []
    for a in p.get("authors") or []:
        if not a:
            continue
        name = (a.get("name") or "").strip()
        if name:
            authors.append(name)

    parts = [f"Title: {title}"]
    if abstract:
        parts.append(f"Abstract: {abstract}")
    if authors:
        parts.append(f"Authors: {', '.join(authors[:12])}")
    if year:
        parts.append(f"Year: {year}")
    if venue:
        parts.append(f"Venue: {venue}")
    if doi:
        parts.append(f"DOI: {doi}")
    return "\n".join(parts)


def _collect_field_papers(
    field: str,
    spec: FieldSpec,
    target: int = TARGET_PER_FIELD,
    avoid_paper_ids: set[str] | None = None,
) -> list[dict]:
    seen: set[str] = set()
    avoid = avoid_paper_ids or set()
    out: list[dict] = []

    offset = 0
    limit = 50
    while len(out) < target and offset <= 500:
        rows = search_papers(spec.seed_query, limit=limit, offset=offset)
        if not rows:
            break

        for p in rows:
            pid = str(p.get("paper_id") or "").strip()
            if not pid or pid in seen or pid in avoid:
                continue
            title = (p.get("title") or "").strip()
            if not title:
                continue
            seen.add(pid)
            out.append({**p, "field": field})
            if len(out) >= target:
                break

        offset += limit
        time.sleep(0.25)

    return out


@pytest.fixture(scope="session")
def corpus() -> list[dict]:
    if not RUN:
        pytest.skip("Set RUN_LOCAL_AI_TESTS=1 to run Semantic Scholar + embedding integration tests.")

    pytest.importorskip("sentence_transformers")

    cache_file = _cache_path()

    def cache_is_valid(papers: list[dict]) -> bool:
        by_field = {k: 0 for k in FIELDS}
        ids: list[str] = []
        for p in papers:
            f = p.get("field")
            if f not in by_field:
                continue
            by_field[f] += 1
            pid = str(p.get("paper_id") or "").strip()
            if pid:
                ids.append(pid)
        return (
            all(by_field[k] >= TARGET_PER_FIELD for k in by_field)
            and len(ids) == len(set(ids))
            and len(ids) >= TARGET_PER_FIELD * len(FIELDS)
        )

    cached = _load_cache(cache_file) or {}
    cached_papers = cached.get("papers") if isinstance(cached, dict) else None
    if isinstance(cached_papers, list) and cache_is_valid(cached_papers):
        return cached_papers

    all_papers: list[dict] = []
    used_ids: set[str] = set()
    for field, spec in FIELDS.items():
        papers = _collect_field_papers(field, spec, target=TARGET_PER_FIELD, avoid_paper_ids=used_ids)
        assert len(papers) >= TARGET_PER_FIELD, f"Too few papers for {field}: {len(papers)}"
        for p in papers:
            pid = str(p.get("paper_id") or "").strip()
            if pid:
                used_ids.add(pid)
        all_papers.extend(papers)

    assert len(all_papers) >= TARGET_PER_FIELD * len(FIELDS)
    assert len(used_ids) == len(all_papers)

    _save_cache(cache_file, {"papers": all_papers})
    return all_papers


@pytest.fixture(scope="session")
def embedded(corpus: list[dict]) -> dict:
    model_name = (os.getenv("LOCAL_EMBED_MODEL") or os.getenv("LOCAL_AI_EMBED_MODEL") or "").strip() or "intfloat/e5-base-v2"
    device = (os.getenv("LOCAL_EMBED_DEVICE") or os.getenv("LOCAL_AI_EMBED_DEVICE") or "").strip() or None

    embedder = HuggingFaceEmbedder(model_name=model_name, device=device)
    texts = [_paper_text(p) for p in corpus]
    vecs = embedder.embed_passages(texts)

    dim = len(vecs[0]) if vecs else 0
    assert dim > 0
    assert all(len(v) == dim for v in vecs)

    return {"papers": corpus, "vectors": vecs, "embedder": embedder}


def test_fetch_and_embed_has_expected_shapes(corpus: list[dict], embedded: dict) -> None:
    papers = embedded["papers"]
    vecs = embedded["vectors"]

    assert len(papers) == len(vecs)
    assert len(papers) >= TARGET_PER_FIELD * len(FIELDS)
    assert all(p.get("title") for p in papers)


@pytest.mark.parametrize(
    "field",
    ["ai", "biology", "optics"],
)
def test_domain_query_retrieves_correct_field(embedded: dict, field: str) -> None:
    spec = FIELDS[field]
    papers: list[dict] = embedded["papers"]
    vecs: list[list[float]] = embedded["vectors"]
    embedder: HuggingFaceEmbedder = embedded["embedder"]

    qvec = embedder.embed_queries([spec.eval_query])[0]
    top = top_k_cosine(qvec, vecs, k=10)
    top_fields = [papers[i]["field"] for i, _ in top]

    hits = sum(1 for f in top_fields if f == field)
    assert hits >= 6, f"Expected >=6/{len(top_fields)} hits for {field}, got {hits}: {top_fields}"
