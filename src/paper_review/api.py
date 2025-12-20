from __future__ import annotations

import hashlib
import logging
import re
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import delete, desc, or_, select, update
from sqlalchemy.orm import Session, selectinload
from starlette.middleware.sessions import SessionMiddleware
from starlette.background import BackgroundTask
from starlette.responses import FileResponse, HTMLResponse, StreamingResponse
from starlette.staticfiles import StaticFiles

from paper_review.analysis_output import validate_analysis
from paper_review.db import db_session, init_db
from paper_review.drive import (
    delete_drive_file,
    open_drive_file_stream,
    resolve_drive_upload_folder_id,
    upload_drive_file,
)
from paper_review.models import (
    AnalysisOutput,
    AnalysisRun,
    EvidenceSnippet,
    Folder,
    Paper,
    PaperEmbedding,
    PaperLink,
    PaperMetadata,
    RecommendationItem,
    RecommendationExclude,
    RecommendationRun,
    RecommendationTask,
    Review,
)
from paper_review.render import render_markdown
from paper_review.schemas import (
    AnalysisRunOut,
    FolderCreate,
    FolderOut,
    FolderUpdate,
    GraphOut,
    GraphNodeOut,
    PaperCreate,
    PaperDetailOut,
    PaperLinkCreate,
    PaperLinkNeighborOut,
    PaperLinkOut,
    PaperOut,
    PaperSummaryOut,
    PaperUpdate,
    ReviewUpsert,
    PaperEmbeddingsUpsert,
    RecommendationRunCreate,
    RecommendationRunOut,
    RecommendationItemOut,
    RecommendationTaskCreate,
    RecommendationTaskOut,
    RecommendationExcludeCreate,
    RecommendationExcludeOut,
)
from paper_review.settings import settings
from paper_review.translation import (
    translation_enabled,
    translate_recommendation_texts,
    translation_style,
)

app = FastAPI(title="paper-review", version="0.1.0")

logger = logging.getLogger(__name__)

_UPLOAD_PREFIX = "upload:"
_DOI_ONLY_PREFIX = "doi_only:"
_IMPORT_JSON_PREFIX = "import_json:"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _summarize_schema_validation_error(e: ValidationError) -> str:
    errors = e.errors()
    parts: list[str] = []
    for err in errors[:10]:
        loc = ".".join([str(x) for x in (err.get("loc") or [])])
        msg = err.get("msg") or "invalid"
        parts.append(f"{loc}: {msg}" if loc else msg)
    suffix = "" if len(errors) <= 10 else f" (+{len(errors) - 10} more)"
    return f"Schema validation failed: {'; '.join(parts)}{suffix}"


def _maybe_mark_stale_recommender_task(db: Session, task: RecommendationTask) -> None:
    if not task or task.status != "running":
        return
    try:
        from paper_review.recommender.task_runner import is_task_thread_alive

        if is_task_thread_alive(task.id):
            return
    except Exception:
        return

    msg = "Stale running task (no active runner in this process)."
    logs = list(task.logs or [])
    logs.append({"ts": _utcnow().isoformat(), "level": "error", "message": msg})
    task.logs = logs
    task.status = "failed"
    task.error = msg
    task.finished_at = _utcnow()
    db.add(task)
    db.flush()


