from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2 import credentials as oauth_credentials
from google.oauth2 import service_account

from paper_review.settings import settings

_DEFAULT_UPLOAD_MIME = "application/pdf"
_FOLDER_MIME = "application/vnd.google-apps.folder"

_CACHED_UPLOAD_FOLDER_ID: str | None = None


def _escape_drive_query_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _raise_drive_http_error(r: httpx.Response, *, context: str) -> None:
    if r.status_code < 400:
        return
    body = r.text.strip()
    message = f"{context} (HTTP {r.status_code})."
    try:
        j = r.json()
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


def ensure_drive_folder(folder_name: str) -> str:
    """
    Ensure a Drive folder exists and return its file id.

    By default we prefer a folder in the root (My Drive), but if not found we fall back to any match.
    """
    name = (folder_name or "").strip()
    if not name:
        raise ValueError("Drive folder name is empty.")

    token = _get_drive_access_token()
    url = "https://www.googleapis.com/drive/v3/files"
    headers = {"Authorization": f"Bearer {token}"}

    def _find(*, root_only: bool) -> str | None:
        q_parts = [
            f"mimeType='{_FOLDER_MIME}'",
            f"name='{_escape_drive_query_string(name)}'",
            "trashed=false",
        ]
        if root_only:
            q_parts.append("'root' in parents")
        q = " and ".join(q_parts)
        params = {
            "q": q,
            "spaces": "drive",
            "pageSize": "10",
            "fields": "files(id,name)",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        r = client.get(url, params=params, headers=headers)
        _raise_drive_http_error(r, context="Drive folder lookup failed")
        data = r.json() if r.content else {}
        files = data.get("files") if isinstance(data, dict) else None
        if not isinstance(files, list) or not files:
            return None
        fid = (files[0] or {}).get("id")
        return fid if isinstance(fid, str) and fid.strip() else None

    with httpx.Client(timeout=120.0) as client:
        folder_id = _find(root_only=True) or _find(root_only=False)
        if folder_id:
            return folder_id

        payload: dict[str, object] = {"name": name, "mimeType": _FOLDER_MIME, "parents": ["root"]}
        r = client.post(url, params={"supportsAllDrives": "true"}, headers=headers, json=payload)
        _raise_drive_http_error(r, context="Drive folder create failed")
        data = r.json() if r.content else {}
        fid = data.get("id") if isinstance(data, dict) else None
        if not isinstance(fid, str) or not fid.strip():
            raise RuntimeError("Drive folder create failed: missing folder id in response.")
        return fid


def resolve_drive_upload_folder_id() -> str | None:
    """
    Resolve the Drive folder id used for uploads.

    Priority:
    1) GOOGLE_DRIVE_UPLOAD_FOLDER_ID (explicit id)
    2) GOOGLE_DRIVE_UPLOAD_FOLDER_NAME (default: Paper-Review) → find/create
    """
    explicit = (settings.google_drive_upload_folder_id or "").strip() or None
    if explicit:
        return explicit

    global _CACHED_UPLOAD_FOLDER_ID
    if _CACHED_UPLOAD_FOLDER_ID:
        return _CACHED_UPLOAD_FOLDER_ID

    name = (settings.google_drive_upload_folder_name or "").strip()
    if not name:
        return None

    folder_id = ensure_drive_folder(name)
    _CACHED_UPLOAD_FOLDER_ID = folder_id
    return folder_id


def open_drive_file_stream(file_id: str) -> tuple[httpx.Response, Callable[[], None]]:
    """
    Open a streaming HTTP response for a Drive file (alt=media).

    Returns: (httpx.Response, close_fn)
    """
    token = _get_drive_access_token()
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
    params = {"alt": "media", "supportsAllDrives": "true"}
    headers = {"Authorization": f"Bearer {token}"}

    client = httpx.Client(timeout=120.0)
    try:
        req = client.build_request("GET", url, params=params, headers=headers)
        r = client.send(req, stream=True)
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
            try:
                r.close()
            finally:
                client.close()
            raise RuntimeError(message)

        def _close() -> None:
            try:
                r.close()
            finally:
                client.close()

        return r, _close
    except Exception:
        client.close()
        raise


def iter_drive_file_bytes(file_id: str):
    """
    Stream a Drive file's raw bytes (alt=media).

    Used for proxying downloads without buffering the whole file in memory/disk.
    """
    r, close = open_drive_file_stream(file_id)
    try:
        for chunk in r.iter_bytes():
            yield chunk
    finally:
        close()


def _get_drive_access_token() -> str:
    scope = settings.google_drive_scope.strip() or "https://www.googleapis.com/auth/drive.readonly"
    if settings.google_service_account_file:
        creds = service_account.Credentials.from_service_account_file(
            settings.google_service_account_file, scopes=[scope]
        )
        try:
            creds.refresh(Request())
        except RefreshError as e:
            raise RuntimeError(
                f"Failed to mint Google access token (service account): {e}. "
                "Check GOOGLE_SERVICE_ACCOUNT_FILE and GOOGLE_DRIVE_SCOPE."
            ) from e
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
        try:
            creds.refresh(Request())
        except RefreshError as e:
            msg = str(e)
            if "invalid_scope" in msg:
                raise RuntimeError(
                    f"Google token refresh failed: {e}. "
                    "This usually means GOOGLE_DRIVE_SCOPE does not match the scope used to mint "
                    "GOOGLE_REFRESH_TOKEN. Re-issue the refresh token with the same scope "
                    "(recommended for upload+download: https://www.googleapis.com/auth/drive)."
                ) from e
            raise RuntimeError(f"Google token refresh failed: {e}.") from e
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
