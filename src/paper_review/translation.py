from __future__ import annotations

import copy
import json
import re
from typing import Any

from paper_review.llm.providers import GoogleJsonLLM, LLMOutputParseError
from paper_review.settings import settings

_STRING_BATCH_SCHEMA: dict[str, Any] = {
    "name": "korean_translation_batch",
    "schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "text": {"type": ["string", "null"]},
                    },
                    "required": ["path", "text"],
                },
            }
        },
        "required": ["items"],
    },
    "strict": True,
}

_RECS_TRANSLATE_SCHEMA: dict[str, Any] = {
    "name": "recommendation_text_translation",
    "schema": {
        "type": "object",
        "properties": {
            "one_liner": {"type": ["string", "null"]},
            "summary": {"type": ["string", "null"]},
            "abstract": {"type": ["string", "null"]},
        },
        "required": ["one_liner", "summary", "abstract"],
        "additionalProperties": False,
    },
    "strict": True,
}


def translation_enabled() -> bool:
    return bool((settings.google_ai_api_key or "").strip())


def translation_style() -> str:
    style = (settings.translation_style or "").strip()
    return style or "디씨인사이드 말투"


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


_URL_RE = re.compile(r"^(https?://|www\.)", re.IGNORECASE)
_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

_SKIP_KEYS = {
    "doi",
    "url",
    "id",
    "severity",
    "status",
    "code_status",
    "data_status",
}

_SKIP_SUBTREES: tuple[tuple[str | int, ...], ...] = (
    ("paper", "metadata", "authors"),
)


def _is_under_skip_subtree(path: tuple[str | int, ...]) -> bool:
    return any(path[: len(prefix)] == prefix for prefix in _SKIP_SUBTREES)


def _looks_like_identifier(text: str) -> bool:
    s = (text or "").strip()
    if not s:
        return True
    if _URL_RE.match(s):
        return True
    if _DOI_RE.match(s):
        return True
    if _UUID_RE.match(s):
        return True
    return False


def _should_translate_string(*, text: str, path: tuple[str | int, ...]) -> bool:
    if _is_under_skip_subtree(path):
        return False
    key = path[-1] if path else None
    if isinstance(key, str) and key in _SKIP_KEYS:
        return False
    if _looks_like_identifier(text):
        return False
    return True


def _path_to_str(path: tuple[str | int, ...]) -> str:
    return "/" + "/".join(str(x) for x in path)


def _collect_translatable_strings(
    obj: Any,
    *,
    path: tuple[str | int, ...],
    out: list[tuple[tuple[str | int, ...], str]],
) -> None:
    if _is_under_skip_subtree(path):
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            _collect_translatable_strings(v, path=path + (k,), out=out)
        return
    if isinstance(obj, list):
        for i, v in enumerate(obj):
            _collect_translatable_strings(v, path=path + (i,), out=out)
        return
    if isinstance(obj, str):
        if _should_translate_string(text=obj, path=path):
            out.append((path, obj))


def _set_at_path(root: Any, path: tuple[str | int, ...], value: Any) -> None:
    if not path:
        raise ValueError("Empty path.")
    cur = root
    for seg in path[:-1]:
        cur = cur[seg]
    cur[path[-1]] = value


def _batch_items(items: list[dict[str, Any]], *, max_chars: int, max_items: int) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    buf: list[dict[str, Any]] = []
    chars = 0
    for it in items:
        text = str(it.get("text") or "")
        add = len(text)
        if buf and (len(buf) >= max_items or chars + add > max_chars):
            batches.append(buf)
            buf = []
            chars = 0
        buf.append(it)
        chars += add
    if buf:
        batches.append(buf)
    return batches


