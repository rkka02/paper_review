from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=200)
    why: str = Field(min_length=1)


class Author(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    affiliation: str | None = None


class PaperMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None
    authors: list[Author]
    year: int | None = Field(default=None, ge=0)
    venue: str | None
    doi: str | None
    url: str | None


class PaperInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: PaperMetadata
    abstract: str | None


class SectionMapItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    summary: str


class FigureItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    page: int = Field(ge=1)
    caption: str
    why_important: str


class TableItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    page: int = Field(ge=1)
    caption: str
    why_important: str


class ContributionOrClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[Evidence]


class LimitationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    status: Literal["known", "unknown"]
    evidence: list[Evidence]


class Reproducibility(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code_status: Literal["available", "unavailable", "unknown"]
    data_status: Literal["available", "unavailable", "unknown"]
    notes: str
    evidence: list[Evidence]


class Normalized(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_map: list[SectionMapItem]
    figures: list[FigureItem]
    tables: list[TableItem]
    contributions: list[ContributionOrClaim]
    claims: list[ContributionOrClaim]
    limitations: list[LimitationItem]
    method_summary: str
    experiments_summary: str
    reproducibility: Reproducibility


class PersonaHighlight(BaseModel):
    model_config = ConfigDict(extra="forbid")

    point: str
    severity: Literal["low", "med", "high"]
    evidence: list[Evidence]

class PersonaBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    highlights: list[PersonaHighlight]


class SuggestedRating(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall: int = Field(ge=0, le=5)
    confidence: float = Field(ge=0.0, le=1.0)


class FinalSynthesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    one_liner: str
    strengths: list[str]
    weaknesses: list[str]
    who_should_read: list[str]
    suggested_rating: SuggestedRating
    evidence: list[Evidence]


class Diagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unknowns: list[str]
    notes: str


class PaperAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper: PaperInfo
    normalized: Normalized
    personas: list[PersonaBlock]
    final_synthesis: FinalSynthesis
    diagnostics: Diagnostics


EVIDENCE_JSON_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["page", "quote", "why"],
    "properties": {
        "page": {"type": "integer"},
        "quote": {"type": "string", "maxLength": 200},
        "why": {"type": "string"},
    },
}

OPENAI_JSON_SCHEMA: dict = {
    "name": "paper_review_single_session",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["paper", "normalized", "personas", "final_synthesis", "diagnostics"],
        "properties": {
            "paper": {
                "type": "object",
                "additionalProperties": False,
                "required": ["metadata", "abstract"],
                "properties": {
                    "metadata": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["title", "authors", "year", "venue", "doi", "url"],
                        "properties": {
                            "title": {"type": ["string", "null"]},
                            "authors": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["name", "affiliation"],
                                    "properties": {
                                        "name": {"type": "string"},
                                        "affiliation": {"type": ["string", "null"]},
                                    },
                                },
                            },
                            "year": {"type": ["integer", "null"]},
                            "venue": {"type": ["string", "null"]},
                            "doi": {"type": ["string", "null"]},
                            "url": {"type": ["string", "null"]},
                        },
                    },
                    "abstract": {"type": ["string", "null"]},
                },
            },
            "normalized": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "section_map",
                    "figures",
                    "tables",
                    "contributions",
                    "claims",
                    "limitations",
                    "method_summary",
                    "experiments_summary",
                    "reproducibility",
                ],
                "properties": {
                    "section_map": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["name", "page_start", "page_end", "summary"],
                            "properties": {
                                "name": {"type": "string"},
                                "page_start": {"type": "integer"},
                                "page_end": {"type": "integer"},
                                "summary": {"type": "string"},
                            },
                        },
                    },
                    "figures": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["id", "page", "caption", "why_important"],
                            "properties": {
                                "id": {"type": "string"},
                                "page": {"type": "integer"},
                                "caption": {"type": "string"},
                                "why_important": {"type": "string"},
                            },
                        },
                    },
                    "tables": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["id", "page", "caption", "why_important"],
                            "properties": {
                                "id": {"type": "string"},
                                "page": {"type": "integer"},
                                "caption": {"type": "string"},
                                "why_important": {"type": "string"},
                            },
                        },
                    },
                    "contributions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["text", "confidence", "evidence"],
                            "properties": {
                                "text": {"type": "string"},
                                "confidence": {"type": "number"},
                                "evidence": {"type": "array", "items": EVIDENCE_JSON_SCHEMA},
                            },
                        },
                    },
                    "claims": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["text", "confidence", "evidence"],
                            "properties": {
                                "text": {"type": "string"},
                                "confidence": {"type": "number"},
                                "evidence": {"type": "array", "items": EVIDENCE_JSON_SCHEMA},
                            },
                        },
                    },
                    "limitations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["text", "status", "evidence"],
                            "properties": {
                                "text": {"type": "string"},
                                "status": {"type": "string", "enum": ["known", "unknown"]},
                                "evidence": {"type": "array", "items": EVIDENCE_JSON_SCHEMA},
                            },
                        },
                    },
                    "method_summary": {"type": "string"},
                    "experiments_summary": {"type": "string"},
                    "reproducibility": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["code_status", "data_status", "notes", "evidence"],
                        "properties": {
                            "code_status": {
                                "type": "string",
                                "enum": ["available", "unavailable", "unknown"],
                            },
                            "data_status": {
                                "type": "string",
                                "enum": ["available", "unavailable", "unknown"],
                            },
                            "notes": {"type": "string"},
                            "evidence": {"type": "array", "items": EVIDENCE_JSON_SCHEMA},
                        },
                    },
                },
            },
            "personas": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "title", "highlights"],
                    "properties": {
                        "id": {"type": "string"},
                        "title": {"type": "string"},
                        "highlights": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["point", "severity", "evidence"],
                                "properties": {
                                    "point": {"type": "string"},
                                    "severity": {"type": "string", "enum": ["low", "med", "high"]},
                                    "evidence": {"type": "array", "items": EVIDENCE_JSON_SCHEMA},
                                },
                            },
                        },
                    },
                },
            },
            "final_synthesis": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "one_liner",
                    "strengths",
                    "weaknesses",
                    "who_should_read",
                    "suggested_rating",
                    "evidence",
                ],
                "properties": {
                    "one_liner": {"type": "string"},
                    "strengths": {"type": "array", "items": {"type": "string"}},
                    "weaknesses": {"type": "array", "items": {"type": "string"}},
                    "who_should_read": {"type": "array", "items": {"type": "string"}},
                    "suggested_rating": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["overall", "confidence"],
                        "properties": {
                            "overall": {"type": "integer"},
                            "confidence": {"type": "number"},
                        },
                    },
                    "evidence": {"type": "array", "items": EVIDENCE_JSON_SCHEMA},
                },
            },
            "diagnostics": {
                "type": "object",
                "additionalProperties": False,
                "required": ["unknowns", "notes"],
                "properties": {
                    "unknowns": {"type": "array", "items": {"type": "string"}},
                    "notes": {"type": "string"},
                },
            },
        },
    },
}


def validate_analysis(data: dict) -> PaperAnalysis:
    return PaperAnalysis.model_validate(data)
