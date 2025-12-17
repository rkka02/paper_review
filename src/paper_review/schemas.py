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


class PaperSummaryOut(BaseModel):
    paper: PaperOut
    latest_run: AnalysisRunOut | None = None


class ReviewUpsert(BaseModel):
    one_liner: str | None = None
    summary: str | None = None
    pros: str | None = None
    cons: str | None = None
    rating_overall: int | None = Field(default=None, ge=0, le=5)
