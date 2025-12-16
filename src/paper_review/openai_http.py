from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from paper_review.settings import settings


def _headers() -> dict[str, str]:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    return {"Authorization": f"Bearer {settings.openai_api_key}"}


def _timeout() -> httpx.Timeout:
    seconds = float(settings.openai_timeout_seconds)
    return httpx.Timeout(connect=30.0, read=seconds, write=seconds, pool=30.0)


def upload_file(path: Path) -> str:
    url = "https://api.openai.com/v1/files"
    with path.open("rb") as f:
        files = {"file": (path.name, f, "application/pdf")}
        data = {"purpose": "user_data"}
        with httpx.Client(timeout=_timeout()) as client:
            r = client.post(url, headers=_headers(), data=data, files=files)
            r.raise_for_status()
            return r.json()["id"]


def delete_file(file_id: str) -> None:
    url = f"https://api.openai.com/v1/files/{file_id}"
    with httpx.Client(timeout=30.0) as client:
        r = client.delete(url, headers=_headers())
        if r.status_code in (200, 204, 404):
            return
        r.raise_for_status()


def create_response(prompt: str, file_id: str | None, json_schema: dict[str, Any]) -> dict[str, Any]:
    url = "https://api.openai.com/v1/responses"

    content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
    if file_id:
        content.insert(0, {"type": "input_file", "file_id": file_id})

    body: dict[str, Any] = {
        "model": settings.openai_model,
        "input": [
            {
                "role": "user",
                "content": content,
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": json_schema["name"],
                "schema": json_schema["schema"],
                "strict": bool(json_schema.get("strict", True)),
            }
        },
    }

    with httpx.Client(timeout=_timeout()) as client:
        r = client.post(url, headers={**_headers(), "Content-Type": "application/json"}, json=body)
        r.raise_for_status()
        return r.json()


def extract_output_json(response_json: dict[str, Any]) -> dict[str, Any]:
    maybe_text = response_json.get("output_text")
    if isinstance(maybe_text, str) and maybe_text.strip():
        return json.loads(maybe_text)

    for item in response_json.get("output") or []:
        for content in item.get("content") or []:
            if content.get("type") == "output_json" and isinstance(content.get("json"), dict):
                return content["json"]
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return json.loads(content["text"])

    raise ValueError("Could not find structured output in response.")
