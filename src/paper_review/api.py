from __future__ import annotations

import hashlib
import secrets
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import HTMLResponse
from starlette.staticfiles import StaticFiles

from paper_review.db import db_session, init_db
from paper_review.drive import upload_drive_file
from paper_review.models import AnalysisRun, AnalysisOutput, Paper, Review
from paper_review.schemas import (
    AnalysisRunOut,
    PaperCreate,
    PaperDetailOut,
    PaperOut,
    PaperSummaryOut,
    PaperUpdate,
    ReviewUpsert,
)
from paper_review.settings import settings

app = FastAPI(title="paper-review", version="0.1.0")

_UPLOAD_PREFIX = "upload:"
_DOI_ONLY_PREFIX = "doi_only:"

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


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/api/papers", response_model=PaperOut, dependencies=[Depends(_require_auth)])
def create_paper(payload: PaperCreate, db: Session = Depends(get_db)) -> PaperOut:
    drive_file_id = (payload.drive_file_id or "").strip() or None
    doi = (payload.doi or "").strip() or None
    title = (payload.title or "").strip() or None
    if not drive_file_id and not doi:
        raise HTTPException(status_code=400, detail="Provide drive_file_id and/or doi.")

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
        tags=[],
        status="to_read",
    )
    db.add(paper)
    db.flush()
    db.refresh(paper)
    return PaperOut.model_validate(paper, from_attributes=True)


@app.get("/api/papers", response_model=list[PaperOut], dependencies=[Depends(_require_auth)])
def list_papers(
    db: Session = Depends(get_db),
    status_filter: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None),
) -> list[PaperOut]:
    stmt = select(Paper).order_by(desc(Paper.created_at))
    if status_filter:
        stmt = stmt.where(Paper.status == status_filter)
    if q:
        like = f"%{q}%"
        stmt = stmt.where((Paper.title.ilike(like)) | (Paper.doi.ilike(like)))
    papers = db.execute(stmt).scalars().all()
    return [PaperOut.model_validate(p, from_attributes=True) for p in papers]


@app.get("/api/papers/summary", response_model=list[PaperSummaryOut], dependencies=[Depends(_require_auth)])
def list_papers_summary(
    db: Session = Depends(get_db),
    status_filter: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None),
) -> list[PaperSummaryOut]:
    stmt = select(Paper).order_by(desc(Paper.created_at))
    if status_filter:
        stmt = stmt.where(Paper.status == status_filter)
    if q:
        like = f"%{q}%"
        stmt = stmt.where((Paper.title.ilike(like)) | (Paper.doi.ilike(like)))

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


@app.post("/api/papers/upload", response_model=PaperOut, dependencies=[Depends(_require_auth)])
async def upload_paper_pdf(
    request: Request,
    doi: str | None = Query(default=None),
    title: str | None = Query(default=None),
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

    drive_file_id: str
    if settings.upload_backend.strip().lower() == "drive":
        filename = f"{paper_id}.pdf"
        if title:
            safe = "".join([c if c.isalnum() or c in {" ", "_", "-"} else "_" for c in title]).strip()
            if safe:
                filename = f"{safe}.pdf"

        try:
            drive_file_id = upload_drive_file(
                final_path,
                filename=filename,
                parent_folder_id=settings.google_drive_upload_folder_id,
            )
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
        tags=[],
        status="to_read",
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
    content_md: str | None = None
    if run:
        out = (
            db.execute(select(AnalysisOutput).where(AnalysisOutput.analysis_run_id == run.id))
            .scalars()
            .first()
        )
        if out:
            output_json = out.canonical_json
            content_md = out.content_md

    return PaperDetailOut(
        paper=PaperOut.model_validate(paper, from_attributes=True),
        latest_run=AnalysisRunOut.model_validate(run, from_attributes=True) if run else None,
        latest_output=output_json,
        latest_content_md=content_md,
    )


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
    if payload.tags is not None:
        paper.tags = payload.tags
    if payload.doi is not None:
        paper.doi = payload.doi
    if payload.title is not None:
        paper.title = payload.title

    db.add(paper)
    db.flush()
    db.refresh(paper)
    return PaperOut.model_validate(paper, from_attributes=True)


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
