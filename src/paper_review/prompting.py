from __future__ import annotations

PERSONAS = [
    {
        "id": "optimist",
        "title": "Optimist",
        "focus": "Key strengths, novelty, what works well, and why it matters.",
    },
    {
        "id": "critics",
        "title": "Critics",
        "focus": "Key weaknesses, unstated assumptions, and where claims may be overreaching.",
    },
    {
        "id": "theory",
        "title": "Theory",
        "focus": "Theoretical grounding, assumptions/justification, and whether the method is principled.",
    },
    {
        "id": "experimenter",
        "title": "Experimenter",
        "focus": "Experimental design, baselines, ablations, metrics, and whether results support claims.",
    },
    {
        "id": "literature_scout",
        "title": "Literature Scout",
        "focus": "Closest related work to compare against and what to read next (use web search if available).",
    },
]


def build_single_session_prompt(context: dict) -> str:
    doi = context.get("doi") or ""
    title = context.get("title") or ""
    abstract = context.get("abstract") or ""
    authors = context.get("authors") or []
    year = context.get("year") or ""
    venue = context.get("venue") or ""
    url = context.get("url") or ""
    has_pdf = bool(context.get("has_pdf", True))

    personas_text = "\n".join(
        [f'- id="{p["id"]}", title="{p["title"]}": {p["focus"]}' for p in PERSONAS]
    )

    no_pdf_rules = ""
    if not has_pdf:
        no_pdf_rules = """

No-PDF mode:
- You did NOT receive the PDF. Do NOT invent page numbers or quotes.
- Set: normalized.section_map = [], normalized.figures = [], normalized.tables = [].
- For ALL evidence arrays in the schema: use [] (empty).
- Prefer "unknown"/low-confidence where appropriate and record unknowns in diagnostics.unknowns.
""".rstrip()

    return f"""You are reviewing an academic paper.

You MUST produce a single JSON object that matches the provided JSON Schema exactly.
Do not output Markdown. Do not add keys that are not in the schema.

Evidence rules (strict):
- For every non-trivial claim, contribution, limitation, and persona highlight: include evidence objects.
- Each evidence object must include: page number, a short direct quote (<=200 chars), and why that quote supports the point.
- If you cannot find evidence, leave the evidence array empty and record the uncertainty in diagnostics.unknowns (no guessing).
{no_pdf_rules}

Output size limits (keep it concise):
- section_map: <= 12 items (1–2 sentence summaries)
- figures/tables: <= 10 each (only the most important)
- contributions/claims/limitations: <= 5 each (prioritize the most central)
- per persona: highlights <= 6
- final_synthesis: strengths <= 6, weaknesses <= 6, who_should_read <= 5

Context (best-effort, may be incomplete):
- title: {title}
- authors: {", ".join([a.get("name","") for a in authors if isinstance(a, dict)])}
- year: {year}
- venue: {venue}
- doi: {doi}
- url: {url}
- abstract: {abstract}

Process (do this internally, but output only JSON):
1) Normalize the paper: section map, figures/tables, contributions, claims, limitations, method + experiments + reproducibility.
2) Run the following personas sequentially, referencing the normalized information and given file if given. :
{personas_text}
3) Provide a final synthesis (one-liner, strengths/weaknesses, who should read, suggested rating) with evidence.
"""
