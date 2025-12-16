from __future__ import annotations

import threading

from fastapi import FastAPI

from paper_review.settings import settings
from paper_review.worker import run_worker

app = FastAPI(title="paper-review-worker", version="0.1.0")


@app.on_event("startup")
def _startup() -> None:
    t = threading.Thread(target=run_worker, kwargs={"once": False}, daemon=True)
    t.start()
    app.state.worker_thread = t


@app.get("/health")
def health() -> dict:
    t = getattr(app.state, "worker_thread", None)
    alive = bool(t and getattr(t, "is_alive", lambda: False)())
    return {"ok": True, "worker_alive": alive, "poll_s": settings.worker_poll_seconds}