def _translate_items_batch(
    llm: GoogleJsonLLM,
    *,
    items: list[dict[str, Any]],
    style: str,
) -> dict[str, str]:
    payload = {"items": items}
    system = "You are a meticulous translator who rewrites natural-language text into Korean."
    user = (
        "Rewrite each item's text into Korean using the requested tone.\n"
        "Rules:\n"
        "- Return EXACTLY the same JSON object shape as the input: {\"items\": [{\"path\": ..., \"text\": ...}, ...]}.\n"
        "- Do NOT change any `path` values.\n"
        "- Do NOT add/remove/reorder items.\n"
        "- Preserve any URLs/DOIs/IDs inside text exactly, and NEVER wrap URLs in Markdown.\n"
        "- Keep meaning; translate only natural-language.\n"
        f"- Tone: {style}\n\n"
        "Input JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n"
    )
    out = llm.generate_json(system=system, user=user, json_schema=_STRING_BATCH_SCHEMA)
    if not isinstance(out, dict) or not isinstance(out.get("items"), list):
        raise ValueError("Invalid translation output shape.")
    out_items = out["items"]
    if len(out_items) != len(items):
        raise ValueError("Translation output item count mismatch.")
    input_paths = []
    for src in items:
        p = src.get("path")
        if not isinstance(p, str) or not p:
            raise ValueError("Invalid translation input path.")
        input_paths.append(p)
    input_set = set(input_paths)
    if len(input_set) != len(input_paths):
        raise ValueError("Translation input paths must be unique.")

    mapping: dict[str, str] = {}
    seen: set[str] = set()
    for it in out_items:
        if not isinstance(it, dict):
            continue
        path = it.get("path")
        if not isinstance(path, str) or not path:
            continue
        if path in seen:
            raise ValueError("Translation output path duplicated.")
        if path not in input_set:
            raise ValueError("Translation output path mismatch.")
        seen.add(path)
        text = _normalize_text(it.get("text"))
        if not text:
            continue
        mapping[path] = text
    if seen != input_set:
        raise ValueError("Translation output paths incomplete.")
    return mapping


def _translate_items_with_retry(
    llm: GoogleJsonLLM,
    *,
    items: list[dict[str, Any]],
    style: str,
) -> dict[str, str]:
    if not items:
        return {}
    try:
        return _translate_items_batch(llm, items=items, style=style)
    except (LLMOutputParseError, ValueError):
        if len(items) <= 1:
            raise
        mid = len(items) // 2
        left = _translate_items_with_retry(llm, items=items[:mid], style=style)
        right = _translate_items_with_retry(llm, items=items[mid:], style=style)
        left.update(right)
        return left


def translate_analysis_json(canonical: dict) -> dict | None:
    if not canonical:
        return None
    llm = GoogleJsonLLM(model=settings.google_ai_model, api_key=settings.google_ai_api_key)
    style = translation_style()

    found: list[tuple[tuple[str | int, ...], str]] = []
    _collect_translatable_strings(canonical, path=(), out=found)
    if not found:
        return copy.deepcopy(canonical)

    items: list[dict[str, Any]] = []
    path_map: dict[str, tuple[str | int, ...]] = {}
    for path, text in found:
        path_str = _path_to_str(path)
        path_map[path_str] = path
        items.append({"path": path_str, "text": text})

    out = copy.deepcopy(canonical)
    for batch in _batch_items(items, max_chars=6000, max_items=30):
        mapping = _translate_items_with_retry(llm, items=batch, style=style)
        for path_str, translated in mapping.items():
            path = path_map.get(path_str)
            if not path:
                continue
            _set_at_path(out, path, translated)
    return out


def translate_recommendation_texts(
    *,
    one_liner: str | None,
    summary: str | None,
    abstract: str | None,
) -> dict[str, str | None] | None:
    payload = {
        "one_liner": _normalize_text(one_liner),
        "summary": _normalize_text(summary),
        "abstract": _normalize_text(abstract),
    }
    if not any(payload.values()):
        return None

    llm = GoogleJsonLLM(model=settings.google_ai_model, api_key=settings.google_ai_api_key)
    style = translation_style()

    system = "You are a Korean translator who rewrites recommendation snippets in a specific tone."
    user = (
        "Translate the fields into Korean using the requested tone.\n"
        "Rules:\n"
        "- Keep null values as null.\n"
        "- Do not add or remove keys.\n"
        f"- Tone: {style}\n\n"
        "Input JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n"
    )
    out = llm.generate_json(system=system, user=user, json_schema=_RECS_TRANSLATE_SCHEMA)
    if not isinstance(out, dict):
        return None
    return {
        "one_liner": _normalize_text(out.get("one_liner")),
        "summary": _normalize_text(out.get("summary")),
        "abstract": _normalize_text(out.get("abstract")),
    }
