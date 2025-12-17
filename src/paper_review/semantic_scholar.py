from __future__ import annotations

import logging
import random
import time
from typing import Any
from urllib.parse import quote

import httpx

from paper_review.settings import settings

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_DOI_TO_PAPER_ID_CACHE: dict[str, str | None] = {}


def _ss_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    if settings.semantic_scholar_api_key:
        headers["x-api-key"] = settings.semantic_scholar_api_key
    return headers


def _resolve_paper_id_from_doi(doi: str) -> str | None:
    doi_norm = (doi or "").strip().lower()
    if not doi_norm:
        return None
    if doi_norm in _DOI_TO_PAPER_ID_CACHE:
        return _DOI_TO_PAPER_ID_CACHE[doi_norm]

    rows = search_papers(doi_norm, limit=5, offset=0)

    pid: str | None = None
    for r in rows:
        if not isinstance(r, dict):
            continue
        rdoi = (r.get("doi") or "").strip().lower()
        if rdoi and rdoi == doi_norm:
            pid = (str(r.get("paper_id") or "").strip() or None)
            if pid:
                break
    if not pid:
        for r in rows:
            if not isinstance(r, dict):
                continue
            pid = (str(r.get("paper_id") or "").strip() or None)
            if pid:
                break

    _DOI_TO_PAPER_ID_CACHE[doi_norm] = pid
    return pid


def _retry_sleep_seconds(*, attempt: int, response: httpx.Response | None) -> float:
    if response is not None and response.status_code == 429:
        retry_after = (response.headers.get("retry-after") or "").strip()
        if retry_after.isdigit():
            return min(60.0, float(int(retry_after)))
    base = min(10.0, 0.7 * (2**attempt))
    return base + random.random() * 0.25


def _get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 20.0,
    max_retries: int = 4,
) -> dict | None:
    """
    Best-effort GET JSON with retries on Semantic Scholar transient errors.

    - Returns dict on success
    - Returns None on 404 or after exhausting retries for retryable errors
    - Raises on non-retryable HTTP errors (e.g., 400/401/403)
    """
    headers = headers or {}
    with httpx.Client(timeout=timeout_seconds) as client:
        last_err: Exception | None = None
        last_status: int | None = None
        for attempt in range(max_retries + 1):
            resp: httpx.Response | None = None
            try:
                resp = client.get(url, params=params, headers=headers)
                last_status = resp.status_code

                if resp.status_code == 404:
                    return None

                if resp.status_code in _RETRYABLE_STATUS:
                    if attempt >= max_retries:
                        break
                    time.sleep(_retry_sleep_seconds(attempt=attempt, response=resp))
                    continue

                resp.raise_for_status()
                try:
                    payload = resp.json()
                except Exception as e:  # noqa: BLE001
                    last_err = e
                    if attempt >= max_retries:
                        break
                    time.sleep(_retry_sleep_seconds(attempt=attempt, response=resp))
                    continue
                if not isinstance(payload, dict):
                    return None
                return payload
            except httpx.HTTPStatusError as e:
                last_err = e
                if resp is not None and resp.status_code in _RETRYABLE_STATUS and attempt < max_retries:
                    time.sleep(_retry_sleep_seconds(attempt=attempt, response=resp))
                    continue
                raise
            except httpx.HTTPError as e:
                last_err = e
                if attempt >= max_retries:
                    break
                time.sleep(_retry_sleep_seconds(attempt=attempt, response=resp))
                continue

        if last_status in _RETRYABLE_STATUS:
            logger.warning("semantic_scholar_retry_exhausted url=%s status=%s", url, last_status)
        elif last_err is not None:
            logger.warning("semantic_scholar_failed url=%s error=%s", url, type(last_err).__name__)
        return None


