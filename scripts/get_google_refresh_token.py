from __future__ import annotations

import json
from pathlib import Path

import typer
from google_auth_oauthlib.flow import InstalledAppFlow

app = typer.Typer(add_completion=False)

_SCOPE_PRESETS = {
    "drive.readonly": "https://www.googleapis.com/auth/drive.readonly",
    "drive": "https://www.googleapis.com/auth/drive",
}


@app.command()
def main(
    client_secrets: str,
    port: int = typer.Option(
        8080,
        help="Local redirect port (use a fixed port if you have a Web OAuth client).",
    ),
    host: str = typer.Option("localhost", help="Local redirect host."),
    scope: str = typer.Option(
        "drive",
        help="OAuth scope preset: drive.readonly (download) or drive (upload+download).",
    ),
) -> None:
    """
    Print a Google OAuth refresh token for Drive (personal use).

    1) Create an OAuth Client (Desktop) in Google Cloud Console
    2) Download the JSON and pass its path here
    """
    path = Path(client_secrets)
    raw = json.loads(path.read_text(encoding="utf-8"))
    client_type = "installed" if "installed" in raw else ("web" if "web" in raw else "unknown")

    scope_uri = _SCOPE_PRESETS.get(scope, scope)
    scopes = [scope_uri]

    redirect_uri = f"http://{host}:{port}/"
    print(f"OAuth client type: {client_type}")
    print(f"Redirect URI: {redirect_uri}")
    print(f"Scope: {scope_uri}")
    if client_type == "web":
        print(
            "If you see redirect_uri_mismatch: Google Cloud Console → Credentials → "
            "this OAuth client → Authorized redirect URIs → add the exact URI above."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(path), scopes=scopes)
    creds = flow.run_local_server(
        host=host,
        port=port,
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    print(json.dumps({"refresh_token": creds.refresh_token}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
