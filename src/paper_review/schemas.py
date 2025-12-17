from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class FolderCreate(BaseModel):
    name: str
    parent_id: uuid.UUID | None = None


class FolderUpdate(BaseModel):
    name: str | None = None
    parent_id: uuid.UUID | None = None


class FolderOut(BaseModel):
    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class PaperCreate(BaseModel):
    drive_file_id: str | None = None
    pdf_sha256: str | None = None
    pdf_size_bytes: int | None = None
    doi: str | None = None
    title: str | None = None
    folder_id: uuid.UUID | None = None


class PaperUpdate(BaseModel):
    status: str | None = None
    doi: str | None = None
    title: str | None = None
    folder_id: uuid.UUID | None = None
    memo: str | None = None


class PaperOut(BaseModel):
    id: uuid.UUID
    title: str | None
    doi: str | None
    drive_file_id: str
    pdf_sha256: str | None
    pdf_size_bytes: int | None
    abstract: str | None
    status: str
    folder_id: uuid.UUID | None
    memo: str | None
    metadata_row: "PaperMetadataOut | None" = None
    review: "ReviewOut | None" = None
    created_at: datetime
    updated_at: datetime


class AnalysisRunOut(BaseModel):
    id: uuid.UUID
    paper_id: uuid.UUID
    stage: str
    status: str
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PaperDetailOut(BaseModel):
    paper: PaperOut
    latest_run: AnalysisRunOut | None = None
    latest_output: dict | None = None
    latest_content_md: str | None = None
    links: list["PaperLinkNeighborOut"] = Field(default_factory=list)


class PaperSummaryOut(BaseModel):
    paper: PaperOut
    latest_run: AnalysisRunOut | None = None


class PaperEmbeddingVectorIn(BaseModel):
    paper_id: uuid.UUID
    vector: list[float]


class PaperEmbeddingsUpsert(BaseModel):
    provider: str
    model: str
    vectors: list[PaperEmbeddingVectorIn] = Field(default_factory=list)


class PaperLinkCreate(BaseModel):
    other_paper_id: uuid.UUID


class PaperLinkNeighborOut(BaseModel):
    id: uuid.UUID
    title: str | None
    doi: str | None
    folder_id: uuid.UUID | None


class PaperLinkOut(BaseModel):
    id: uuid.UUID
    a_paper_id: uuid.UUID
    b_paper_id: uuid.UUID
    source: str
    meta: dict | None = None
    created_at: datetime


class GraphNodeOut(BaseModel):
    id: uuid.UUID
    title: str | None
    doi: str | None
    folder_id: uuid.UUID | None


class PaperMetadataOut(BaseModel):
    paper_id: uuid.UUID
    authors: list[dict] | None
    year: int | None
    venue: str | None
    url: str | None
    source: str | None
    created_at: datetime
    updated_at: datetime


class ReviewOut(BaseModel):
    id: uuid.UUID
    paper_id: uuid.UUID
    one_liner: str | None
    summary: str | None
    pros: str | None
    cons: str | None
    rating_overall: int | None
    created_at: datetime
    updated_at: datetime


class GraphOut(BaseModel):
    nodes: list[GraphNodeOut]
    edges: list[PaperLinkOut]


class ReviewUpsert(BaseModel):
    one_liner: str | None = None
    summary: str | None = None
    pros: str | None = None
    cons: str | None = None
    rating_overall: int | None = Field(default=None, ge=0, le=5)


class RecommendationItemIn(BaseModel):
    kind: str
    folder_id: uuid.UUID | None = None
    rank: int = Field(ge=1)

    semantic_scholar_paper_id: str | None = None
    title: str
    doi: str | None = None
    url: str | None = None
    year: int | None = None
    venue: str | None = None
    authors: list[dict] | None = None
    abstract: str | None = None

    score: float | None = None
    one_liner: str | None = None
    summary: str | None = None
    rationale: dict | None = None


class RecommendationRunCreate(BaseModel):
    source: str = "local"
    meta: dict | None = None
    items: list[RecommendationItemIn] = Field(default_factory=list)


class RecommendationItemOut(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    kind: str
    folder_id: uuid.UUID | None
    rank: int

    semantic_scholar_paper_id: str | None
    title: str
    doi: str | None
    url: str | None
    year: int | None
    venue: str | None
    authors: list[dict] | None
    abstract: str | None

    score: float | None
    one_liner: str | None
    summary: str | None
    rationale: dict | None

    created_at: datetime


class RecommendationRunOut(BaseModel):
    id: uuid.UUID
    source: str
    meta: dict | None
    created_at: datetime
    items: list[RecommendationItemOut] = Field(default_factory=list)


class RecommendationTaskCreate(BaseModel):
    per_folder: int | None = Field(default=None, ge=1)
    cross_domain: int | None = Field(default=None, ge=0)
    random_seed: int | None = None


class RecommendationTaskOut(BaseModel):
    id: uuid.UUID
    trigger: str
    status: str
    config: dict | None
    logs: list[dict] | None
    run_id: uuid.UUID | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