def fetch_metadata_by_doi(doi: str) -> dict:
    """
    Best-effort DOI metadata enrichment using Semantic Scholar Graph API.
    Returns a dict with keys: title, abstract, authors(list), year, venue, url, doi.
    """
    doi = doi.strip()
    if not doi:
        return {}

    doi_key = quote(f"DOI:{doi}", safe="")
    url = f"https://api.semanticscholar.org/graph/v1/paper/{doi_key}"
    params = {"fields": "title,abstract,authors,year,venue,url,externalIds"}
    headers = _ss_headers()

    data = _get_json(url, params=params, headers=headers, timeout_seconds=20.0, max_retries=4)
    if not data:
        paper_id = _resolve_paper_id_from_doi(doi)
        if paper_id:
            pid_key = quote(paper_id, safe="")
            url2 = f"https://api.semanticscholar.org/graph/v1/paper/{pid_key}"
            data = _get_json(url2, params=params, headers=headers, timeout_seconds=20.0, max_retries=4)
    data = data or {}

    authors = []
    for a in data.get("authors") or []:
        if not a:
            continue
        authors.append({"name": a.get("name") or "", "affiliation": None})

    return {
        "title": data.get("title"),
        "abstract": data.get("abstract"),
        "authors": authors,
        "year": data.get("year"),
        "venue": data.get("venue"),
        "url": data.get("url"),
        "doi": (data.get("externalIds") or {}).get("DOI") or doi,
        "source": "semantic_scholar",
    }


def search_papers(query: str, limit: int = 20, offset: int = 0) -> list[dict]:
    """
    Search papers using Semantic Scholar Graph API.

    Returns a list of dicts with keys: paper_id, title, abstract, authors(list), year, venue, url, doi.
    """
    q = (query or "").strip()
    if not q:
        return []

    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))

    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": q,
        "limit": str(limit),
        "offset": str(offset),
        "fields": "paperId,title,abstract,authors,year,venue,url,externalIds",
    }

    headers: dict[str, str] = {}
    if settings.semantic_scholar_api_key:
        headers["x-api-key"] = settings.semantic_scholar_api_key

    payload = _get_json(url, params=params, headers=headers, timeout_seconds=20.0, max_retries=4)
    if not payload:
        return []

    out: list[dict] = []
    for row in payload.get("data") or []:
        if not row or not isinstance(row, dict):
            continue

        paper_id = row.get("paperId")
        if not paper_id:
            continue

        authors: list[dict] = []
        for a in row.get("authors") or []:
            if not a:
                continue
            authors.append({"name": a.get("name") or "", "affiliation": None})

        out.append(
            {
                "paper_id": paper_id,
                "title": row.get("title"),
                "abstract": row.get("abstract"),
                "authors": authors,
                "year": row.get("year"),
                "venue": row.get("venue"),
                "url": row.get("url"),
                "doi": (row.get("externalIds") or {}).get("DOI"),
                "source": "semantic_scholar",
            }
        )
    return out


