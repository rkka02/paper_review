from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, time as dtime, timedelta, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import selectinload

from paper_review.db import db_session, init_db
from paper_review.embeddings import get_embedder
from paper_review.embeddings.store import paper_embedding_text
from paper_review.llm import get_decider_llm, get_query_llm
from paper_review.models import (
    Folder,
    Paper,
    PaperEmbedding,
    RecommendationItem,
    RecommendationRun,
    RecommendationTask,
)
from paper_review.recommender.pipeline import RecommenderConfig, build_recommendations
from paper_review.recommender.seed import RandomSeedSelector
from paper_review.settings import settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _append_log(task_id: uuid.UUID, message: str, *, level: str = "info") -> None:
    msg = (message or "").strip()
    if not msg:
        return
    try:
        with db_session() as db:
            task = db.get(RecommendationTask, task_id)
            if not task:
                return
            logs = list(task.logs or [])
            logs.append({"ts": _utcnow().isoformat(), "level": level, "message": msg})
            task.logs = logs
            db.add(task)
    except Exception:
        # best-effort only; do not crash the run due to logging failures
        return


def _update_task(
    task_id: uuid.UUID,
    *,
    status: str | None = None,
    run_id: uuid.UUID | None = None,
    error: str | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> None:
    with db_session() as db:
        task = db.get(RecommendationTask, task_id)
        if not task:
            return
        if status is not None:
            task.status = status
        if run_id is not None:
            task.run_id = run_id
        if error is not None:
            task.error = error
        if started_at is not None:
            task.started_at = started_at
        if finished_at is not None:
            task.finished_at = finished_at
        db.add(task)


def _persist_recommendations(payload) -> uuid.UUID:
    with db_session() as db:
        run = RecommendationRun(source=(payload.source or "server").strip() or "server", meta=payload.meta)
        db.add(run)
        db.flush()

        for item in payload.items:
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
                    abstract=(item.abstract or "").strip() or None,
                    score=float(item.score) if item.score is not None else None,
                    one_liner=(item.one_liner or "").strip() or None,
                    summary=(item.summary or "").strip() or None,
                    rationale=item.rationale,
                )
            )

        db.flush()
        return run.id


def _sync_missing_embeddings(
    *,
    task_id: uuid.UUID,
    embedder,
) -> int:
    provider = getattr(embedder, "provider", "unknown")
    model = getattr(embedder, "model", "unknown")

    with db_session() as db:
        papers = (
            db.execute(
                select(Paper)
                .options(selectinload(Paper.metadata_row), selectinload(Paper.review))
                .order_by(desc(Paper.created_at))
            )
            .scalars()
            .all()
        )
        if not papers:
            return 0

        ids = [p.id for p in papers]
        existing = (
            db.execute(select(PaperEmbedding).where(PaperEmbedding.paper_id.in_(ids))).scalars().all()
        )
        emb_by_id = {e.paper_id: e for e in existing}

        missing = [p for p in papers if (p.id not in emb_by_id) or (emb_by_id[p.id].provider != provider) or (emb_by_id[p.id].model != model)]

    if not missing:
        _append_log(task_id, f"Embeddings: up-to-date ({provider}/{model}).")
        return 0

    _append_log(task_id, f"Embeddings: syncing {len(missing)} paper(s) ({provider}/{model}).")

    batch = 64
    upserts = 0
    total = len(missing)
    total_batches = (total + batch - 1) // batch
    for i in range(0, len(missing), batch):
        batch_idx = i // batch + 1
        chunk = missing[i : i + batch]
        _append_log(task_id, f"Embeddings: batch {batch_idx}/{total_batches} ({len(chunk)} paper(s))...")
        texts = [paper_embedding_text(p) for p in chunk]
        vecs = embedder.embed_passages(texts)
        if len(vecs) != len(chunk):
            raise RuntimeError("Embedding output count mismatch (sync).")

        dim = len(vecs[0]) if vecs else 0
        with db_session() as db:
            for paper, vec in zip(chunk, vecs, strict=True):
                row = db.get(PaperEmbedding, paper.id)
                if row is None:
                    db.add(
                        PaperEmbedding(
                            paper_id=paper.id,
                            provider=provider,
                            model=model,
                            dim=dim,
                            vector=vec,
                        )
                    )
                else:
                    row.provider = provider
                    row.model = model
                    row.dim = dim
                    row.vector = vec
                upserts += 1
        _append_log(task_id, f"Embeddings: batch {batch_idx}/{total_batches} done ({upserts}/{total}).")

    _append_log(task_id, f"Embeddings: synced {upserts} paper(s).")
    return upserts


