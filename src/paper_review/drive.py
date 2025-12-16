from __future__ import annotations

import json
from pathlib import Path

import httpx
from google.auth.transport.requests import Request
from google.oauth2 import credentials as oauth_credentials
from google.oauth2 import service_account

from paper_review.settings import settings

DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"


def _get_drive_access_token() -> str:
    if settings.google_service_account_file:
        creds = service_account.Credentials.from_service_account_file(
            settings.google_service_account_file, scopes=[DRIVE_READONLY_SCOPE]
        )
        creds.refresh(Request())
        if not creds.token:
            raise RuntimeError("Failed to mint Google access token (service account).")
        return creds.token

    if settings.google_client_id and settings.google_client_secret and settings.google_refresh_token:
        creds = oauth_credentials.Credentials(
            token=None,
            refresh_token=settings.google_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            scopes=[DRIVE_READONLY_SCOPE],
        )
        creds.refresh(Request())
        if not creds.token:
            raise RuntimeError("Failed to refresh Google access token (OAuth).")
        return creds.token

    raise RuntimeError(
        "Google Drive credentials not configured. Set GOOGLE_SERVICE_ACCOUNT_FILE or "
        "GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET/GOOGLE_REFRESH_TOKEN."
    )


def download_drive_file(file_id: str, dest_path: Path) -> None:
    token = _get_drive_access_token()
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
    params = {"alt": "media", "supportsAllDrives": "true"}
    headers = {"Authorization": f"Bearer {token}"}

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", url, params=params, headers=headers, timeout=120.0) as r:
        if r.status_code >= 400:
            body = ""
            try:
                body = r.read().decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                body = ""
            message = f"Drive download failed (HTTP {r.status_code}) for file_id={file_id}."
            try:
                j = json.loads(body) if body else None
            except Exception:  # noqa: BLE001
                j = None
            if isinstance(j, dict) and isinstance(j.get("error"), dict):
                err = j["error"]
                reason = ""
                if isinstance(err.get("errors"), list) and err["errors"]:
                    reason = (err["errors"][0] or {}).get("reason") or ""
                detail = err.get("message") or body
                message = f"{message} {detail}"
                if reason in {"accessNotConfigured", "SERVICE_DISABLED"}:
                    message += (
                        " Enable the Google Drive API (drive.googleapis.com) in the Google Cloud project "
                        "that owns your OAuth client, then retry."
                    )
                if "missing a valid api key" in str(detail).lower():
                    message += (
                        " This usually means the request was unauthenticated; ensure your worker loaded "
                        "GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET/GOOGLE_REFRESH_TOKEN (or a service account) "
                        "and that Drive API is enabled for that project."
                    )
            elif body:
                message = f"{message} {body}"
            raise RuntimeError(message)

        with dest_path.open("wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
