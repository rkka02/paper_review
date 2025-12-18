from __future__ import annotations

import json
from typing import Any

import httpx


def _clip(text: str, limit: int = 1900) -> str:
    s = (text or "").strip()
    if not s:
        return ""
    if len(s) <= limit:
        return s
    return s[: max(0, limit - 1)].rstrip() + "…"


def send_discord_webhook(
    *,
    url: str,
    content: str,
    username: str | None = None,
    avatar_url: str | None = None,
    embeds: list[dict[str, Any]] | None = None,
    thread_id: int | None = None,
    timeout_seconds: float = 20.0,
) -> None:
    webhook_url = (url or "").strip()
    if not webhook_url:
        raise RuntimeError("Discord webhook url is empty.")

    body: dict[str, Any] = {"content": _clip(content, 1900)}
    if username:
        body["username"] = str(username)[:80]
    if avatar_url:
        body["avatar_url"] = str(avatar_url)
    if embeds:
        body["embeds"] = embeds

    timeout = httpx.Timeout(connect=10.0, read=timeout_seconds, write=timeout_seconds, pool=10.0)
    with httpx.Client(timeout=timeout) as client:
        params: dict[str, str] | None = None
        if thread_id is not None:
            params = {"thread_id": str(int(thread_id))}
        r = client.post(webhook_url, params=params, json=body)
        if r.status_code >= 400:
            detail = ""
            try:
                payload = r.json()
                detail = json.dumps(payload, ensure_ascii=False)[:500]
            except Exception:  # noqa: BLE001
                detail = (r.text or "")[:500]
            raise RuntimeError(f"Discord webhook error ({r.status_code}): {detail}".strip())