def run_recommendation_task(task_id: uuid.UUID) -> None:
    init_db()
    started = _utcnow()
    _update_task(task_id, status="running", started_at=started, error=None)
    _append_log(task_id, "Started recommendation run.")

    try:
        cfg = RecommenderConfig()
        trigger = "manual"
        with db_session() as db:
            task = db.get(RecommendationTask, task_id)
            if task and task.trigger:
                trigger = str(task.trigger)
            raw = (task.config or {}) if task and isinstance(task.config, dict) else {}
            if "per_folder" in raw:
                cfg.per_folder = int(raw["per_folder"])
            if "cross_domain" in raw:
                cfg.cross_domain = int(raw["cross_domain"])
            if "random_seed" in raw and raw["random_seed"] is not None:
                cfg.random_seed = int(raw["random_seed"])

        embedder = get_embedder()
        query_llm = get_query_llm()
        decider_llm = get_decider_llm()

        _append_log(
            task_id,
            f"LLM: query={getattr(query_llm, 'provider', '?')}/{getattr(query_llm, 'model', '?')} "
            f"decider={getattr(decider_llm, 'provider', '?')}/{getattr(decider_llm, 'model', '?')}",
        )
        _append_log(
            task_id,
            f"Embeddings: {getattr(embedder, 'provider', '?')}/{getattr(embedder, 'model', '?')}",
        )

        _sync_missing_embeddings(task_id=task_id, embedder=embedder)

        with db_session() as db:
            folders = db.execute(select(Folder).order_by(Folder.created_at.asc())).scalars().all()
            papers = (
                db.execute(
                    select(Paper)
                    .options(selectinload(Paper.metadata_row), selectinload(Paper.review))
                    .order_by(desc(Paper.created_at))
                )
                .scalars()
                .all()
            )

        folders_in = [{"id": str(f.id), "name": f.name, "parent_id": str(f.parent_id) if f.parent_id else None} for f in folders]
        paper_summaries = []
        for p in papers:
            meta = p.metadata_row
            review = p.review
            paper_summaries.append(
                {
                    "paper": {
                        "id": str(p.id),
                        "title": p.title,
                        "doi": p.doi,
                        "abstract": p.abstract,
                        "folder_id": str(p.folder_id) if p.folder_id else None,
                        "status": p.status,
                        "memo": p.memo,
                        "authors": (meta.authors if meta else None),
                        "year": (meta.year if meta else None),
                        "venue": (meta.venue if meta else None),
                        "url": (meta.url if meta else None),
                        "review": (
                            {
                                "one_liner": review.one_liner,
                                "summary": review.summary,
                                "pros": review.pros,
                                "cons": review.cons,
                                "rating_overall": review.rating_overall,
                            }
                            if review
                            else None
                        ),
                    },
                    "latest_run": None,
                }
            )

        _append_log(task_id, f"Loaded library: {len(folders_in)} folder(s), {len(paper_summaries)} paper(s).")

        def progress(msg: str) -> None:
            _append_log(task_id, msg)

        payload = build_recommendations(
            folders=folders_in,
            paper_summaries=paper_summaries,
            config=cfg,
            embedder=embedder,
            query_llm=query_llm,
            decider_llm=decider_llm,
            seed_selector=RandomSeedSelector(),
            progress=progress,
        )

        _append_log(task_id, f"Generated payload: {len(payload.items)} item(s). Saving to DB...")
        run_id = _persist_recommendations(payload)
        _append_log(task_id, f"Saved recommendations: run_id={run_id}.")

        _update_task(task_id, status="succeeded", run_id=run_id, finished_at=_utcnow())
        _append_log(task_id, "Done.")

        if settings.discord_notify_recommender:
            try:
                from paper_review.discord.webhook import send_discord_webhook

                url = (settings.discord_notify_webhook_url or settings.discord_webhook_url or "").strip()
                if url:
                    intro = (
                        "사서 알림) 자동 추천 업데이트가 끝났어요."
                        if trigger == "auto"
                        else "사서 알림) 새 추천 목록을 정리해뒀어요."
                    )
                    send_discord_webhook(
                        url=url,
                        content=(
                            f"{intro}\n"
                            f"총 {len(payload.items)}편이에요. Web UI의 Recs 탭에서 확인해 주세요."
                        ),
                        username=settings.discord_notify_username,
                        avatar_url=settings.discord_notify_avatar_url,
                    )
            except Exception:
                pass
    except Exception as e:  # noqa: BLE001
        _append_log(task_id, f"Failed: {type(e).__name__}: {e}", level="error")
        _update_task(task_id, status="failed", error=str(e), finished_at=_utcnow())

        if settings.discord_notify_recommender:
            try:
                from paper_review.discord.webhook import send_discord_webhook

                url = (settings.discord_notify_webhook_url or settings.discord_webhook_url or "").strip()
                if url:
                    err = str(e)
                    if len(err) > 240:
                        err = err[:240].rstrip() + "..."
                    send_discord_webhook(
                        url=url,
                        content=(
                            "사서 알림) 추천 목록을 정리하다가 문제가 생겼어요.\n"
                            "잠시 후 다시 시도해 주세요.\n"
                            f"(오류: {type(e).__name__}: {err})"
                        ),
                        username=settings.discord_notify_username,
                        avatar_url=settings.discord_notify_avatar_url,
                    )
            except Exception:
                pass


