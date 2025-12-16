from __future__ import annotations

import json
from pathlib import Path

import httpx
from google.auth.transport.requests import Request
from google.oauth2 import credentials as oauth_credentials
from google.oauth2 import service_account

from paper_review.settings import settings

_DEFAULT_UPLOAD_MIME = "application/pdf"


def _get_drive_access_token() -> str:
    scope = settings.google_drive_scope.strip() or "https://www.googleapis.com/auth/drive.readonly"
    if settings.google_service_account_file:
        creds = service_account.Credentials.from_service_account_file(
            settings.google_service_account_file, scopes=[scope]
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
            scopes=[scope],
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


def upload_drive_file(
    src_path: Path,
    *,
    filename: str | None = None,
    mime_type: str = _DEFAULT_UPLOAD_MIME,
    parent_folder_id: str | None = None,
) -> str:
    """
    Upload a file to Google Drive (resumable upload) and return the file id.
    Requires GOOGLE_DRIVE_SCOPE with write access (e.g. https://www.googleapis.com/auth/drive).
    """
    token = _get_drive_access_token()
    url = "https://www.googleapis.com/upload/drive/v3/files"
    params = {"uploadType": "resumable", "supportsAllDrives": "true"}
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
        "X-Upload-Content-Type": mime_type,
        "X-Upload-Content-Length": str(src_path.stat().st_size),
    }

    name = filename or src_path.name
    metadata: dict[str, object] = {"name": name}
    if parent_folder_id:
        metadata["parents"] = [parent_folder_id]

    with httpx.Client(timeout=120.0) as client:
        r = client.post(url, params=params, headers=headers, json=metadata)
        if r.status_code >= 400:
            detail = r.text.strip()
            hint = ""
            if r.status_code in {401, 403}:
                hint = (
                    " Ensure GOOGLE_DRIVE_SCOPE allows uploads (recommended: "
                    "https://www.googleapis.com/auth/drive) and that your refresh token/service account "
                    "was authorized with that scope."
                )
            raise RuntimeError(f"Drive upload init failed (HTTP {r.status_code}). {detail}{hint}")

        upload_url = r.headers.get("Location") or r.headers.get("location")
        if not upload_url:
            raise RuntimeError("Drive upload init succeeded but Location header is missing.")

        def _iter_file(path: Path, chunk_size: int = 1024 * 1024):
            with path.open("rb") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk

        put_headers = {"Authorization": f"Bearer {token}", "Content-Type": mime_type}
        put = client.put(upload_url, headers=put_headers, content=_iter_file(src_path))
        if put.status_code >= 400:
            detail = put.text.strip()
            raise RuntimeError(f"Drive upload failed (HTTP {put.status_code}). {detail}")

        data = put.json()
        file_id = data.get("id")
        if not isinstance(file_id, str) or not file_id.strip():
            raise RuntimeError("Drive upload succeeded but response is missing file id.")
        return file_id