_DOI_RE = re.compile(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", re.IGNORECASE)
_ARXIV_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/([^?#\s<>]+)", re.IGNORECASE)


def _normalize_doi(text: str | None) -> str | None:
    raw = (text or "").strip()
    if not raw:
        return None

    m = _DOI_RE.search(raw)
    if m:
        return (m.group(1) or "").strip().lower() or None

    lowered = raw.lower()
    for prefix in ("doi:", "https://doi.org/", "http://doi.org/"):
        if lowered.startswith(prefix):
            candidate = raw[len(prefix) :].strip()
            m2 = _DOI_RE.search(candidate)
            if m2:
                return (m2.group(1) or "").strip().lower() or None
            return None

    return None


def _normalize_title(text: str | None) -> str:
    s = (text or "").strip().lower()
    if not s:
        return ""
    s = re.sub(r"[^0-9a-z가-힣]+", " ", s)
    s = " ".join(s.split())
    return s


def _extract_arxiv_id(text: str | None) -> str | None:
    raw = (text or "").strip()
    if not raw:
        return None
    m = _ARXIV_RE.search(raw)
    if not m:
        return None
    arx = (m.group(1) or "").strip().lower()
    if not arx:
        return None
    if arx.endswith(".pdf"):
        arx = arx[: -len(".pdf")]
    if "v" in arx:
        base, _, v = arx.rpartition("v")
        if base and v.isdigit():
            arx = base
    return arx or None


def _filter_excluded_recommendations(db: Session, items: list[RecommendationItem]) -> list[RecommendationItem]:
    if not items:
        return items

    dois: set[str] = set()
    for i in items:
        doi = _normalize_doi(i.doi) or _normalize_doi(i.url)
        if doi:
            dois.add(doi)
    s2_ids = {
        (str(i.semantic_scholar_paper_id).strip())
        for i in items
        if (i.semantic_scholar_paper_id or "").strip()
    }
    arxiv_ids = {_extract_arxiv_id(i.url) for i in items if _extract_arxiv_id(i.url)}
    titles = {_normalize_title(i.title) for i in items if _normalize_title(i.title)}

    conds = []
    if dois:
        conds.append(RecommendationExclude.doi_norm.in_(sorted(dois)))
    if s2_ids:
        conds.append(RecommendationExclude.semantic_scholar_paper_id.in_(sorted(s2_ids)))
    if arxiv_ids:
        conds.append(RecommendationExclude.arxiv_id.in_(sorted(arxiv_ids)))
    if titles:
        conds.append(RecommendationExclude.title_norm.in_(sorted(titles)))
    if not conds:
        return items

    excludes = db.execute(select(RecommendationExclude).where(or_(*conds))).scalars().all()
    if not excludes:
        return items

    ex_doi = {e.doi_norm for e in excludes if (e.doi_norm or "").strip()}
    ex_s2 = {e.semantic_scholar_paper_id for e in excludes if (e.semantic_scholar_paper_id or "").strip()}
    ex_arx = {e.arxiv_id for e in excludes if (e.arxiv_id or "").strip()}
    ex_title = {e.title_norm for e in excludes if (e.title_norm or "").strip()}

    out: list[RecommendationItem] = []
    for it in items:
        s2 = (it.semantic_scholar_paper_id or "").strip()
        if s2 and s2 in ex_s2:
            continue
        doi = _normalize_doi(it.doi) or _normalize_doi(it.url)
        if doi and doi in ex_doi:
            continue
        arx = _extract_arxiv_id(it.url)
        if arx and arx in ex_arx:
            continue
        tn = _normalize_title(it.title)
        if tn and tn in ex_title:
            continue
        out.append(it)
    return out


def _extract_evidence_rows(canonical: dict) -> list[dict]:
    rows: list[dict] = []

    def add_evidence(evs: list[dict] | None, source: str) -> None:
        if not evs:
            return
        for ev in evs:
            if not isinstance(ev, dict):
                continue
            rows.append(
                {
                    "page": ev.get("page"),
                    "quote": ev.get("quote"),
                    "why": ev.get("why"),
                    "source": source,
                }
            )

    normalized = canonical.get("normalized") or {}
    for item in (normalized.get("contributions") or []):
        add_evidence((item or {}).get("evidence"), "normalization")
    for item in (normalized.get("claims") or []):
        add_evidence((item or {}).get("evidence"), "normalization")
    for item in (normalized.get("limitations") or []):
        add_evidence((item or {}).get("evidence"), "normalization")
    repro = normalized.get("reproducibility") or {}
    add_evidence(repro.get("evidence"), "normalization")

    for persona in (canonical.get("personas") or []):
        for h in (persona or {}).get("highlights") or []:
            add_evidence((h or {}).get("evidence"), "persona")

    final = canonical.get("final_synthesis") or {}
    add_evidence(final.get("evidence"), "persona")

    return rows


def _upsert_metadata_from_analysis(db: Session, paper: Paper, canonical: dict) -> None:
    paper_block = canonical.get("paper") or {}
    meta = paper_block.get("metadata") or {}

    row = paper.metadata_row
    if row is None:
        row = PaperMetadata(paper_id=paper.id)
        db.add(row)
        db.flush()
        paper.metadata_row = row

    row.authors = meta.get("authors")
    row.year = meta.get("year")
    row.venue = meta.get("venue")
    row.url = meta.get("url")
    row.source = "import_json"

    if meta.get("title") and not paper.title:
        paper.title = meta.get("title")
    if meta.get("doi") and not paper.doi:
        paper.doi = meta.get("doi")
    if paper_block.get("abstract") and not paper.abstract:
        paper.abstract = paper_block.get("abstract")

    db.add(row)
    db.add(paper)


def _normalize_folder_name(raw: str) -> str:
    name = (raw or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Folder name cannot be empty.")
    if len(name) > 200:
        raise HTTPException(status_code=400, detail="Folder name too long (max 200 chars).")
    return name


def _folder_descendant_ids(db: Session, root_id: uuid.UUID) -> list[uuid.UUID]:
    rows = db.execute(select(Folder.id, Folder.parent_id)).all()
    children_by_parent: dict[uuid.UUID | None, list[uuid.UUID]] = {}
    for folder_id, parent_id in rows:
        children_by_parent.setdefault(parent_id, []).append(folder_id)

    out: list[uuid.UUID] = []
    stack = [root_id]
    seen: set[uuid.UUID] = set()
    while stack:
        folder_id = stack.pop()
        if folder_id in seen:
            continue
        seen.add(folder_id)
        out.append(folder_id)
        for child in children_by_parent.get(folder_id, []):
            stack.append(child)
    return out


def _validate_folder_parent(db: Session, folder_id: uuid.UUID, parent_id: uuid.UUID | None) -> None:
    if parent_id is None:
        return
    if parent_id == folder_id:
        raise HTTPException(status_code=400, detail="Folder cannot be its own parent.")
    parent = db.get(Folder, parent_id)
    if not parent:
        raise HTTPException(status_code=400, detail="Parent folder not found.")
    cur = parent
    while cur.parent_id is not None:
        if cur.parent_id == folder_id:
            raise HTTPException(status_code=400, detail="Invalid parent (would create a cycle).")
        cur = db.get(Folder, cur.parent_id)
        if not cur:
            break

if settings.web_auth_enabled and not settings.session_secret:
    raise RuntimeError("SESSION_SECRET must be set when WEB_USERNAME/WEB_PASSWORD are set.")
if settings.session_secret:
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        same_site="lax",
        https_only=bool(settings.cookie_https_only),
    )

_WEBAPP_DIR = Path(__file__).resolve().parent / "webapp"
_INDEX_HTML = (_WEBAPP_DIR / "index.html").read_text(encoding="utf-8")
app.mount("/static", StaticFiles(directory=str(_WEBAPP_DIR / "static")), name="static")


@app.get("/", include_in_schema=False)
def web_index() -> HTMLResponse:
    return HTMLResponse(_INDEX_HTML)


def _session_user(request: Request) -> str | None:
    session = request.scope.get("session")
    if not isinstance(session, dict):
        return None
    user = session.get("user")
    return user if isinstance(user, str) else None


def _require_auth(
    request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")
) -> None:
    auth_configured = bool(settings.api_key) or settings.web_auth_enabled
    if not auth_configured:
        return

    if settings.api_key and x_api_key and secrets.compare_digest(x_api_key, settings.api_key):
        return

    if settings.web_auth_enabled:
        user = _session_user(request)
        if user and settings.web_username and secrets.compare_digest(user, settings.web_username):
            return

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


class _LoginPayload(BaseModel):
    username: str
    password: str


@app.get("/api/session", include_in_schema=False)
def get_session(request: Request) -> dict:
    if not settings.web_auth_enabled:
        return {"auth_enabled": False, "authenticated": True}
    user = _session_user(request)
    authenticated = bool(user and settings.web_username and secrets.compare_digest(user, settings.web_username))
    return {"auth_enabled": True, "authenticated": authenticated}


@app.post("/api/session", include_in_schema=False)
def login(payload: _LoginPayload, request: Request) -> dict:
    if not settings.web_auth_enabled:
        raise HTTPException(status_code=400, detail="WEB_USERNAME/WEB_PASSWORD not set.")
    assert settings.web_username is not None
    assert settings.web_password is not None
    if not (
        secrets.compare_digest(payload.username, settings.web_username)
        and secrets.compare_digest(payload.password, settings.web_password)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    request.session.clear()
    request.session["user"] = settings.web_username
    return {"ok": True}


@app.delete("/api/session", include_in_schema=False)
def logout(request: Request) -> dict:
    if "session" in request.scope:
        request.session.clear()
    return {"ok": True}


def get_db() -> Session:
    with db_session() as session:
        yield session


@app.on_event("startup")
def _startup() -> None:
    init_db()
    try:
        from paper_review.recommender.task_runner import reconcile_stale_running_tasks

        reconcile_stale_running_tasks()
    except Exception:
        pass
    if settings.recommender_auto_run:
        from paper_review.recommender.task_runner import start_recommender_scheduler

        start_recommender_scheduler()


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/graph", response_model=GraphOut, dependencies=[Depends(_require_auth)])
def graph(db: Session = Depends(get_db)) -> GraphOut:
    papers = db.execute(select(Paper).order_by(desc(Paper.created_at))).scalars().all()
    nodes = [
        GraphNodeOut(
            id=p.id,
            title=p.title,
            doi=p.doi,
            folder_id=p.folder_id,
        )
        for p in papers
    ]
    edges = db.execute(select(PaperLink).order_by(desc(PaperLink.created_at))).scalars().all()
    return GraphOut(nodes=nodes, edges=[PaperLinkOut.model_validate(e, from_attributes=True) for e in edges])


def _canonical_pair(a: uuid.UUID, b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    if a.int <= b.int:
        return a, b
    return b, a


def _paper_neighbors(db: Session, paper_id: uuid.UUID) -> list[PaperLinkNeighborOut]:
    links = (
        db.execute(
            select(PaperLink).where((PaperLink.a_paper_id == paper_id) | (PaperLink.b_paper_id == paper_id))
        )
        .scalars()
        .all()
    )
    other_ids: list[uuid.UUID] = []
    for link in links:
        other_ids.append(link.b_paper_id if link.a_paper_id == paper_id else link.a_paper_id)

    if not other_ids:
        return []

    papers = db.execute(select(Paper).where(Paper.id.in_(other_ids))).scalars().all()
    paper_by_id = {p.id: p for p in papers}
    out: list[PaperLinkNeighborOut] = []
    for oid in other_ids:
        p = paper_by_id.get(oid)
        if not p:
            continue
        out.append(PaperLinkNeighborOut(id=p.id, title=p.title, doi=p.doi, folder_id=p.folder_id))
    out.sort(key=lambda x: (x.title or "").lower())
    return out


@app.post("/api/papers/{paper_id}/links", response_model=dict, dependencies=[Depends(_require_auth)])
def create_link(paper_id: uuid.UUID, payload: PaperLinkCreate, db: Session = Depends(get_db)) -> dict:
    other_id = payload.other_paper_id
    if other_id == paper_id:
        raise HTTPException(status_code=400, detail="Cannot link a paper to itself.")

    if not db.get(Paper, paper_id) or not db.get(Paper, other_id):
        raise HTTPException(status_code=404, detail="Paper not found")

    a_id, b_id = _canonical_pair(paper_id, other_id)
    existing = (
        db.execute(select(PaperLink).where(PaperLink.a_paper_id == a_id, PaperLink.b_paper_id == b_id))
        .scalars()
        .first()
    )
    if existing:
        return {"ok": True, "link_id": str(existing.id)}

    link = PaperLink(a_paper_id=a_id, b_paper_id=b_id, source="user", meta=None)
    db.add(link)
    db.flush()
    db.refresh(link)
    return {"ok": True, "link_id": str(link.id)}


@app.delete("/api/papers/{paper_id}/links/{other_paper_id}", response_model=dict, dependencies=[Depends(_require_auth)])
def delete_link(
    paper_id: uuid.UUID, other_paper_id: uuid.UUID, db: Session = Depends(get_db)
) -> dict:
    if other_paper_id == paper_id:
        raise HTTPException(status_code=400, detail="Invalid link.")

    a_id, b_id = _canonical_pair(paper_id, other_paper_id)
    link = (
        db.execute(select(PaperLink).where(PaperLink.a_paper_id == a_id, PaperLink.b_paper_id == b_id))
        .scalars()
        .first()
    )
    if not link:
        return {"ok": True}

    db.delete(link)
    db.flush()
    return {"ok": True}


@app.get("/api/folders", response_model=list[FolderOut], dependencies=[Depends(_require_auth)])
def list_folders(db: Session = Depends(get_db)) -> list[FolderOut]:
    folders = db.execute(select(Folder).order_by(Folder.name.asc())).scalars().all()
    return [FolderOut.model_validate(f, from_attributes=True) for f in folders]


@app.post("/api/folders", response_model=FolderOut, dependencies=[Depends(_require_auth)])
def create_folder(payload: FolderCreate, db: Session = Depends(get_db)) -> FolderOut:
    name = _normalize_folder_name(payload.name)
    parent_id = payload.parent_id
    if parent_id is not None and not db.get(Folder, parent_id):
        raise HTTPException(status_code=400, detail="Parent folder not found.")

    folder = Folder(name=name, parent_id=parent_id)
    db.add(folder)
    db.flush()
    db.refresh(folder)
    return FolderOut.model_validate(folder, from_attributes=True)


@app.patch("/api/folders/{folder_id}", response_model=FolderOut, dependencies=[Depends(_require_auth)])
def update_folder(folder_id: uuid.UUID, payload: FolderUpdate, db: Session = Depends(get_db)) -> FolderOut:
    folder = db.get(Folder, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    if "name" in payload.model_fields_set:
        folder.name = _normalize_folder_name(payload.name or "")
    if "parent_id" in payload.model_fields_set:
        _validate_folder_parent(db, folder_id, payload.parent_id)
        folder.parent_id = payload.parent_id

    db.add(folder)
    db.flush()
    db.refresh(folder)
    return FolderOut.model_validate(folder, from_attributes=True)


@app.delete("/api/folders/{folder_id}", response_model=dict, dependencies=[Depends(_require_auth)])
def delete_folder(folder_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    folder = db.get(Folder, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    ids = _folder_descendant_ids(db, folder_id)
    db.execute(update(Paper).where(Paper.folder_id.in_(ids)).values(folder_id=None))
    db.execute(delete(Folder).where(Folder.id.in_(ids)))
    db.flush()
    return {"ok": True}


@app.post("/api/papers", response_model=PaperOut, dependencies=[Depends(_require_auth)])
def create_paper(payload: PaperCreate, db: Session = Depends(get_db)) -> PaperOut:
    drive_file_id = (payload.drive_file_id or "").strip() or None
    doi = (payload.doi or "").strip() or None
    title = (payload.title or "").strip() or None
    if not drive_file_id and not doi:
        raise HTTPException(status_code=400, detail="Provide drive_file_id and/or doi.")

    folder_id = payload.folder_id
    if folder_id is not None and not db.get(Folder, folder_id):
        raise HTTPException(status_code=400, detail="Folder not found.")

    paper_id = uuid.uuid4()
    if not drive_file_id:
        drive_file_id = f"{_DOI_ONLY_PREFIX}{paper_id}"

    paper = Paper(
        id=paper_id,
        drive_file_id=drive_file_id,
        pdf_sha256=payload.pdf_sha256,
        pdf_size_bytes=payload.pdf_size_bytes,
        doi=doi,
        title=title,
        status="to_read",
        folder_id=folder_id,
        memo=None,
    )
    db.add(paper)
    db.flush()
    db.refresh(paper)
    return PaperOut.model_validate(paper, from_attributes=True)


@app.post("/api/papers/import-json", response_model=PaperOut, dependencies=[Depends(_require_auth)])
async def import_paper_from_json(
    request: Request,
    drive_file_id: str | None = Query(default=None),
    doi: str | None = Query(default=None),
    title: str | None = Query(default=None),
    folder_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PaperOut:
    try:
        payload = await request.json()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Body must be valid JSON: {e}")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON must be an object.")

    try:
        parsed = validate_analysis(payload)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=_summarize_schema_validation_error(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Schema validation failed: {e}")

    canonical = parsed.model_dump()
    paper_id = uuid.uuid4()

    drive_file_id = (drive_file_id or "").strip() or None
    doi = (doi or "").strip() or None
    title = (title or "").strip() or None

    paper_block = canonical.get("paper") or {}
    meta = paper_block.get("metadata") or {}
    meta_doi = (meta.get("doi") or "").strip() or None
    meta_title = (meta.get("title") or "").strip() or None
    doi = doi or meta_doi
    title = title or meta_title

    if not drive_file_id:
        drive_file_id = f"{_IMPORT_JSON_PREFIX}{paper_id}"

    if folder_id is not None and not db.get(Folder, folder_id):
        raise HTTPException(status_code=400, detail="Folder not found.")

    paper = Paper(
        id=paper_id,
        drive_file_id=drive_file_id,
        doi=doi,
        title=title,
        abstract=paper_block.get("abstract"),
        status="to_read",
        folder_id=folder_id,
        memo=None,
    )
    db.add(paper)
    db.flush()
    db.refresh(paper)

    now = _utcnow()
    run = AnalysisRun(
        paper_id=paper.id,
        stage="import_json",
        status="succeeded",
        error=None,
        started_at=now,
        finished_at=now,
        timings={"import_json": True},
    )
    db.add(run)
    db.flush()
    db.refresh(run)

    content_md = render_markdown(canonical)
    out = AnalysisOutput(
        analysis_run_id=run.id,
        canonical_json=canonical,
        canonical_json_ko=None,
        content_md=content_md,
    )
    db.add(out)

    for ev in _extract_evidence_rows(canonical):
        db.add(
            EvidenceSnippet(
                paper_id=paper.id,
                analysis_run_id=run.id,
                page=ev.get("page"),
                quote=ev.get("quote"),
                why=ev.get("why"),
                source=ev.get("source"),
            )
        )

    _upsert_metadata_from_analysis(db, paper, canonical)
    db.flush()
    db.refresh(paper)
    return PaperOut.model_validate(paper, from_attributes=True)


@app.get("/api/papers", response_model=list[PaperOut], dependencies=[Depends(_require_auth)])
def list_papers(
    db: Session = Depends(get_db),
    status_filter: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None),
    folder_id: uuid.UUID | None = Query(default=None),
    unfiled: bool = Query(default=False),
) -> list[PaperOut]:
    stmt = (
        select(Paper)
        .options(selectinload(Paper.metadata_row), selectinload(Paper.review))
        .order_by(desc(Paper.created_at))
    )
    if status_filter:
        stmt = stmt.where(Paper.status == status_filter)
    if folder_id is not None:
        stmt = stmt.where(Paper.folder_id == folder_id)
    elif unfiled:
        stmt = stmt.where(Paper.folder_id.is_(None))
    if q:
        like = f"%{q}%"
        stmt = stmt.where((Paper.title.ilike(like)) | (Paper.doi.ilike(like)) | (Paper.memo.ilike(like)))
    papers = db.execute(stmt).scalars().all()
    return [PaperOut.model_validate(p, from_attributes=True) for p in papers]


@app.get("/api/papers/summary", response_model=list[PaperSummaryOut], dependencies=[Depends(_require_auth)])
def list_papers_summary(
    db: Session = Depends(get_db),
    status_filter: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None),
    folder_id: uuid.UUID | None = Query(default=None),
    unfiled: bool = Query(default=False),
) -> list[PaperSummaryOut]:
    stmt = (
        select(Paper)
        .options(selectinload(Paper.metadata_row), selectinload(Paper.review))
        .order_by(desc(Paper.created_at))
    )
    if status_filter:
        stmt = stmt.where(Paper.status == status_filter)
    if folder_id is not None:
        stmt = stmt.where(Paper.folder_id == folder_id)
    elif unfiled:
        stmt = stmt.where(Paper.folder_id.is_(None))
    if q:
        like = f"%{q}%"
        stmt = stmt.where((Paper.title.ilike(like)) | (Paper.doi.ilike(like)) | (Paper.memo.ilike(like)))

    papers = db.execute(stmt).scalars().all()
    out: list[PaperSummaryOut] = []
    for paper in papers:
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
        out.append(
            PaperSummaryOut(
                paper=PaperOut.model_validate(paper, from_attributes=True),
                latest_run=AnalysisRunOut.model_validate(run, from_attributes=True) if run else None,
            )
        )
    return out


@app.get(
    "/api/paper-embeddings/missing",
    response_model=list[uuid.UUID],
    dependencies=[Depends(_require_auth)],
)
def list_missing_paper_embeddings(
    db: Session = Depends(get_db),
    provider: str | None = Query(default=None),
    model: str | None = Query(default=None),
) -> list[uuid.UUID]:
    prov = (provider or "").strip() or None
    mdl = (model or "").strip() or None

    stmt = select(Paper.id).outerjoin(PaperEmbedding, PaperEmbedding.paper_id == Paper.id)
    if prov and mdl:
        stmt = stmt.where(
            (PaperEmbedding.paper_id.is_(None))
            | (PaperEmbedding.provider != prov)
            | (PaperEmbedding.model != mdl)
        )
    else:
        stmt = stmt.where(PaperEmbedding.paper_id.is_(None))

    return list(db.execute(stmt).scalars().all())


@app.post(
    "/api/paper-embeddings/batch",
    response_model=dict,
    dependencies=[Depends(_require_auth)],
)
def upsert_paper_embeddings(payload: PaperEmbeddingsUpsert, db: Session = Depends(get_db)) -> dict:
    provider = (payload.provider or "").strip()
    model = (payload.model or "").strip()
    if not provider or not model:
        raise HTTPException(status_code=400, detail="provider and model are required.")

    vectors = payload.vectors or []
    if not vectors:
        return {"ok": True, "upserts": 0, "provider": provider, "model": model, "dim": 0}

    dim = len(vectors[0].vector or [])
    if dim <= 0:
        raise HTTPException(status_code=400, detail="vector cannot be empty.")

    for v in vectors:
        if len(v.vector) != dim:
            raise HTTPException(status_code=400, detail="vector dim mismatch in request.")

    ids = [v.paper_id for v in vectors]
    existing = set(db.execute(select(Paper.id).where(Paper.id.in_(ids))).scalars().all())
    missing = [str(pid) for pid in ids if pid not in existing]
    if missing:
        extra = f" (+{len(missing) - 10} more)" if len(missing) > 10 else ""
        raise HTTPException(status_code=400, detail=f"Unknown paper_id(s): {', '.join(missing[:10])}{extra}")

    upserts = 0
    for v in vectors:
        row = db.get(PaperEmbedding, v.paper_id)
        if row is None:
            db.add(
                PaperEmbedding(
                    paper_id=v.paper_id,
                    provider=provider,
                    model=model,
                    dim=dim,
                    vector=[float(x) for x in v.vector],
                )
            )
        else:
            row.provider = provider
            row.model = model
            row.dim = dim
            row.vector = [float(x) for x in v.vector]
        upserts += 1

    db.flush()
    return {"ok": True, "upserts": upserts, "provider": provider, "model": model, "dim": dim}


@app.post("/api/papers/upload", response_model=PaperOut, dependencies=[Depends(_require_auth)])
async def upload_paper_pdf(
    request: Request,
    doi: str | None = Query(default=None),
    title: str | None = Query(default=None),
    folder_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PaperOut:
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(status_code=415, detail="Upload must be application/pdf.")

    max_bytes = int(settings.max_pdf_mb) * 1024 * 1024
    paper_id = uuid.uuid4()
    upload_dir = settings.upload_dir
    upload_dir.mkdir(parents=True, exist_ok=True)
    final_path = upload_dir / f"{paper_id}.pdf"
    tmp_path = upload_dir / f"{paper_id}.pdf.part"

    hasher = hashlib.sha256()
    size = 0
    try:
        with tmp_path.open("wb") as f:
            async for chunk in request.stream():
                if not chunk:
                    continue
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=413, detail=f"PDF too large (>{settings.max_pdf_mb} MB)."
                    )
                hasher.update(chunk)
                f.write(chunk)
        tmp_path.replace(final_path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
        raise

    doi = (doi or "").strip() or None
    title = (title or "").strip() or None

    if folder_id is not None and not db.get(Folder, folder_id):
        raise HTTPException(status_code=400, detail="Folder not found.")

    drive_file_id: str
    if settings.upload_backend.strip().lower() == "drive":
        filename = f"{paper_id}.pdf"
        if title:
            safe = "".join([c if c.isalnum() or c in {" ", "_", "-"} else "_" for c in title]).strip()
            if safe:
                filename = f"{safe}.pdf"

        try:
            parent_folder_id = resolve_drive_upload_folder_id()
            drive_file_id = upload_drive_file(
                final_path,
                filename=filename,
                parent_folder_id=parent_folder_id,
            )
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(e))
        finally:
            try:
                final_path.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                pass
    else:
        drive_file_id = f"{_UPLOAD_PREFIX}{paper_id}"

    paper = Paper(
        id=paper_id,
        drive_file_id=drive_file_id,
        pdf_sha256=hasher.hexdigest(),
        pdf_size_bytes=size,
        doi=doi,
        title=title,
        status="to_read",
        folder_id=folder_id,
        memo=None,
    )
    try:
        db.add(paper)
        db.flush()
        db.refresh(paper)
    except Exception:
        try:
            final_path.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
        raise

    return PaperOut.model_validate(paper, from_attributes=True)


@app.post("/api/papers/{paper_id}/pdf", response_model=PaperOut, dependencies=[Depends(_require_auth)])
async def replace_paper_pdf(
    paper_id: uuid.UUID, request: Request, db: Session = Depends(get_db)
) -> PaperOut:
    paper = db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(status_code=415, detail="Upload must be application/pdf.")

    max_bytes = int(settings.max_pdf_mb) * 1024 * 1024
    upload_dir = settings.upload_dir
    upload_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = upload_dir / f"{paper_id}.{uuid.uuid4().hex}.pdf.part"

    hasher = hashlib.sha256()
    size = 0
    try:
        with tmp_path.open("wb") as f:
            async for chunk in request.stream():
                if not chunk:
                    continue
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=413, detail=f"PDF too large (>{settings.max_pdf_mb} MB)."
                    )
                hasher.update(chunk)
                f.write(chunk)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
        raise

    old_drive_file_id = paper.drive_file_id
    backend = settings.upload_backend.strip().lower()

    try:
        if backend == "drive":
            filename = f"{paper_id}.pdf"
            label = (paper.title or "").strip() or (paper.doi or "").strip() or ""
            if label:
                safe = "".join([c if c.isalnum() or c in {" ", "_", "-"} else "_" for c in label]).strip()
                if safe:
                    filename = f"{safe}.pdf"

            parent_folder_id = resolve_drive_upload_folder_id()
            try:
                drive_file_id = upload_drive_file(
                    tmp_path,
                    filename=filename,
                    parent_folder_id=parent_folder_id,
                )
            except Exception as e:  # noqa: BLE001
                raise HTTPException(status_code=502, detail=str(e))
            paper.drive_file_id = drive_file_id
        else:
            final_path = upload_dir / f"{paper_id}.pdf"
            tmp_path.replace(final_path)
            paper.drive_file_id = f"{_UPLOAD_PREFIX}{paper_id}"
    finally:
        if backend == "drive":
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                pass

    paper.pdf_sha256 = hasher.hexdigest()
    paper.pdf_size_bytes = size

    db.add(paper)
    db.flush()
    db.refresh(paper)

    # Best-effort cleanup of the previous PDF (if any).
    try:
        if old_drive_file_id.startswith(_UPLOAD_PREFIX) and backend == "drive":
            (settings.upload_dir / f"{paper_id}.pdf").unlink(missing_ok=True)
            (settings.upload_dir / f"{paper_id}.pdf.part").unlink(missing_ok=True)
        elif not (
            old_drive_file_id.startswith(_UPLOAD_PREFIX)
            or old_drive_file_id.startswith(_DOI_ONLY_PREFIX)
            or old_drive_file_id.startswith(_IMPORT_JSON_PREFIX)
        ) and old_drive_file_id != paper.drive_file_id:
            delete_drive_file(old_drive_file_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("pdf_replace_cleanup_failed paper_id=%s error=%s", paper_id, e)

    return PaperOut.model_validate(paper, from_attributes=True)


@app.get("/api/papers/{paper_id}/pdf", dependencies=[Depends(_require_auth)])
def download_paper_pdf(paper_id: uuid.UUID, db: Session = Depends(get_db)):
    paper = db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    drive_file_id = (paper.drive_file_id or "").strip()
    if not drive_file_id:
        raise HTTPException(status_code=404, detail="No PDF for this paper.")

    if drive_file_id.startswith(_DOI_ONLY_PREFIX) or drive_file_id.startswith(_IMPORT_JSON_PREFIX):
        raise HTTPException(status_code=404, detail="No PDF for this paper.")

    filename = f"{paper_id}.pdf"

    if drive_file_id.startswith(_UPLOAD_PREFIX):
        path = settings.upload_dir / f"{paper_id}.pdf"
        if not path.exists():
            raise HTTPException(status_code=404, detail="PDF not found on server.")
        return FileResponse(
            path=path,
            media_type="application/pdf",
            filename=filename,
            content_disposition_type="inline",
        )

    try:
        r, close = open_drive_file_stream(drive_file_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(e))

    headers = {
        "Content-Disposition": f'inline; filename="{filename}"',
    }
    content_length = r.headers.get("content-length")
    if content_length:
        headers["Content-Length"] = content_length

    return StreamingResponse(
        r.iter_bytes(),
        media_type="application/pdf",
        headers=headers,
        background=BackgroundTask(close),
    )


@app.get("/api/papers/{paper_id}", response_model=PaperDetailOut, dependencies=[Depends(_require_auth)])
def get_paper(paper_id: uuid.UUID, db: Session = Depends(get_db)) -> PaperDetailOut:
    paper = db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    run = (
        db.execute(
            select(AnalysisRun)
            .where(AnalysisRun.paper_id == paper_id)
            .order_by(desc(AnalysisRun.created_at))
            .limit(1)
        )
        .scalars()
        .first()
    )
    output_json: dict | None = None
    output_json_ko: dict | None = None
    content_md: str | None = None
    if run:
        out = (
            db.execute(select(AnalysisOutput).where(AnalysisOutput.analysis_run_id == run.id))
            .scalars()
            .first()
        )
        if out:
            output_json = out.canonical_json
            output_json_ko = out.canonical_json_ko
            content_md = out.content_md
        else:
            fallback = (
                db.execute(
                    select(AnalysisOutput)
                    .join(AnalysisRun, AnalysisOutput.analysis_run_id == AnalysisRun.id)
                    .where(AnalysisRun.paper_id == paper_id)
                    .order_by(desc(AnalysisRun.created_at))
                    .limit(1)
                )
                .scalars()
                .first()
            )
            if fallback:
                output_json = fallback.canonical_json
                output_json_ko = fallback.canonical_json_ko
                content_md = fallback.content_md

    return PaperDetailOut(
        paper=PaperOut.model_validate(paper, from_attributes=True),
        latest_run=AnalysisRunOut.model_validate(run, from_attributes=True) if run else None,
        latest_output=output_json,
        latest_output_ko=output_json_ko,
        latest_content_md=content_md,
        links=_paper_neighbors(db, paper_id),
    )


class _AnalysisJsonSavePayload(BaseModel):
    lang: Literal["original", "ko"]
    canonical: dict = Field(alias="json")


@app.put(
    "/api/papers/{paper_id}/analysis-json",
    response_model=dict,
    dependencies=[Depends(_require_auth)],
)
def save_paper_analysis_json(
    paper_id: uuid.UUID, payload: _AnalysisJsonSavePayload, db: Session = Depends(get_db)
) -> dict:
    logs: list[str] = []

    paper = db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    try:
        parsed = validate_analysis(payload.canonical)
    except ValidationError as e:
        msg = _summarize_schema_validation_error(e)
        logs.append(msg)
        return {"ok": False, "logs": logs, "error": msg}
    except Exception as e:  # noqa: BLE001
        msg = f"Schema validation failed: {e}"
        logs.append(msg)
        return {"ok": False, "logs": logs, "error": msg}

    canonical = parsed.model_dump()
    lang = payload.lang

    latest_row = (
        db.execute(
            select(AnalysisRun, AnalysisOutput)
            .join(AnalysisOutput, AnalysisOutput.analysis_run_id == AnalysisRun.id)
            .where(AnalysisRun.paper_id == paper_id)
            .order_by(desc(AnalysisRun.created_at))
            .limit(1)
        )
        .first()
    )

    run: AnalysisRun | None = None
    out: AnalysisOutput | None = None
    if latest_row:
        run, out = latest_row

    if not out:
        if lang == "ko":
            msg = "No analysis JSON found. Save 원문 JSON first."
            logs.append(msg)
            return {"ok": False, "logs": logs, "error": msg}

        now = _utcnow()
        run = AnalysisRun(
            paper_id=paper.id,
            stage="manual_json",
            status="succeeded",
            error=None,
            started_at=now,
            finished_at=now,
            timings={"manual_json": True},
        )
        db.add(run)
        db.flush()
        db.refresh(run)

        out = AnalysisOutput(
            analysis_run_id=run.id,
            canonical_json=canonical,
            canonical_json_ko=None,
            content_md=render_markdown(canonical),
        )
        db.add(out)
        _upsert_metadata_from_analysis(db, paper, canonical)
        for ev in _extract_evidence_rows(canonical):
            db.add(
                EvidenceSnippet(
                    paper_id=paper.id,
                    analysis_run_id=run.id,
                    page=ev.get("page"),
                    quote=ev.get("quote"),
                    why=ev.get("why"),
                    source=ev.get("source"),
                )
            )
        db.flush()
        logs.append("Saved 원문 JSON.")
        return {"ok": True, "logs": logs}

    if lang == "original":
        out.canonical_json = canonical
        out.content_md = render_markdown(canonical)
        _upsert_metadata_from_analysis(db, paper, canonical)
        db.execute(delete(EvidenceSnippet).where(EvidenceSnippet.analysis_run_id == out.analysis_run_id))
        for ev in _extract_evidence_rows(canonical):
            db.add(
                EvidenceSnippet(
                    paper_id=paper.id,
                    analysis_run_id=out.analysis_run_id,
                    page=ev.get("page"),
                    quote=ev.get("quote"),
                    why=ev.get("why"),
                    source=ev.get("source"),
                )
            )
        db.add(out)
        db.flush()
        logs.append("Saved 원문 JSON.")
        return {"ok": True, "logs": logs}

    out.canonical_json_ko = canonical
    db.add(out)
    db.flush()
    logs.append("Saved 한국어 JSON.")
    return {"ok": True, "logs": logs}


@app.patch(
    "/api/papers/{paper_id}",
    response_model=PaperOut,
    dependencies=[Depends(_require_auth)],
)
def update_paper(paper_id: uuid.UUID, payload: PaperUpdate, db: Session = Depends(get_db)) -> PaperOut:
    paper = db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    if payload.status is not None:
        paper.status = payload.status
    if payload.doi is not None:
        doi = (payload.doi or "").strip()
        paper.doi = doi or None
    if payload.title is not None:
        paper.title = payload.title
    if "folder_id" in payload.model_fields_set:
        if payload.folder_id is not None and not db.get(Folder, payload.folder_id):
            raise HTTPException(status_code=400, detail="Folder not found.")
        paper.folder_id = payload.folder_id
    if "memo" in payload.model_fields_set:
        raw = payload.memo if payload.memo is not None else ""
        memo = raw.strip()
        paper.memo = memo or None

    db.add(paper)
    db.flush()
    db.refresh(paper)
    return PaperOut.model_validate(paper, from_attributes=True)


@app.post(
    "/api/papers/{paper_id}/import-json",
    response_model=AnalysisRunOut,
    dependencies=[Depends(_require_auth)],
)
async def import_analysis_json(
    paper_id: uuid.UUID, request: Request, db: Session = Depends(get_db)
) -> AnalysisRunOut:
    paper = db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    try:
        payload = await request.json()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Body must be valid JSON: {e}")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON must be an object.")

    try:
        parsed = validate_analysis(payload)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=_summarize_schema_validation_error(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Schema validation failed: {e}")

    canonical = parsed.model_dump()
    content_md = render_markdown(canonical)

    now = _utcnow()
    run = AnalysisRun(
        paper_id=paper.id,
        stage="import_json",
        status="succeeded",
        error=None,
        started_at=now,
        finished_at=now,
        timings={"import_json": True},
    )
    db.add(run)
    db.flush()
    db.refresh(run)

    out = AnalysisOutput(
        analysis_run_id=run.id,
        canonical_json=canonical,
        canonical_json_ko=None,
        content_md=content_md,
    )
    db.add(out)

    for ev in _extract_evidence_rows(canonical):
        db.add(
            EvidenceSnippet(
                paper_id=paper.id,
                analysis_run_id=run.id,
                page=ev.get("page"),
                quote=ev.get("quote"),
                why=ev.get("why"),
                source=ev.get("source"),
            )
        )

    _upsert_metadata_from_analysis(db, paper, canonical)
    db.flush()
    db.refresh(run)
    return AnalysisRunOut.model_validate(run, from_attributes=True)


@app.delete("/api/papers/{paper_id}", response_model=dict, dependencies=[Depends(_require_auth)])
def delete_paper(paper_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    paper = db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    db.execute(delete(EvidenceSnippet).where(EvidenceSnippet.paper_id == paper_id))
    db.delete(paper)
    db.flush()

    if paper.drive_file_id.startswith(_UPLOAD_PREFIX):
        try:
            (settings.upload_dir / f"{paper_id}.pdf").unlink(missing_ok=True)
            (settings.upload_dir / f"{paper_id}.pdf.part").unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass

    return {"ok": True}


@app.post(
    "/api/papers/{paper_id}/analyze",
    response_model=AnalysisRunOut,
    dependencies=[Depends(_require_auth)],
)
def enqueue_analysis(paper_id: uuid.UUID, db: Session = Depends(get_db)) -> AnalysisRunOut:
    paper = db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    run = AnalysisRun(paper_id=paper_id, stage="single_session_review", status="queued")
    db.add(run)
    db.flush()
    db.refresh(run)
    return AnalysisRunOut.model_validate(run, from_attributes=True)


@app.put(
    "/api/papers/{paper_id}/review",
    response_model=dict,
    dependencies=[Depends(_require_auth)],
)
def upsert_review(paper_id: uuid.UUID, payload: ReviewUpsert, db: Session = Depends(get_db)) -> dict:
    paper = db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    existing = (
        db.execute(select(Review).where(Review.paper_id == paper_id)).scalars().first()
    )
    if existing:
        review = existing
    else:
        review = Review(paper_id=paper_id)
        db.add(review)

    for field in ("one_liner", "summary", "pros", "cons", "rating_overall"):
        value = getattr(payload, field)
        if value is not None:
            setattr(review, field, value)

    db.flush()
    db.refresh(review)
    return {"ok": True, "review_id": str(review.id)}


@app.get(
    "/api/recommendations/latest",
    response_model=RecommendationRunOut,
    dependencies=[Depends(_require_auth)],
)
def get_latest_recommendations(db: Session = Depends(get_db)) -> RecommendationRunOut:
    run = (
        db.execute(
            select(RecommendationRun)
            .options(selectinload(RecommendationRun.items))
            .order_by(desc(RecommendationRun.created_at))
            .limit(1)
        )
        .scalars()
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="No recommendations.")

    items = sorted(
        run.items,
        key=lambda i: (
            i.kind or "",
            str(i.folder_id or ""),
            int(i.rank or 0),
        ),
    )
    items = _filter_excluded_recommendations(db, items)
    return RecommendationRunOut(
        id=run.id,
        source=run.source,
        meta=run.meta,
        created_at=run.created_at,
        items=[RecommendationItemOut.model_validate(it, from_attributes=True) for it in items],
    )


@app.post(
    "/api/recommendations/{run_id}/translate",
    response_model=dict,
    dependencies=[Depends(_require_auth)],
)
def translate_recommendations(run_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    logs: list[str] = []
    if not translation_enabled():
        msg = "GOOGLE_AI_API_KEY is not set."
        logs.append(msg)
        return {"ok": False, "logs": logs, "error": msg}

    run = (
        db.execute(
            select(RecommendationRun)
            .options(selectinload(RecommendationRun.items))
            .where(RecommendationRun.id == run_id)
        )
        .scalars()
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Recommendation run not found.")

    style = translation_style()
    items = list(run.items or [])
    logs.append(f"Translating {len(items)} item(s) (style={style}).")

    translated = 0
    for item in items:
        one_liner = (item.one_liner or "").strip()
        summary = (item.summary or "").strip()
        abstract = (item.abstract or "").strip()

        if not any([one_liner, summary, abstract]):
            item.one_liner_ko = None
            item.summary_ko = None
            item.abstract_ko = None
            db.add(item)
            continue

        try:
            out = translate_recommendation_texts(
                one_liner=one_liner,
                summary=summary,
                abstract=abstract,
            )
            if not out:
                continue
            item.one_liner_ko = out.get("one_liner")
            item.summary_ko = out.get("summary")
            item.abstract_ko = out.get("abstract")
            db.add(item)
            translated += 1
        except Exception as e:  # noqa: BLE001
            logs.append(f"Item {item.id} failed: {type(e).__name__}: {e}")
            continue

    db.flush()
    logs.append(f"Translated {translated} item(s).")
    return {"ok": True, "logs": logs, "translated": translated}


@app.post(
    "/api/recommendations/excludes",
    response_model=RecommendationExcludeOut,
    dependencies=[Depends(_require_auth)],
)
def exclude_recommendation(payload: RecommendationExcludeCreate, db: Session = Depends(get_db)) -> RecommendationExcludeOut:
    item = db.get(RecommendationItem, payload.item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Recommendation item not found.")

    doi_norm = _normalize_doi(item.doi) or _normalize_doi(item.url)
    arxiv_id = _extract_arxiv_id(item.url)
    s2_id = (item.semantic_scholar_paper_id or "").strip() or None
    title = (item.title or "").strip() or None
    title_norm = _normalize_title(title)

    if not any([doi_norm, arxiv_id, s2_id, title_norm]):
        raise HTTPException(status_code=400, detail="Cannot build exclusion key from item.")

    conds = []
    if doi_norm:
        conds.append(RecommendationExclude.doi_norm == doi_norm)
    if arxiv_id:
        conds.append(RecommendationExclude.arxiv_id == arxiv_id)
    if s2_id:
        conds.append(RecommendationExclude.semantic_scholar_paper_id == s2_id)
    if title_norm:
        conds.append(RecommendationExclude.title_norm == title_norm)

    existing = (
        db.execute(select(RecommendationExclude).where(or_(*conds)).order_by(desc(RecommendationExclude.created_at)).limit(1))
        .scalars()
        .first()
    )
    if existing:
        if payload.reason and not (existing.reason or "").strip():
            existing.reason = payload.reason.strip()
            db.add(existing)
            db.flush()
            db.refresh(existing)
        return RecommendationExcludeOut.model_validate(existing, from_attributes=True)

    ex = RecommendationExclude(
        doi_norm=doi_norm,
        arxiv_id=arxiv_id,
        semantic_scholar_paper_id=s2_id,
        title=title,
        title_norm=title_norm or "(untitled)",
        reason=(payload.reason or "").strip() or None,
        source_item_id=item.id,
    )
    db.add(ex)
    db.flush()
    db.refresh(ex)
    return RecommendationExcludeOut.model_validate(ex, from_attributes=True)


@app.get(
    "/api/recommendations/excludes",
    response_model=list[RecommendationExcludeOut],
    dependencies=[Depends(_require_auth)],
)
def list_recommendation_excludes(
    limit: int = 500,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> list[RecommendationExcludeOut]:
    limit = max(1, min(int(limit), 5000))
    offset = max(0, int(offset))
    rows = (
        db.execute(
            select(RecommendationExclude)
            .order_by(desc(RecommendationExclude.created_at))
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return [RecommendationExcludeOut.model_validate(r, from_attributes=True) for r in rows]


@app.get(
    "/api/recommendations/tasks/latest",
    response_model=RecommendationTaskOut,
    dependencies=[Depends(_require_auth)],
)
def get_latest_recommendation_task(db: Session = Depends(get_db)) -> RecommendationTaskOut:
    task = (
        db.execute(select(RecommendationTask).order_by(desc(RecommendationTask.created_at)).limit(1))
        .scalars()
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="No recommendation tasks.")
    _maybe_mark_stale_recommender_task(db, task)
    return RecommendationTaskOut.model_validate(task, from_attributes=True)


@app.get(
    "/api/recommendations/tasks/{task_id}",
    response_model=RecommendationTaskOut,
    dependencies=[Depends(_require_auth)],
)
def get_recommendation_task(task_id: uuid.UUID, db: Session = Depends(get_db)) -> RecommendationTaskOut:
    task = db.get(RecommendationTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    _maybe_mark_stale_recommender_task(db, task)
    return RecommendationTaskOut.model_validate(task, from_attributes=True)


@app.post(
    "/api/recommendations/tasks",
    response_model=RecommendationTaskOut,
    dependencies=[Depends(_require_auth)],
)
def start_recommendation_task(payload: RecommendationTaskCreate | None = None) -> RecommendationTaskOut:
    from paper_review.recommender.task_runner import enqueue_recommendation_task

    cfg: dict | None = None
    if payload is not None:
        cfg = {}
        if payload.per_folder is not None:
            cfg["per_folder"] = int(payload.per_folder)
        if payload.cross_domain is not None:
            cfg["cross_domain"] = int(payload.cross_domain)
        if payload.random_seed is not None:
            cfg["random_seed"] = int(payload.random_seed)
        if not cfg:
            cfg = None

    task_id = enqueue_recommendation_task(trigger="manual", config=cfg)
    with db_session() as db:
        task = db.get(RecommendationTask, task_id)
        if not task:
            raise HTTPException(status_code=500, detail="Failed to create task.")
        return RecommendationTaskOut.model_validate(task, from_attributes=True)


@app.post(
    "/api/recommendations",
    response_model=RecommendationRunOut,
    dependencies=[Depends(_require_auth)],
)
def create_recommendations(payload: RecommendationRunCreate, db: Session = Depends(get_db)) -> RecommendationRunOut:
    run = RecommendationRun(source=(payload.source or "local").strip() or "local", meta=payload.meta)
    db.add(run)
    db.flush()

    do_translate = translation_enabled()
    for item in payload.items:
        abstract = (item.abstract or "").strip() or None
        one_liner = (item.one_liner or "").strip() or None
        summary = (item.summary or "").strip() or None

        abstract_ko = (item.abstract_ko or "").strip() if item.abstract_ko is not None else None
        one_liner_ko = (item.one_liner_ko or "").strip() if item.one_liner_ko is not None else None
        summary_ko = (item.summary_ko or "").strip() if item.summary_ko is not None else None

        if do_translate and not any([abstract_ko, one_liner_ko, summary_ko]):
            try:
                translated = translate_recommendation_texts(
                    one_liner=one_liner,
                    summary=summary,
                    abstract=abstract,
                )
                if translated:
                    one_liner_ko = translated.get("one_liner")
                    summary_ko = translated.get("summary")
                    abstract_ko = translated.get("abstract")
            except Exception as e:  # noqa: BLE001
                logger.warning("recommendation_translate_failed title=%s error=%s", item.title, e)

        db.add(
            RecommendationItem(
                run_id=run.id,
                kind=(item.kind or "").strip() or "folder",
                folder_id=item.folder_id,
                rank=int(item.rank),
                semantic_scholar_paper_id=(item.semantic_scholar_paper_id or "").strip() or None,
                title=(item.title or "").strip() or "(untitled)",
                doi=(item.doi or "").strip() or None,
                url=(item.url or "").strip() or None,
                year=item.year,
                venue=(item.venue or "").strip() or None,
                authors=item.authors,
                abstract=abstract,
                abstract_ko=abstract_ko,
                score=float(item.score) if item.score is not None else None,
                one_liner=one_liner,
                one_liner_ko=one_liner_ko,
                summary=summary,
                summary_ko=summary_ko,
                rationale=item.rationale,
            )
        )

    db.flush()
    db.refresh(run)

    items = (
        db.execute(
            select(RecommendationItem)
            .where(RecommendationItem.run_id == run.id)
            .order_by(
                RecommendationItem.kind.asc(),
                RecommendationItem.folder_id.asc(),
                RecommendationItem.rank.asc(),
            )
        )
        .scalars()
        .all()
    )
    return RecommendationRunOut(
        id=run.id,
        source=run.source,
        meta=run.meta,
        created_at=run.created_at,
        items=[RecommendationItemOut.model_validate(it, from_attributes=True) for it in items],
    )
