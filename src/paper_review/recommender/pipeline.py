from __future__ import annotations

import json
import random
import time
import uuid
from dataclasses import asdict, dataclass
from collections.abc import Callable

from paper_review.embeddings import Embedder, get_embedder
from paper_review.llm import JsonLLM, get_decider_llm, get_query_llm
from paper_review.recommender.query import LLMQueryGenerator
from paper_review.recommender.seed import RandomSeedSelector, SeedSelector
from paper_review.schemas import RecommendationItemIn, RecommendationRunCreate
from paper_review.semantic_scholar import fetch_citations_by_doi, fetch_references_by_doi, search_papers


def _dot(a: list[float], b: list[float]) -> float:
    return float(sum(x * y for x, y in zip(a, b, strict=False)))


def _l2_normalize(vec: list[float]) -> list[float]:
    s = 0.0
    for v in vec:
        s += float(v) * float(v)
    if s <= 0:
        return vec
    inv = (s ** 0.5) ** -1
    return [float(x) * inv for x in vec]


def _mean_vec(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    dim = len(vectors[0])
    out = [0.0] * dim
    for v in vectors:
        for i, x in enumerate(v):
            out[i] += float(x)
    inv = 1.0 / float(len(vectors))
    return [x * inv for x in out]


def _paper_text(paper: dict) -> str:
    title = (paper.get("title") or "").strip()
    doi = (paper.get("doi") or "").strip()
    abstract = (paper.get("abstract") or "").strip()
    parts: list[str] = []
    if title:
        parts.append(f"Title: {title}")
    if doi:
        parts.append(f"DOI: {doi}")
    if abstract:
        parts.append(f"Abstract: {abstract}")
    if not parts:
        return "(paper)"
    return "\n".join(parts)


def _candidate_key(c: dict) -> str:
    doi = (c.get("doi") or "").strip().lower()
    if doi:
        return f"doi:{doi}"
    pid = (c.get("paper_id") or "").strip()
    if pid:
        return f"ss:{pid}"
    title = (c.get("title") or "").strip().lower()
    return f"title:{title}" if title else f"anon:{id(c)}"


def _clip(text: str | None, n: int) -> str | None:
    t = (text or "").strip()
    if not t:
        return None
    if len(t) <= n:
        return t
    return t[:n].rstrip() + "…"


def _safe_uuid(v: str | None) -> uuid.UUID | None:
    if not v:
        return None
    try:
        return uuid.UUID(str(v))
    except Exception:  # noqa: BLE001
        return None


@dataclass(slots=True)
class RecommenderConfig:
    per_folder: int = 3
    cross_domain: int = 3

    seeds_per_folder: int = 5
    queries_per_folder: int = 3
    search_limit: int = 50
    ref_limit: int = 40
    citation_limit: int = 40
    top_candidates_per_folder: int = 20
    top_candidates_cross_domain: int = 40
    polite_sleep_s: float = 0.25

    random_seed: int | None = None


def _decide_topk(
    *,
    llm: JsonLLM,
    group_label: str,
    candidates: list[dict],
    k: int,
    mode: str,
) -> list[dict]:
    k = max(1, int(k))
    pool = candidates[: max(k, 1)]

    sys = "You are a research assistant. Select the best papers to read next."
    rows = []
    for c in candidates[:20]:
        rows.append(
            {
                "id": c["id"],
                "title": c.get("title"),
                "year": c.get("year"),
                "venue": c.get("venue"),
                "doi": c.get("doi"),
                "url": c.get("url"),
                "score": c.get("score"),
                "abstract": _clip(c.get("abstract"), 600),
            }
        )
    user = (
        f"Group: {group_label}\n"
        f"Mode: {mode}\n\n"
        f"Pick exactly {k} papers from the candidate list.\n"
        "Rules:\n"
        "- Prefer novelty + usefulness.\n"
        "- Avoid near-duplicates.\n"
        "- Keep summaries short (1 sentence).\n"
        "- Provide a 1-sentence one_liner explaining why this is recommended for the group.\n"
        "- Reasons should be 2–3 short bullet strings.\n\n"
        f"Candidates (JSON):\n{json.dumps(rows, ensure_ascii=False)}\n"
    )
    schema = {
        "name": "recommendation_picks",
        "schema": {
            "type": "object",
            "properties": {
                "picks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "summary": {"type": "string"},
                            "one_liner": {"type": "string"},
                            "reasons": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                        },
                        "required": ["id", "summary", "one_liner", "reasons"],
                        "additionalProperties": False,
                    },
                    "minItems": k,
                    "maxItems": k,
                }
            },
            "required": ["picks"],
            "additionalProperties": False,
        },
        "strict": True,
    }

    try:
        out = llm.generate_json(system=sys, user=user, json_schema=schema)
        picks = out.get("picks")
        if not isinstance(picks, list):
            raise RuntimeError("LLM did not return picks[].")
        by_id = {c["id"]: c for c in candidates}
        selected: list[dict] = []
        for p in picks:
            if not isinstance(p, dict):
                continue
            pid = str(p.get("id") or "").strip()
            if not pid or pid not in by_id:
                continue
            base = dict(by_id[pid])
            base["llm_summary"] = (p.get("summary") or "").strip() or None
            base["llm_one_liner"] = (p.get("one_liner") or "").strip() or None
            reasons = p.get("reasons")
            if isinstance(reasons, list):
                base["llm_reasons"] = [str(x) for x in reasons if str(x).strip()]
            selected.append(base)
        if len(selected) != k:
            raise RuntimeError("LLM returned invalid picks.")
        return selected
    except Exception:
        return pool[:k]


