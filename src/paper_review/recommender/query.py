from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from paper_review.llm import JsonLLM


def _seed_brief(p: dict) -> str:
    title = (p.get("title") or "").strip()
    abstract = (p.get("abstract") or "").strip()
    if not title and not abstract:
        return "(missing title/abstract)"
    if abstract and len(abstract) > 500:
        abstract = abstract[:500].rstrip() + "..."
    if abstract:
        return f"- {title}\n  {abstract}"
    return f"- {title}"


_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{2,}")
_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "using",
    "use",
    "used",
    "based",
    "via",
    "towards",
    "toward",
    "approach",
    "approaches",
    "method",
    "methods",
    "model",
    "models",
    "paper",
    "study",
    "studies",
    "results",
    "result",
    "analysis",
    "data",
    "new",
    "novel",
    "system",
    "systems",
    "framework",
    "frameworks",
    "review",
}


def _fallback_queries(*, folder_name: str, seeds: list[dict], n: int, cross_domain: bool) -> list[str]:
    text = " ".join(
        [
            str(folder_name or ""),
            *[str((p.get("title") or "")) for p in (seeds or [])],
            *[str((p.get("abstract") or "")) for p in (seeds or [])],
        ]
    ).lower()
    words = [w for w in _WORD_RE.findall(text) if w not in _STOPWORDS]
    counts = Counter(words)
    top = [w for w, _ in counts.most_common(30)]
    if not top:
        top = ["research", "paper", "method", "application", "experiment"]

    folder_tokens = [
        w for w in _WORD_RE.findall(str(folder_name or "").lower()) if w not in _STOPWORDS
    ]
    cross_terms = ["biology", "optics", "physics", "medical", "imaging", "neuroscience", "robotics"]

    queries: list[str] = []
    for i in range(n):
        terms = top[i * 6 : i * 6 + 8]
        if len(terms) < 4:
            terms = (terms + top)[:8]
        if folder_tokens:
            terms = (terms + folder_tokens)[:10]
        if cross_domain:
            extra = cross_terms[i % len(cross_terms)]
            if extra not in terms:
                terms = (terms + ["application", extra])[:10]
        else:
            if "survey" not in terms:
                terms = (terms + ["survey"])[:10]
        if len(terms) < 4:
            terms = (terms + ["research", "study", "method"])[:4]
        queries.append(" ".join(terms[:10]))
    return queries[:n]


@dataclass(slots=True)
class LLMQueryGenerator:
    llm: JsonLLM

    def generate(
        self,
        *,
        folder_name: str,
        seeds: list[dict],
        n_queries: int,
        cross_domain: bool,
    ) -> list[str]:
        n = max(1, int(n_queries))
        sys = (
            "You generate short keyword search queries for Semantic Scholar. "
            "You must be precise and concise."
        )
        mode = "cross-domain" if cross_domain else "in-domain"
        seed_text = "\n".join(_seed_brief(p) for p in seeds[:8]) or "(no seeds)"
        user = (
            f"Task: Generate {n} Semantic Scholar search queries.\n"
            f"Mode: {mode}\n"
            f"Folder: {folder_name}\n\n"
            "Constraints:\n"
            "- Each query should be 4-10 keywords.\n"
            "- Do NOT use quotes, parentheses, or boolean operators.\n"
            "- Use plain English keywords (technical terms OK).\n"
            "- Cross-domain mode: include at least 1 query that would surface papers from a different field "
            "but plausibly applicable to the folder topic.\n\n"
            f"Seeds:\n{seed_text}\n"
        )
        schema = {
            "name": "semantic_scholar_queries",
            "schema": {
                "type": "object",
                "properties": {
                    "queries": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": n,
                        "maxItems": n,
                    }
                },
                "required": ["queries"],
                "additionalProperties": False,
            },
            "strict": True,
        }

        last_err: Exception | None = None
        for _ in range(3):
            try:
                out = self.llm.generate_json(system=sys, user=user, json_schema=schema)
                queries = out.get("queries")
                if not isinstance(queries, list):
                    raise RuntimeError("LLM did not return queries[].")
                cleaned: list[str] = []
                for q in queries:
                    if not isinstance(q, str):
                        continue
                    v = q.strip()
                    if not v:
                        continue
                    cleaned.append(v)
                if len(cleaned) < n:
                    raise RuntimeError(f"LLM returned too few queries: {len(cleaned)}/{n}")
                return cleaned[:n]
            except Exception as e:  # noqa: BLE001
                last_err = e
                continue

        _ = last_err  # retained for debugging in stack traces
        return _fallback_queries(folder_name=folder_name, seeds=seeds, n=n, cross_domain=cross_domain)
