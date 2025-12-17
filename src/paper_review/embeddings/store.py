from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from paper_review.embeddings.providers import Embedder
from paper_review.models import Paper, PaperEmbedding


def paper_embedding_text(paper: Paper) -> str:
    title = (paper.title or "").strip()
    doi = (paper.doi or "").strip()
    abstract = (paper.abstract or "").strip()

    parts: list[str] = []
    if title:
        parts.append(f"Title: {title}")
    if doi:
        parts.append(f"DOI: {doi}")

    meta = paper.metadata_row
    if meta:
        authors = []
        for a in meta.authors or []:
            if not a:
                continue
            name = (a.get("name") or "").strip()
            if name:
                authors.append(name)
        if authors:
            parts.append(f"Authors: {', '.join(authors[:12])}")
        if meta.year:
            parts.append(f"Year: {meta.year}")
        if meta.venue:
            parts.append(f"Venue: {meta.venue}")
        if meta.url:
            parts.append(f"URL: {meta.url}")

    if abstract:
        parts.append(f"Abstract: {abstract}")

    if not parts:
        return f"Paper {paper.id}"
    return "\n".join(parts)


def reset_paper_embeddings(db: Session) -> int:
    count = db.execute(select(func.count()).select_from(PaperEmbedding)).scalar_one()
    db.execute(delete(PaperEmbedding))
    db.flush()
    return int(count)


def ensure_embedding_backend(
    db: Session,
    provider: str,
    model: str,
    *,
    reset_if_changed: bool = True,
) -> bool:
    row = db.execute(select(PaperEmbedding.provider, PaperEmbedding.model).limit(1)).first()
    if not row:
        return False
    current_provider, current_model = row
    if current_provider == provider and current_model == model:
        return False
    if not reset_if_changed:
        raise RuntimeError(
            f"Embeddings exist for provider/model {current_provider}/{current_model}; "
            f"expected {provider}/{model}. Reset required."
        )
    reset_paper_embeddings(db)
    return True


def rebuild_paper_embeddings(
    db: Session,
    embedder: Embedder,
    *,
    limit: int | None = None,
    reset_if_changed: bool = True,
) -> dict:
    provider = getattr(embedder, "provider", "unknown")
    model = getattr(embedder, "model", "unknown")

    reset_done = ensure_embedding_backend(db, provider, model, reset_if_changed=reset_if_changed)

    stmt = select(Paper).options(selectinload(Paper.metadata_row)).order_by(Paper.created_at.desc())
    papers = db.execute(stmt).scalars().all()
    if limit is not None:
        papers = papers[: max(0, int(limit))]

    ids: list[uuid.UUID] = []
    texts: list[str] = []
    for p in papers:
        ids.append(p.id)
        texts.append(paper_embedding_text(p))

    vecs = embedder.embed_passages(texts)
    if len(vecs) != len(ids):
        raise RuntimeError("Embedding output count mismatch.")

    dim = len(vecs[0]) if vecs else 0
    upserts = 0
    for pid, vec in zip(ids, vecs, strict=True):
        row = db.get(PaperEmbedding, pid)
        if row is None:
            row = PaperEmbedding(
                paper_id=pid,
                provider=provider,
                model=model,
                dim=dim,
                vector=vec,
            )
            db.add(row)
        else:
            row.provider = provider
            row.model = model
            row.dim = dim
            row.vector = vec
        upserts += 1

    db.flush()
    return {
        "provider": provider,
        "model": model,
        "dim": dim,
        "papers": len(ids),
        "upserts": upserts,
        "reset": reset_done,
    }