def _start_task_thread(task_id: uuid.UUID) -> None:
    def runner() -> None:
        try:
            run_recommendation_task(task_id)
        finally:
            with _TASK_THREADS_LOCK:
                _TASK_THREADS.pop(task_id, None)

    t = threading.Thread(target=runner, daemon=True)
    with _TASK_THREADS_LOCK:
        _TASK_THREADS[task_id] = t
    t.start()


_TASK_THREADS: dict[uuid.UUID, threading.Thread] = {}
_TASK_THREADS_LOCK = threading.Lock()


def _is_task_thread_alive(task_id: uuid.UUID) -> bool:
    with _TASK_THREADS_LOCK:
        t = _TASK_THREADS.get(task_id)
    return bool(t and t.is_alive())


def is_task_thread_alive(task_id: uuid.UUID) -> bool:
    return _is_task_thread_alive(task_id)


def reconcile_stale_running_tasks() -> int:
    """
    Marks any `status=running` tasks as failed if there is no in-process runner thread.

    This helps recover from dev server reloads / crashes (daemon thread dies, DB row stays running).
    """
    init_db()
    now = _utcnow()

    with db_session() as db:
        tasks = db.execute(select(RecommendationTask).where(RecommendationTask.status == "running")).scalars().all()
        stale = [t for t in tasks if not _is_task_thread_alive(t.id)]
        if not stale:
            return 0

        msg = "Stale running task (no active runner in this process)."
        for t in stale:
            logs = list(t.logs or [])
            logs.append({"ts": now.isoformat(), "level": "error", "message": msg})
            t.logs = logs
            t.status = "failed"
            t.error = msg
            t.finished_at = now
            db.add(t)
        return len(stale)


def enqueue_recommendation_task(*, trigger: str = "manual", config: dict | None = None) -> uuid.UUID:
    """
    Create (or reuse) a queued task and start it in a background thread.
    Returns the task id.
    """
    init_db()
    with db_session() as db:
        existing_running = (
            db.execute(
                select(RecommendationTask)
                .where(RecommendationTask.status == "running")
                .order_by(desc(RecommendationTask.created_at))
                .limit(1)
            )
            .scalars()
            .first()
        )
        if existing_running:
            if _is_task_thread_alive(existing_running.id):
                return existing_running.id

            existing_running.status = "failed"
            existing_running.error = "Stale running task (no active runner in this process)."
            existing_running.finished_at = _utcnow()
            db.add(existing_running)
            db.flush()

        task = RecommendationTask(
            trigger=(trigger or "manual").strip() or "manual",
            status="running",
            config=config,
            logs=[],
            error=None,
            started_at=_utcnow(),
        )
        db.add(task)
        db.flush()
        task_id = task.id

    _start_task_thread(task_id)
    return task_id


_SCHEDULER_THREAD: threading.Thread | None = None


def _parse_hhmm(value: str) -> dtime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        parts = raw.split(":")
        if len(parts) != 2:
            return None
        h = int(parts[0])
        m = int(parts[1])
        if h < 0 or h > 23 or m < 0 or m > 59:
            return None
        return dtime(hour=h, minute=m)
    except Exception:  # noqa: BLE001
        return None


def _next_run_at_local(target: dtime) -> datetime:
    now = datetime.now()
    today = now.replace(hour=target.hour, minute=target.minute, second=0, microsecond=0)
    if today > now:
        return today
    return today + timedelta(days=1)


def _scheduler_loop() -> None:
    while True:
        if not settings.recommender_auto_run:
            time.sleep(30.0)
            continue

        target = _parse_hhmm(settings.recommender_auto_run_time)
        if target is None:
            time.sleep(60.0)
            continue

        nxt = _next_run_at_local(target)
        sleep_s = max(1.0, (nxt - datetime.now()).total_seconds())
        time.sleep(sleep_s)

        if not settings.recommender_auto_run:
            continue

        try:
            enqueue_recommendation_task(trigger="auto", config={"auto_time": settings.recommender_auto_run_time})
        except Exception:
            # Don't kill the scheduler loop on failures; next tick will retry.
            continue


def start_recommender_scheduler() -> None:
    global _SCHEDULER_THREAD  # noqa: PLW0603
    if _SCHEDULER_THREAD and _SCHEDULER_THREAD.is_alive():
        return
    t = threading.Thread(target=_scheduler_loop, daemon=True)
    _SCHEDULER_THREAD = t
    t.start()
