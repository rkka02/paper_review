from __future__ import annotations


def render_markdown(canonical: dict) -> str:
    paper = canonical.get("paper") or {}
    meta = (paper.get("metadata") or {}) if isinstance(paper, dict) else {}
    title = meta.get("title") or "(untitled)"
    doi = meta.get("doi") or ""
    year = meta.get("year") or ""
    venue = meta.get("venue") or ""

    final = canonical.get("final_synthesis") or {}
    one_liner = final.get("one_liner") or ""

    strengths = final.get("strengths") or []
    weaknesses = final.get("weaknesses") or []

    lines: list[str] = []
    lines.append(f"# {title}")
    if any([doi, year, venue]):
        bits = [b for b in [str(year) if year else "", venue, doi] if b]
        lines.append("")
        lines.append(" / ".join(bits))

    if one_liner:
        lines.append("")
        lines.append(f"**One-liner:** {one_liner}")

    if strengths:
        lines.append("")
        lines.append("## Strengths")
        for s in strengths:
            lines.append(f"- {s}")

    if weaknesses:
        lines.append("")
        lines.append("## Weaknesses")
        for w in weaknesses:
            lines.append(f"- {w}")

    personas = canonical.get("personas") or []
    if personas:
        lines.append("")
        lines.append("## Personas")
        for p in personas:
            title_p = p.get("title") or p.get("id") or "persona"
            lines.append(f"### {title_p}")
            for h in p.get("highlights") or []:
                point = h.get("point")
                if point:
                    lines.append(f"- {point}")

    return "\n".join(lines).strip() + "\n"

