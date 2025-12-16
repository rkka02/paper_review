from __future__ import annotations

import uuid

from paper_review.db import db_session
from paper_review.models import AnalysisRun, Paper


def enqueue_analysis_run(paper_id: uuid.UUID) -> uuid.UUID:
    with db_session() as db:
        paper = db.get(Paper, paper_id)
        if not paper:
            raise ValueError(f"Paper not found: {paper_id}")

        run = AnalysisRun(paper_id=paper_id, stage="single_session_review", status="queued")
        db.add(run)
        db.flush()
        return run.id