def fetch_references_by_doi(doi: str, limit: int = 50, offset: int = 0) -> list[dict]:
    """
    Fetch references for a paper (by DOI) using Semantic Scholar Graph API.

    Returns a list of dicts with keys: paper_id, title, abstract, authors(list), year, venue, url, doi.
    """
    doi = (doi or "").strip()
    if not doi:
        return []

    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))

    doi_key = quote(f"DOI:{doi}", safe="")
    url = f"https://api.semanticscholar.org/graph/v1/paper/{doi_key}/references"
    # NOTE: Requesting `abstract` on /references can trigger S2 Graph API 500s for some papers.
    # Keep this list intentionally conservative.
    params = {
        "limit": str(limit),
        "offset": str(offset),
        "fields": "paperId,title,authors,year,venue,url,externalIds",
    }

    headers = _ss_headers()

    payload = _get_json(url, params=params, headers=headers, timeout_seconds=20.0, max_retries=4)
    if not payload:
        payload = _get_json(
            url,
            params={"limit": str(limit), "offset": str(offset)},
            headers=headers,
            timeout_seconds=20.0,
            max_retries=4,
        )
    if not payload:
        paper_id = _resolve_paper_id_from_doi(doi)
        if paper_id:
            pid_key = quote(paper_id, safe="")
            url2 = f"https://api.semanticscholar.org/graph/v1/paper/{pid_key}/references"
            payload = _get_json(url2, params=params, headers=headers, timeout_seconds=20.0, max_retries=4)
            if not payload:
                payload = _get_json(
                    url2,
                    params={"limit": str(limit), "offset": str(offset)},
                    headers=headers,
                    timeout_seconds=20.0,
                    max_retries=4,
                )
    if not payload:
        return []

    out: list[dict] = []
    for row in payload.get("data") or []:
        cited = (row or {}).get("citedPaper") if isinstance(row, dict) else None
        if not cited or not isinstance(cited, dict):
            continue
        paper_id = cited.get("paperId")
        if not paper_id:
            continue

        authors: list[dict] = []
        for a in cited.get("authors") or []:
            if not a:
                continue
            authors.append({"name": a.get("name") or "", "affiliation": None})

        out.append(
            {
                "paper_id": paper_id,
                "title": cited.get("title"),
                "abstract": cited.get("abstract"),
                "authors": authors,
                "year": cited.get("year"),
                "venue": cited.get("venue"),
                "url": cited.get("url"),
                "doi": (cited.get("externalIds") or {}).get("DOI"),
                "source": "semantic_scholar",
            }
        )
    return out


def fetch_citations_by_doi(doi: str, limit: int = 50, offset: int = 0) -> list[dict]:
    """
    Fetch citations for a paper (by DOI) using Semantic Scholar Graph API.

    Returns a list of dicts with keys: paper_id, title, abstract, authors(list), year, venue, url, doi.
    """
    doi = (doi or "").strip()
    if not doi:
        return []

    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))

    doi_key = quote(f"DOI:{doi}", safe="")
    url = f"https://api.semanticscholar.org/graph/v1/paper/{doi_key}/citations"
    # NOTE: Requesting `abstract` on /citations can trigger S2 Graph API 500s for some papers.
    # Keep this list intentionally conservative.
    params = {
        "limit": str(limit),
        "offset": str(offset),
        "fields": "paperId,title,authors,year,venue,url,externalIds",
    }

    headers = _ss_headers()

    payload = _get_json(url, params=params, headers=headers, timeout_seconds=20.0, max_retries=4)
    if not payload:
        payload = _get_json(
            url,
            params={"limit": str(limit), "offset": str(offset)},
            headers=headers,
            timeout_seconds=20.0,
            max_retries=4,
        )
    if not payload:
        paper_id = _resolve_paper_id_from_doi(doi)
        if paper_id:
            pid_key = quote(paper_id, safe="")
            url2 = f"https://api.semanticscholar.org/graph/v1/paper/{pid_key}/citations"
            payload = _get_json(url2, params=params, headers=headers, timeout_seconds=20.0, max_retries=4)
            if not payload:
                payload = _get_json(
                    url2,
                    params={"limit": str(limit), "offset": str(offset)},
                    headers=headers,
                    timeout_seconds=20.0,
                    max_retries=4,
                )
    if not payload:
        return []

    out: list[dict] = []
    for row in payload.get("data") or []:
        citing = (row or {}).get("citingPaper") if isinstance(row, dict) else None
        if not citing or not isinstance(citing, dict):
            continue
        paper_id = citing.get("paperId")
        if not paper_id:
            continue

        authors: list[dict] = []
        for a in citing.get("authors") or []:
            if not a:
                continue
            authors.append({"name": a.get("name") or "", "affiliation": None})

        out.append(
            {
                "paper_id": paper_id,
                "title": citing.get("title"),
                "abstract": citing.get("abstract"),
                "authors": authors,
                "year": citing.get("year"),
                "venue": citing.get("venue"),
                "url": citing.get("url"),
                "doi": (citing.get("externalIds") or {}).get("DOI"),
                "source": "semantic_scholar",
            }
        )
    return out
