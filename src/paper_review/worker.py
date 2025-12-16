from __future__ import annotations

import json
import logging
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import text
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from paper_review.analysis_output import OPENAI_JSON_SCHEMA, validate_analysis
from paper_review.db import db_session, init_db
from paper_review.drive import download_drive_file
from paper_review.models import AnalysisOutput, AnalysisRun, EvidenceSnippet, Paper, PaperMetadata
from paper_review.openai_http import create_response, delete_file, extract_output_json, upload_file
from paper_review.prompting import build_single_session_prompt
from paper_review.render import render_markdown
from paper_review.semantic_scholar import fetch_metadata_by_doi
from paper_review.settings import settings
from paper_review.utils import sha256_file

logger = logging.getLogger(__name__)

_UPLOAD_PREFIX = "upload:"
_DOI_ONLY_PREFIX = "doi_only:"


@dataclass(frozen=True)
class Job:
    run_id: uuid.UUID
    paper_id: uuid.UUID
    drive_file_id: str
    doi: str | None
    paper_title: str | None
    paper_abstract: str | None
    pdf_size_bytes: int | None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _claim_next_job(db: Session) -> Job | None:
    candidate = (
        db.execute(
            select(AnalysisRun.id, AnalysisRun.paper_id)
            .where(AnalysisRun.status == "queued")
            .order_by(AnalysisRun.created_at.asc())
            .limit(1)
        )
        .first()
    )
    if not candidate:
        return None

    run_id, paper_id = candidate
    claimed = (
        db.execute(
            update(AnalysisRun)
            .where(AnalysisRun.id == run_id, AnalysisRun.status == "queued")
            .values(status="running", started_at=_utcnow())
            .returning(AnalysisRun.id, AnalysisRun.paper_id)
        )
        .first()
    )
    if not claimed:
        return None

    run_id, paper_id = claimed

    paper = db.get(Paper, paper_id)
    if not paper:
        db.execute(
            update(AnalysisRun)
            .where(AnalysisRun.id == run_id)
            .values(status="failed", error="Paper missing", finished_at=_utcnow())
        )
        return None

    return Job(
        run_id=run_id,
        paper_id=paper.id,
        drive_file_id=paper.drive_file_id,
        doi=paper.doi,
        paper_title=paper.title,
        paper_abstract=paper.abstract,
        pdf_size_bytes=paper.pdf_size_bytes,
    )


def _update_run(db: Session, run_id: uuid.UUID, **fields) -> None:
    run = db.get(AnalysisRun, run_id)
    if not run:
        return
    for k, v in fields.items():
        setattr(run, k, v)
    db.add(run)


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


def _upsert_metadata(db: Session, paper: Paper, meta: dict) -> None:
    if not meta:
        return
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
    row.source = meta.get("source")

    if meta.get("title") and not paper.title:
        paper.title = meta.get("title")
    if meta.get("abstract") and not paper.abstract:
        paper.abstract = meta.get("abstract")

    db.add(row)
    db.add(paper)


def _build_repair_prompt(*, previous_json: dict, validation_error: str | None) -> str:
    err = (validation_error or "").strip() or "(unknown validation error)"
    prev = json.dumps(previous_json, ensure_ascii=False, separators=(",", ":"))
    return (
        "You previously generated a JSON object but it failed schema validation.\n\n"
        f"Validation error:\n{err}\n\n"
        "Task:\n"
        "- Fix the JSON to match the provided JSON Schema exactly.\n"
        "- Keep the content as close as possible.\n"
        "- Do NOT invent new evidence; only keep existing evidence or set evidence arrays to [].\n"
        "- If a field is missing, add it with a safe default (e.g., [] for arrays, \"\" for strings).\n"
        "- Output ONLY the corrected JSON.\n\n"
        f"Previous JSON:\n{prev}\n"
    )


