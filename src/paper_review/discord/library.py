from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from paper_review.models import AnalysisRun, Folder, Paper

_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)
_DOI_RE = re.compile(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", re.IGNORECASE)


def extract_uuid(text: str) -> uuid.UUID | None:
    m = _UUID_RE.search(text or "")
    if not m:
        return None
    try:
        return uuid.UUID(m.group(0))
    except Exception:  # noqa: BLE001
        return None


def extract_doi(text: str) -> str | None:
    m = _DOI_RE.search(text or "")
    if not m:
        return None
    doi = (m.group(1) or "").strip()
    return doi or None


def _folder_path(folder_id: uuid.UUID | None, folder_by_id: dict[uuid.UUID, Folder]) -> str | None:
    if not folder_id:
        return None
    names: list[str] = []
    cur: uuid.UUID | None = folder_id
    while cur and cur in folder_by_id:
        f = folder_by_id[cur]
        name = (f.name or "").strip()
        if name:
            names.append(name)
        cur = f.parent_id
    if not names:
        return None
    return "/".join(reversed(names))


def _authors_text(authors: list[dict] | None) -> str | None:
    if not isinstance(authors, list) or not authors:
        return None
    names: list[str] = []
    for a in authors:
        if not isinstance(a, dict):
            continue
        n = (a.get("name") or "").strip()
        if n:
            names.append(n)
    if not names:
        return None
    s = ", ".join(names[:12])
    if len(names) > 12:
        s += f" (+{len(names) - 12})"
    return s


def paper_context_text(db: Session, paper: Paper) -> str:
    folders = db.execute(select(Folder).order_by(Folder.created_at.asc())).scalars().all()
    folder_by_id = {f.id: f for f in folders}

    path = _folder_path(paper.folder_id, folder_by_id)
    title = (paper.title or "").strip() or "(untitled)"
    doi = (paper.doi or "").strip() or None
    abstract = (paper.abstract or "").strip() or None
    status = (paper.status or "").strip() or None
    memo = (paper.memo or "").strip() or None

    meta = paper.metadata_row
    authors = _authors_text(meta.authors) if meta else None
    year = meta.year if meta else None
    venue = (meta.venue or "").strip() if meta else ""
    url = (meta.url or "").strip() if meta else ""

    review = paper.review
    review_one_liner = (review.one_liner or "").strip() if review else ""
    review_summary = (review.summary or "").strip() if review else ""
    review_pros = (review.pros or "").strip() if review else ""
    review_cons = (review.cons or "").strip() if review else ""
    rating = review.rating_overall if review else None

    run = (
        db.execute(
            select(AnalysisRun)
            .where(AnalysisRun.paper_id == paper.id)
            .order_by(desc(AnalysisRun.created_at))
            .limit(1)
        )
        .scalars()
        .first()
    )

    parts: list[str] = []
    parts.append(f"Title: {title}")
    parts.append(f"Paper ID: {paper.id}")
    if doi:
        parts.append(f"DOI: {doi}")
    if path:
        parts.append(f"Folder: {path}")
    if status:
        parts.append(f"Status: {status}")
    if year:
        parts.append(f"Year: {year}")
    if venue:
        parts.append(f"Venue: {venue}")
    if authors:
        parts.append(f"Authors: {authors}")
    if url:
        parts.append(f"URL: {url}")
    if memo:
        parts.append(f"Memo: {memo}")
    if review_one_liner:
        parts.append(f"Review one-liner: {review_one_liner}")
    if review_summary:
        parts.append(f"Review summary: {review_summary}")
    if review_pros:
        parts.append(f"Review pros: {review_pros}")
    if review_cons:
        parts.append(f"Review cons: {review_cons}")
    if rating is not None:
        parts.append(f"Review rating_overall: {rating}")
    if abstract:
        parts.append(f"Abstract: {abstract}")
    if run:
        parts.append(
            "Latest analysis run: "
            f"stage={run.stage}, status={run.status}, finished_at={run.finished_at}"
        )

    return "\n".join(parts).strip()


@dataclass(frozen=True, slots=True)
class PaperLookupResult:
    paper: Paper | None
    candidates: list[Paper]
    reason: str


def lookup_paper_for_message(db: Session, text: str) -> PaperLookupResult:
    raw = (text or "").strip()

    pid = extract_uuid(raw)
    if pid:
        paper = (
            db.execute(
                select(Paper)
                .options(selectinload(Paper.metadata_row), selectinload(Paper.review))
                .where(Paper.id == pid)
                .limit(1)
            )
            .scalars()
            .first()
        )
        if paper:
            return PaperLookupResult(paper=paper, candidates=[], reason="paper_id")

    doi = extract_doi(raw)
    if doi:
        paper = (
            db.execute(
                select(Paper)
                .options(selectinload(Paper.metadata_row), selectinload(Paper.review))
                .where(Paper.doi.ilike(doi))
                .order_by(desc(Paper.created_at))
                .limit(1)
            )
            .scalars()
            .first()
        )
        if paper:
            return PaperLookupResult(paper=paper, candidates=[], reason="doi")

    q = raw
    if len(q) > 120:
        q = q[:120]
    q = q.strip()
    candidates: list[Paper] = []
    if q:
        like = f"%{q}%"
        candidates = (
            db.execute(
                select(Paper)
                .options(selectinload(Paper.metadata_row), selectinload(Paper.review))
                .where((Paper.title.ilike(like)) | (Paper.doi.ilike(like)))
                .order_by(desc(Paper.updated_at))
                .limit(5)
            )
            .scalars()
            .all()
        )

    return PaperLookupResult(paper=None, candidates=candidates, reason="search")


def latest_papers(db: Session, limit: int = 5) -> list[Paper]:
    return (
        db.execute(
            select(Paper)
            .options(selectinload(Paper.metadata_row), selectinload(Paper.review))
            .order_by(desc(Paper.updated_at))
            .limit(max(1, int(limit)))
        )
        .scalars()
        .all()
    )

