from __future__ import annotations

import json
import logging
import re
import uuid
from urllib.parse import urlparse

import socket

import typer
from rich import print

from paper_review.db import init_db
from paper_review.settings import settings

app = typer.Typer(add_completion=False, help="paper-review CLI")

_URL_PASSWORD_RE = re.compile(r"((?:postgresql|postgres)(?:\+\w+)?://[^:/@]+:)[^@]+@")
_DSN_PASSWORD_RE = re.compile(r"(password=)(\S+)")
_DICT_PASSWORD_RE = re.compile(r"('password'\s*:\s*)'[^']+'")


def _redact_secrets(text: str) -> str:
    if not text:
        return text
    text = _URL_PASSWORD_RE.sub(r"\1***@", text)
    text = _DSN_PASSWORD_RE.sub(r"\1***", text)
    text = _DICT_PASSWORD_RE.sub(r"\1'***'", text)
    return text


@app.command()
def init() -> None:
    """Create tables in the configured database."""
    try:
        init_db()
    except Exception as e:  # noqa: BLE001
        msg = _redact_secrets(str(e))
        print("[red]DB init failed.[/red]")
        if msg:
            print(f"- {type(e).__name__}: {msg}")

        host = urlparse(settings.database_url).hostname
        if host:
            ipv4_ok = False
            ipv6_ok = False
            try:
                ipv4_ok = bool(socket.getaddrinfo(host, None, socket.AF_INET))
            except Exception:  # noqa: BLE001
                ipv4_ok = False
            try:
                ipv6_ok = bool(socket.getaddrinfo(host, None, socket.AF_INET6))
            except Exception:  # noqa: BLE001
                ipv6_ok = False
            if (not ipv4_ok) and ipv6_ok:
                print(
                    "- DNS returns IPv6-only for this DB host; if your network is IPv4-only, "
                    "use a Supabase Pooler host (IPv4) or a different network."
                )

        print("- Check `DATABASE_URL` and that Postgres is reachable.")
        print("- For Supabase, prefer the Pooler connection string and add `?sslmode=require` if needed.")
        raise typer.Exit(code=1)
    else:
        print("[green]OK[/green] DB initialized.")


@app.command()
def show_config() -> None:
    """Print the current effective configuration (secrets masked)."""
    safe = {
        "DATABASE_URL": _redact_secrets(settings.database_url),
        "OPENAI_MODEL": settings.openai_model,
        "OPENAI_API_KEY": "***" if settings.openai_api_key else None,
        "GOOGLE_CLIENT_ID": "***" if settings.google_client_id else None,
        "GOOGLE_REFRESH_TOKEN": "***" if settings.google_refresh_token else None,
        "GOOGLE_SERVICE_ACCOUNT_FILE": settings.google_service_account_file,
        "API_KEY": "***" if settings.api_key else None,
    }
    print(json.dumps(safe, ensure_ascii=False, indent=2))


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000, reload: bool = True) -> None:
    """Run the API server."""
    import uvicorn

    uvicorn.run("paper_review.api:app", host=host, port=port, reload=reload)


@app.command()
def worker(
    once: bool = typer.Option(False, help="Process at most one job, then exit."),
    log_level: str = typer.Option("INFO", help="Logging level (DEBUG/INFO/WARNING/ERROR)."),
) -> None:
    """Run the analysis worker loop."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    from paper_review.worker import run_worker

    run_worker(once=once)


@app.command()
def analyze(paper_id: str) -> None:
    """Enqueue analysis for a paper id."""
    from paper_review.services import enqueue_analysis_run

    enqueue_analysis_run(uuid.UUID(paper_id))
    print("[green]OK[/green] enqueued.")