def build_recommendations(
    *,
    folders: list[dict],
    paper_summaries: list[dict],
    config: RecommenderConfig | None = None,
    embedder: Embedder | None = None,
    query_llm: JsonLLM | None = None,
    decider_llm: JsonLLM | None = None,
    seed_selector: SeedSelector | None = None,
    progress: Callable[[str], None] | None = None,
) -> RecommendationRunCreate:
    cfg = config or RecommenderConfig()
    rng = random.Random(cfg.random_seed)

    embedder = embedder or get_embedder()
    query_llm = query_llm or get_query_llm()
    decider_llm = decider_llm or get_decider_llm()
    seed_selector = seed_selector or RandomSeedSelector()
    qgen = LLMQueryGenerator(llm=query_llm)

    folder_name_by_id = {str(f.get("id")): str(f.get("name") or "") for f in folders if isinstance(f, dict)}

    library: list[dict] = []
    for row in paper_summaries:
        paper = (row or {}).get("paper") if isinstance(row, dict) else None
        if not isinstance(paper, dict):
            continue
        library.append(paper)

    library_dois = {((p.get("doi") or "").strip().lower()) for p in library if (p.get("doi") or "").strip()}
    library_titles = {((p.get("title") or "").strip().lower()) for p in library if (p.get("title") or "").strip()}

    by_folder: dict[str, list[dict]] = {}
    for p in library:
        fid = str(p.get("folder_id") or "")
        if not fid:
            continue
        by_folder.setdefault(fid, []).append(p)

    folder_ids = [fid for fid, papers in by_folder.items() if papers]
    if progress:
        progress(f"Prepared library: {len(folder_ids)} folder(s), {len(library)} paper(s).")

    folder_seeds: dict[str, list[dict]] = {}
    folder_queries: dict[str, list[str]] = {}
    for fid in folder_ids:
        seeds = seed_selector.select(by_folder[fid], cfg.seeds_per_folder, rng=rng)
        folder_seeds[fid] = seeds
        fname = folder_name_by_id.get(fid) or "(folder)"
        folder_queries[fid] = qgen.generate(folder_name=fname, seeds=seeds, n_queries=cfg.queries_per_folder, cross_domain=False)
    if progress:
        progress(f"Generated in-domain queries for {len(folder_ids)} folder(s).")

    cross_seeds = seed_selector.select(library, cfg.seeds_per_folder, rng=rng)
    cross_queries = qgen.generate(
        folder_name="(cross-domain)",
        seeds=cross_seeds,
        n_queries=cfg.queries_per_folder,
        cross_domain=True,
    )
    if progress:
        progress("Generated cross-domain queries.")

    candidate_by_key: dict[str, dict] = {}
    candidate_keys_by_folder: dict[str, set[str]] = {fid: set() for fid in folder_ids}
    cross_candidate_keys: set[str] = set()

    def add_candidates(keys: set[str], rows: list[dict]) -> None:
        for c in rows or []:
            if not isinstance(c, dict):
                continue
            title = (c.get("title") or "").strip()
            if not title:
                continue
            key = _candidate_key(c)
            if key not in candidate_by_key:
                candidate_by_key[key] = c
            keys.add(key)

    for fid in folder_ids:
        if progress:
            progress(f"Collecting candidates: folder={folder_name_by_id.get(fid) or fid}")
        for q in folder_queries.get(fid) or []:
            if progress:
                progress(f"Search: {q}")
            add_candidates(candidate_keys_by_folder[fid], search_papers(q, limit=cfg.search_limit, offset=0))
            time.sleep(cfg.polite_sleep_s)

        for s in folder_seeds.get(fid) or []:
            doi = (s.get("doi") or "").strip()
            if not doi:
                continue
            if progress:
                progress(f"References/Citations: doi={doi}")
            add_candidates(candidate_keys_by_folder[fid], fetch_references_by_doi(doi, limit=cfg.ref_limit, offset=0))
            time.sleep(cfg.polite_sleep_s)
            add_candidates(candidate_keys_by_folder[fid], fetch_citations_by_doi(doi, limit=cfg.citation_limit, offset=0))
            time.sleep(cfg.polite_sleep_s)

    if progress:
        progress("Collecting candidates: cross-domain")
    for q in cross_queries:
        if progress:
            progress(f"Search: {q}")
        add_candidates(cross_candidate_keys, search_papers(q, limit=cfg.search_limit, offset=0))
        time.sleep(cfg.polite_sleep_s)

    for s in cross_seeds:
        doi = (s.get("doi") or "").strip()
        if not doi:
            continue
        if progress:
            progress(f"References/Citations: doi={doi}")
        add_candidates(cross_candidate_keys, fetch_references_by_doi(doi, limit=cfg.ref_limit, offset=0))
        time.sleep(cfg.polite_sleep_s)
        add_candidates(cross_candidate_keys, fetch_citations_by_doi(doi, limit=cfg.citation_limit, offset=0))
        time.sleep(cfg.polite_sleep_s)

    def is_already_in_library(c: dict) -> bool:
        doi = (c.get("doi") or "").strip().lower()
        if doi and doi in library_dois:
            return True
        title = (c.get("title") or "").strip().lower()
        if title and title in library_titles:
            return True
        return False

    for fid in folder_ids:
        candidate_keys_by_folder[fid] = {k for k in candidate_keys_by_folder[fid] if not is_already_in_library(candidate_by_key[k])}
    cross_candidate_keys = {k for k in cross_candidate_keys if not is_already_in_library(candidate_by_key[k])}
    if progress:
        progress(
            "Filtered candidates already in library: "
            f"folders={sum(len(candidate_keys_by_folder[f]) for f in folder_ids)} cross={len(cross_candidate_keys)}"
        )

    folder_texts: list[str] = [_paper_text(p) for p in library]
    folder_vecs = embedder.embed_passages(folder_texts)
    if len(folder_vecs) != len(folder_texts):
        raise RuntimeError("Embedding output count mismatch for library.")
    if progress:
        progress(f"Embedded library papers: {len(folder_vecs)}")

    folder_rep_by_id: dict[str, list[float]] = {}
    for fid in folder_ids:
        indices = [i for i, p in enumerate(library) if str(p.get("folder_id") or "") == fid]
        vecs = [folder_vecs[i] for i in indices if i < len(folder_vecs)]
        rep = _l2_normalize(_mean_vec(vecs)) if vecs else []
        if rep:
            folder_rep_by_id[fid] = rep

    all_candidate_keys = sorted({*cross_candidate_keys, *(set().union(*candidate_keys_by_folder.values()) if folder_ids else set())})
    candidate_texts = [_paper_text(candidate_by_key[k]) for k in all_candidate_keys]
    if progress:
        progress(f"Embedding candidates: {len(all_candidate_keys)}")
    candidate_vecs = embedder.embed_passages(candidate_texts)
    if len(candidate_vecs) != len(all_candidate_keys):
        raise RuntimeError("Embedding output count mismatch for candidates.")

    cand_vec_by_key = {k: v for k, v in zip(all_candidate_keys, candidate_vecs, strict=True)}

    folder_items: dict[str, list[dict]] = {}
    for fid in folder_ids:
        rep = folder_rep_by_id.get(fid)
        if not rep:
            continue
        scored: list[dict] = []
        for key in candidate_keys_by_folder[fid]:
            vec = cand_vec_by_key.get(key)
            if vec is None:
                continue
            c = candidate_by_key[key]
            scored.append(
                {
                    "id": key,
                    "paper_id": c.get("paper_id"),
                    "title": c.get("title"),
                    "doi": c.get("doi"),
                    "url": c.get("url"),
                    "year": c.get("year"),
                    "venue": c.get("venue"),
                    "authors": c.get("authors"),
                    "abstract": c.get("abstract"),
                    "score": _dot(vec, rep),
                }
            )
        scored.sort(key=lambda x: float(x.get("score") or 0.0), reverse=True)
        folder_items[fid] = scored[: max(0, int(cfg.top_candidates_per_folder))]

    cross_scored: list[dict] = []
    reps = list(folder_rep_by_id.values())
    rep_keys = list(folder_rep_by_id.keys())
    for key in cross_candidate_keys:
        vec = cand_vec_by_key.get(key)
        if vec is None:
            continue
        sims = [(_dot(vec, rep), rep_keys[i]) for i, rep in enumerate(reps)]
        sims.sort(reverse=True, key=lambda x: x[0])
        s1 = float(sims[0][0]) if sims else 0.0
        s2 = float(sims[1][0]) if len(sims) > 1 else 0.0
        c = candidate_by_key[key]
        cross_scored.append(
            {
                "id": key,
                "paper_id": c.get("paper_id"),
                "title": c.get("title"),
                "doi": c.get("doi"),
                "url": c.get("url"),
                "year": c.get("year"),
                "venue": c.get("venue"),
                "authors": c.get("authors"),
                "abstract": c.get("abstract"),
                "score": s1 + s2,
                "top_folders": [fid for _, fid in sims[:3]],
            }
        )
    cross_scored.sort(key=lambda x: float(x.get("score") or 0.0), reverse=True)
    cross_scored = cross_scored[: max(0, int(cfg.top_candidates_cross_domain))]

    items: list[RecommendationItemIn] = []

    for fid in folder_ids:
        candidates = folder_items.get(fid) or []
        if not candidates:
            continue
        chosen = _decide_topk(
            llm=decider_llm,
            group_label=folder_name_by_id.get(fid) or fid,
            candidates=candidates,
            k=cfg.per_folder,
            mode="folder",
        )
        folder_uuid = _safe_uuid(fid)
        for idx, c in enumerate(chosen, start=1):
            one_liner = (c.get("llm_one_liner") or "").strip() or None
            if not one_liner:
                reasons = c.get("llm_reasons") or []
                if isinstance(reasons, list):
                    one_liner = "; ".join([str(x).strip() for x in reasons if str(x).strip()][:2]) or None
            items.append(
                RecommendationItemIn(
                    kind="folder",
                    folder_id=folder_uuid,
                    rank=idx,
                    semantic_scholar_paper_id=c.get("paper_id"),
                    title=str(c.get("title") or "").strip() or "(untitled)",
                    doi=(str(c.get("doi") or "").strip() or None),
                    url=(str(c.get("url") or "").strip() or None),
                    year=c.get("year"),
                    venue=(str(c.get("venue") or "").strip() or None),
                    authors=c.get("authors"),
                    abstract=_clip(c.get("abstract"), 1500),
                    score=float(c.get("score")) if c.get("score") is not None else None,
                    one_liner=one_liner,
                    summary=(c.get("llm_summary") or None),
                    rationale={"reasons": c.get("llm_reasons")} if c.get("llm_reasons") else None,
                )
            )

    if cross_scored:
        chosen = _decide_topk(
            llm=decider_llm,
            group_label="cross-domain",
            candidates=cross_scored,
            k=cfg.cross_domain,
            mode="cross-domain",
        )
        for idx, c in enumerate(chosen, start=1):
            one_liner = (c.get("llm_one_liner") or "").strip() or None
            if not one_liner:
                reasons = c.get("llm_reasons") or []
                if isinstance(reasons, list):
                    one_liner = "; ".join([str(x).strip() for x in reasons if str(x).strip()][:2]) or None
            items.append(
                RecommendationItemIn(
                    kind="cross_domain",
                    folder_id=None,
                    rank=idx,
                    semantic_scholar_paper_id=c.get("paper_id"),
                    title=str(c.get("title") or "").strip() or "(untitled)",
                    doi=(str(c.get("doi") or "").strip() or None),
                    url=(str(c.get("url") or "").strip() or None),
                    year=c.get("year"),
                    venue=(str(c.get("venue") or "").strip() or None),
                    authors=c.get("authors"),
                    abstract=_clip(c.get("abstract"), 1500),
                    score=float(c.get("score")) if c.get("score") is not None else None,
                    one_liner=one_liner,
                    summary=(c.get("llm_summary") or None),
                    rationale={"reasons": c.get("llm_reasons"), "top_folders": c.get("top_folders")}
                    if (c.get("llm_reasons") or c.get("top_folders"))
                    else None,
                )
            )

    meta = {
        "config": asdict(cfg),
        "seed_selector": getattr(seed_selector, "name", "unknown"),
        "queries": {
            "by_folder": {fid: folder_queries.get(fid) for fid in folder_ids},
            "cross_domain": cross_queries,
        },
        "seeds": {
            "by_folder": {
                fid: [{"title": s.get("title"), "doi": s.get("doi")} for s in (folder_seeds.get(fid) or [])]
                for fid in folder_ids
            },
            "cross_domain": [{"title": s.get("title"), "doi": s.get("doi")} for s in cross_seeds],
        },
        "embeddings": {"provider": getattr(embedder, "provider", "unknown"), "model": getattr(embedder, "model", "unknown")},
        "llm": {
            "query": {"provider": getattr(query_llm, "provider", "unknown"), "model": getattr(query_llm, "model", "unknown")},
            "decider": {"provider": getattr(decider_llm, "provider", "unknown"), "model": getattr(decider_llm, "model", "unknown")},
        },
        "counts": {
            "library": len(library),
            "folders": len(folder_ids),
            "candidates_total": len(all_candidate_keys),
        },
    }

    return RecommendationRunCreate(source="local_recommender", meta=meta, items=items)
