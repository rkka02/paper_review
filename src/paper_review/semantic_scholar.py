from __future__ import annotations

import httpx

from paper_review.settings import settings


def fetch_metadata_by_doi(doi: str) -> dict:
    """
    Best-effort DOI metadata enrichment using Semantic Scholar Graph API.
    Returns a dict with keys: title, abstract, authors(list), year, venue, url, doi.
    """
    doi = doi.strip()
    if not doi:
        return {}

    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
    params = {"fields": "title,abstract,authors,year,venue,url,externalIds"}
    headers: dict[str, str] = {}
    if settings.semantic_scholar_api_key:
        headers["x-api-key"] = settings.semantic_scholar_api_key

    with httpx.Client(timeout=20.0) as client:
        r = client.get(url, params=params, headers=headers)
        if r.status_code == 404:
            return {}
        r.raise_for_status()
        data = r.json()

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

    with httpx.Client(timeout=20.0) as client:
        r = client.get(url, params=params, headers=headers)
        r.raise_for_status()
        payload = r.json()

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