def _process_job(job: Job) -> None:
    timings: dict[str, float] = {}
    t0 = time.perf_counter()

    has_pdf = True
    if job.drive_file_id.startswith(_DOI_ONLY_PREFIX):
        has_pdf = False

    if job.pdf_size_bytes and job.pdf_size_bytes > settings.max_pdf_mb * 1024 * 1024:
        raise RuntimeError(
            f"PDF too large ({job.pdf_size_bytes} bytes). "
            "Implement text-extract or split pipeline per main.txt 9.1."
        )

    meta = fetch_metadata_by_doi(job.doi) if job.doi else {}
    context = {
        "doi": job.doi,
        "title": meta.get("title") or job.paper_title,
        "abstract": meta.get("abstract") or job.paper_abstract,
        "authors": meta.get("authors") or [],
        "year": meta.get("year"),
        "venue": meta.get("venue"),
        "url": meta.get("url"),
        "has_pdf": has_pdf,
    }

    prompt = build_single_session_prompt(context)

    with tempfile.TemporaryDirectory(prefix="paper_review_") as tmpdir:
        pdf_path = Path(tmpdir) / "paper.pdf"
        pdf_sha: str | None = None
        file_size: int | None = None
        openai_file_id: str | None = None

        if has_pdf:
            if job.drive_file_id.startswith(_UPLOAD_PREFIX):
                src_path = settings.upload_dir / f"{job.paper_id}.pdf"
                if not src_path.exists():
                    raise RuntimeError(
                        "Uploaded PDF missing in this worker environment. "
                        "If API and Worker run as separate services (Cloudtype), local uploads are not "
                        "shared; set `UPLOAD_BACKEND=drive` (and configure Drive write creds) or "
                        "use a Drive file id instead."
                    )
                t_copy = time.perf_counter()
                shutil.copyfile(src_path, pdf_path)
                timings["local_copy_s"] = time.perf_counter() - t_copy
                logger.info(
                    "pdf_ready source=local_upload paper_id=%s bytes=%s elapsed_s=%.2f",
                    job.paper_id,
                    pdf_path.stat().st_size,
                    timings["local_copy_s"],
                )
            else:
                t_dl = time.perf_counter()
                download_drive_file(job.drive_file_id, pdf_path)
                timings["drive_download_s"] = time.perf_counter() - t_dl
                logger.info(
                    "pdf_ready source=drive paper_id=%s bytes=%s elapsed_s=%.2f",
                    job.paper_id,
                    pdf_path.stat().st_size,
                    timings["drive_download_s"],
                )

            file_size = pdf_path.stat().st_size
            if file_size > settings.max_pdf_mb * 1024 * 1024:
                raise RuntimeError(
                    f"PDF too large after load ({file_size} bytes). "
                    "Implement text-extract or split pipeline per main.txt 9.1."
                )

            pdf_sha = sha256_file(pdf_path)

            t_up = time.perf_counter()
            logger.info(
                "openai_file_upload_start paper_id=%s bytes=%s model=%s",
                job.paper_id,
                file_size,
                settings.openai_model,
            )
            openai_file_id = upload_file(pdf_path)
            timings["openai_upload_s"] = time.perf_counter() - t_up
            logger.info(
                "openai_file_upload_done paper_id=%s file_id=%s elapsed_s=%.2f",
                job.paper_id,
                openai_file_id,
                timings["openai_upload_s"],
            )

        try:
            with db_session() as db:
                _update_run(db, job.run_id, openai_file_id=openai_file_id, timings=timings)

            last_error: str | None = None
            last_candidate: dict | None = None
            canonical: dict | None = None
            for attempt in range(1, 4):
                t_resp = time.perf_counter()
                file_attached = bool(openai_file_id) and (attempt == 1 or last_candidate is None)
                call_file_id = openai_file_id if file_attached else None
                call_prompt = (
                    prompt
                    if attempt == 1
                    else (
                        _build_repair_prompt(previous_json=last_candidate, validation_error=last_error)
                        if last_candidate is not None
                        else f"{prompt}\n\nFix: {last_error}"
                    )
                )
                logger.info(
                    "openai_response_start paper_id=%s run_id=%s attempt=%s model=%s has_pdf=%s file_attached=%s",
                    job.paper_id,
                    job.run_id,
                    attempt,
                    settings.openai_model,
                    has_pdf,
                    file_attached,
                )
                try:
                    response_json = create_response(
                        prompt=call_prompt,
                        file_id=call_file_id,
                        json_schema=OPENAI_JSON_SCHEMA,
                    )
                except httpx.TimeoutException as e:
                    timings[f"openai_timeout_{attempt}_s"] = time.perf_counter() - t_resp
                    last_error = f"OpenAI timeout: {e}"
                    time.sleep(2 * attempt)
                    continue
                except httpx.HTTPError as e:
                    timings[f"openai_http_error_{attempt}_s"] = time.perf_counter() - t_resp
                    last_error = f"OpenAI HTTP error: {e}"
                    time.sleep(2 * attempt)
                    continue

                timings[f"openai_response_{attempt}_s"] = time.perf_counter() - t_resp
                logger.info(
                    "openai_response_done paper_id=%s run_id=%s attempt=%s elapsed_s=%.2f",
                    job.paper_id,
                    job.run_id,
                    attempt,
                    timings[f"openai_response_{attempt}_s"],
                )

                try:
                    candidate = extract_output_json(response_json)
                    last_candidate = candidate
                    parsed = validate_analysis(candidate)
                except Exception as e:  # noqa: BLE001
                    last_error = str(e)
                    logger.warning(
                        "openai_output_invalid paper_id=%s run_id=%s attempt=%s error=%s",
                        job.paper_id,
                        job.run_id,
                        attempt,
                        last_error,
                    )
                    continue

                canonical = parsed.model_dump()
                break

            if canonical is None:
                raise RuntimeError(f"Structured output validation failed: {last_error}")
        finally:
            if openai_file_id and settings.openai_delete_files:
                try:
                    delete_file(openai_file_id)
                except Exception:  # noqa: BLE001
                    logger.warning("openai_file_delete_failed file_id=%s", openai_file_id)

        content_md = render_markdown(canonical)
        evidence_rows = _extract_evidence_rows(canonical)

        with db_session() as db:
            paper = db.get(Paper, job.paper_id)
            run = db.get(AnalysisRun, job.run_id)
            if not paper or not run:
                return

            _upsert_metadata(db, paper, meta)

            existing = (
                db.execute(select(AnalysisOutput).where(AnalysisOutput.analysis_run_id == run.id))
                .scalars()
                .first()
            )
            if existing:
                db.delete(existing)
                db.flush()

            out = AnalysisOutput(
                analysis_run_id=run.id,
                canonical_json=canonical,
                content_md=content_md,
            )
            db.add(out)

            for ev in evidence_rows:
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

            run.status = "succeeded"
            run.error = None
            run.timings = {**(run.timings or {}), "total_s": time.perf_counter() - t0}
            run.finished_at = _utcnow()
            db.add(run)

            if pdf_sha and (not paper.pdf_sha256):
                paper.pdf_sha256 = pdf_sha
            if file_size and (not paper.pdf_size_bytes):
                paper.pdf_size_bytes = file_size
            db.add(paper)

        # OpenAI file deletion happens in the finally block above (success or failure).


def _mark_failed(run_id: uuid.UUID, err: Exception) -> None:
    with db_session() as db:
        _update_run(db, run_id, status="failed", error=str(err), finished_at=_utcnow())


def run_worker(*, once: bool = False) -> None:
    init_db()
    try:
        with db_session() as db:
            db.execute(text("select 1"))
    except Exception:  # noqa: BLE001
        logger.exception("db_connect_failed")
        raise

    logger.info("worker_started poll_s=%s", settings.worker_poll_seconds)
    while True:
        job: Job | None = None
        try:
            with db_session() as db:
                job = _claim_next_job(db)
        except Exception:  # noqa: BLE001
            logger.exception("claim_failed")
            if once:
                return
            time.sleep(settings.worker_poll_seconds)
            continue

        if not job:
            if once:
                return
            time.sleep(settings.worker_poll_seconds)
            continue

        try:
            logger.info("run_started run_id=%s paper_id=%s", job.run_id, job.paper_id)
            _process_job(job)
            logger.info("run_succeeded run_id=%s", job.run_id)
        except Exception as e:  # noqa: BLE001
            _mark_failed(job.run_id, e)
            logger.exception("run_failed run_id=%s", job.run_id)

        if once:
            return
