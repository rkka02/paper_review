from __future__ import annotations

import json
import logging
import re
import uuid
from urllib.parse import urlparse
from pathlib import Path

import socket

import typer
from rich import print

from paper_review.db import db_session, init_db
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
        "SERVER_BASE_URL": settings.server_base_url,
        "SERVER_API_KEY": "***" if settings.server_api_key else None,
        "OPENAI_MODEL": settings.openai_model,
        "OPENAI_API_KEY": "***" if settings.openai_api_key else None,
        "GOOGLE_AI_MODEL": settings.google_ai_model,
        "GOOGLE_AI_API_KEY": "***" if settings.google_ai_api_key else None,
        "EMBEDDINGS_PROVIDER": "openai",
        "EMBEDDINGS_NORMALIZE": settings.embeddings_normalize,
        "OPENAI_EMBED_MODEL": settings.openai_embed_model,
        "OPENAI_EMBED_BATCH_SIZE": settings.openai_embed_batch_size,
        "RECOMMENDER_QUERY_LLM_PROVIDER": settings.recommender_query_llm_provider,
        "RECOMMENDER_DECIDER_LLM_PROVIDER": settings.recommender_decider_llm_provider,
        "LOCAL_LLM_MODEL": settings.local_llm_model,
        "OLLAMA_BASE_URL": settings.ollama_base_url,
        "OLLAMA_TIMEOUT_SECONDS": settings.ollama_timeout_seconds,
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
def worker_serve(
    host: str = "0.0.0.0",
    port: int = 8001,
    log_level: str = typer.Option("INFO", help="Logging level (DEBUG/INFO/WARNING/ERROR)."),
) -> None:
    """Run the worker loop with an HTTP /health endpoint (useful on PaaS that requires a port)."""
    import uvicorn

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    uvicorn.run("paper_review.worker_service:app", host=host, port=port, reload=False)


@app.command()
def discord_bot(log_level: str = typer.Option("INFO", help="Logging level (DEBUG/INFO/WARNING/ERROR).")) -> None:
    """Run the Discord bot (role mention -> persona reply via webhook)."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    import asyncio

    from paper_review.discord.bot import run_discord_bot

    asyncio.run(run_discord_bot())


@app.command()
def discord_bot_serve(
    host: str = "0.0.0.0",
    port: int = 8002,
    log_level: str = typer.Option("INFO", help="Logging level (DEBUG/INFO/WARNING/ERROR)."),
) -> None:
    """Run the Discord bot with an HTTP /health endpoint (useful on PaaS that requires a port)."""
    import uvicorn

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    uvicorn.run("paper_review.discord_service:app", host=host, port=port, reload=False)


@app.command()
def analyze(paper_id: str) -> None:
    """Enqueue analysis for a paper id."""
    from paper_review.services import enqueue_analysis_run

    enqueue_analysis_run(uuid.UUID(paper_id))
    print("[green]OK[/green] enqueued.")


@app.command()
def embeddings_reset(
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not prompt; reset immediately."),
) -> None:
    """Delete all stored paper embeddings (use when changing embedding provider/model)."""
    init_db()
    if not yes:
        ok = typer.confirm("This will delete all rows in paper_embeddings. Continue?", default=False)
        if not ok:
            raise typer.Exit(code=1)

    from paper_review.embeddings.store import reset_paper_embeddings

    with db_session() as db:
        removed = reset_paper_embeddings(db)
    print(f"[green]OK[/green] removed {removed} embeddings.")


@app.command()
def embeddings_rebuild(
    provider: str | None = typer.Option(None, help="Embeddings provider (must be 'openai')."),
    limit: int | None = typer.Option(None, help="Only embed the newest N papers (debug)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not prompt; proceed immediately."),
) -> None:
    """(Re)build embeddings for papers in the DB using the configured embedding backend."""
    init_db()
    if not yes:
        ok = typer.confirm(
            "This will write embeddings into paper_embeddings (and may reset them if provider/model changed). Continue?",
            default=False,
        )
        if not ok:
            raise typer.Exit(code=1)

    from paper_review.embeddings import get_embedder
    from paper_review.embeddings.store import rebuild_paper_embeddings

    embedder = get_embedder(provider)
    with db_session() as db:
        result = rebuild_paper_embeddings(db, embedder, limit=limit, reset_if_changed=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))


@app.command()
def recommend(
    server_url: str | None = typer.Option(None, help="Server base URL (default: SERVER_BASE_URL)."),
    api_key: str | None = typer.Option(None, help="Server API key (default: SERVER_API_KEY or API_KEY)."),
    web_username: str | None = typer.Option(None, help="Web login username (session-based auth)."),
    web_password: str | None = typer.Option(None, help="Web login password (session-based auth)."),
    sync_embeddings: bool = typer.Option(True, help="Fill missing paper embeddings on the server before recommending."),
    sync_embeddings_batch: int = typer.Option(64, help="Batch size for embedding upload when syncing."),
    per_folder: int = typer.Option(3, help="Recommendations per folder."),
    cross_domain: int = typer.Option(3, help="Cross-domain recommendations."),
    seeds_per_folder: int = typer.Option(5, help="Random seeds per folder."),
    seed_selector: str = typer.Option("random", help="Seed selection strategy (currently: random)."),
    random_seed: int | None = typer.Option(None, help="Fixed RNG seed (reproducible run)."),
    queries_per_folder: int = typer.Option(3, help="Semantic Scholar queries per folder."),
    search_limit: int = typer.Option(50, help="Semantic Scholar results per query."),
    out: Path | None = typer.Option(None, help="Write the generated payload JSON to this file."),
    dry_run: bool = typer.Option(False, help="Do not upload to the server."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not prompt; proceed immediately."),
) -> None:
    """Generate paper recommendations locally (Semantic Scholar + embeddings + LLM) and upload to server."""
    base_url = (server_url or settings.server_base_url or "").strip()
    if not base_url:
        raise typer.BadParameter("SERVER_BASE_URL is required.")

    key = (api_key or settings.server_api_key or settings.api_key or "").strip() or None

    web_user = (web_username or "").strip() or None
    web_pass = (web_password or "").strip() or None
    if (web_user and not web_pass) or (web_pass and not web_user):
        raise typer.BadParameter("Provide both --web-username and --web-password (or neither).")

    if not key and not web_user and not web_pass:
        host = (urlparse(base_url).hostname or "").lower()
        if host in {"127.0.0.1", "localhost", "0.0.0.0"} and settings.web_username and settings.web_password:
            web_user = settings.web_username
            web_pass = settings.web_password

    if not yes:
        ok = typer.confirm(
            "This will call Semantic Scholar (network) and may call OpenAI (decider). Continue?",
            default=False,
        )
        if not ok:
            raise typer.Exit(code=1)

    from paper_review.recommender import RecommenderConfig, build_recommendations
    from paper_review.recommender.server_client import ServerClient
    from paper_review.embeddings import get_embedder
    from paper_review.schemas import PaperEmbeddingVectorIn, PaperEmbeddingsUpsert

    def paper_text_for_embedding(paper: dict) -> str:
        title = (paper.get("title") or "").strip()
        doi = (paper.get("doi") or "").strip()
        abstract = (paper.get("abstract") or "").strip()
        status = (paper.get("status") or "").strip()
        memo = (paper.get("memo") or "").strip()

        meta = paper.get("metadata_row") if isinstance(paper.get("metadata_row"), dict) else None

        year = paper.get("year")
        if year is None and meta:
            year = meta.get("year")

        venue = (paper.get("venue") or "").strip()
        if not venue and meta:
            venue = (meta.get("venue") or "").strip()

        url = (paper.get("url") or "").strip()
        if not url and meta:
            url = (meta.get("url") or "").strip()

        authors_raw = paper.get("authors")
        if (authors_raw is None or authors_raw == "") and meta:
            authors_raw = meta.get("authors")
        authors: list[str] = []
        if isinstance(authors_raw, list):
            for a in authors_raw:
                if not isinstance(a, dict):
                    continue
                name = (a.get("name") or "").strip()
                if name:
                    authors.append(name)

        review = paper.get("review") if isinstance(paper.get("review"), dict) else None
        review_one_liner = (review.get("one_liner") or "").strip() if review else ""
        review_summary = (review.get("summary") or "").strip() if review else ""
        parts: list[str] = []
        if title:
            parts.append(f"Title: {title}")
        if doi:
            parts.append(f"DOI: {doi}")
        if year:
            parts.append(f"Year: {year}")
        if venue:
            parts.append(f"Venue: {venue}")
        if authors:
            parts.append(f"Authors: {', '.join(authors[:12])}")
        if url:
            parts.append(f"URL: {url}")
        if status:
            parts.append(f"Status: {status}")
        if memo:
            parts.append(f"Memo: {memo}")
        if review_one_liner:
            parts.append(f"Review one-liner: {review_one_liner}")
        if review_summary:
            parts.append(f"Review summary: {review_summary}")
        if abstract:
            parts.append(f"Abstract: {abstract}")
        if not parts:
            pid = str(paper.get("id") or "").strip()
            return f"Paper {pid}" if pid else "Paper"
        return "\n".join(parts)

    embedder = get_embedder()
    embed_provider = getattr(embedder, "provider", "unknown")
    embed_model = getattr(embedder, "model", "unknown")

    try:
        with ServerClient(
            base_url=base_url,
            api_key=key,
            web_username=web_user,
            web_password=web_pass,
            timeout_seconds=60.0,
        ) as client:
            folders = client.fetch_folders()
            paper_summaries = client.fetch_papers_summary()

            if sync_embeddings and not dry_run:
                missing_ids = client.fetch_missing_paper_embeddings(
                    provider=str(embed_provider),
                    model=str(embed_model),
                )
                paper_by_id = {}
                for row in paper_summaries:
                    p = (row or {}).get("paper") if isinstance(row, dict) else None
                    if not isinstance(p, dict):
                        continue
                    pid = str(p.get("id") or "").strip()
                    if pid:
                        paper_by_id[pid] = p
                todo = [pid for pid in missing_ids if pid in paper_by_id]
                if todo:
                    texts = [paper_text_for_embedding(paper_by_id[pid]) for pid in todo]
                    vecs = embedder.embed_passages(texts)
                    if len(vecs) != len(todo):
                        raise RuntimeError("Embedding output count mismatch (sync).")

                    bs = max(1, int(sync_embeddings_batch))
                    upserts_total = 0
                    for i in range(0, len(todo), bs):
                        chunk_ids = todo[i : i + bs]
                        chunk_vecs = vecs[i : i + bs]
                        payload = PaperEmbeddingsUpsert(
                            provider=str(embed_provider),
                            model=str(embed_model),
                            vectors=[
                                PaperEmbeddingVectorIn(paper_id=pid, vector=vec)
                                for pid, vec in zip(chunk_ids, chunk_vecs, strict=True)
                            ],
                        )
                        res = client.upsert_paper_embeddings(payload)
                        upserts_total += int(res.get("upserts") or 0)
                    print(f"[green]OK[/green] synced {upserts_total} paper embeddings ({embed_provider}/{embed_model}).")

            seed_selector_key = (seed_selector or "").strip().lower()
            if seed_selector_key != "random":
                raise typer.BadParameter("Unsupported seed_selector (use: random).")

            from paper_review.recommender.seed import RandomSeedSelector

            payload = build_recommendations(
                folders=folders,
                paper_summaries=paper_summaries,
                config=RecommenderConfig(
                    per_folder=per_folder,
                    cross_domain=cross_domain,
                    seeds_per_folder=seeds_per_folder,
                    random_seed=random_seed,
                    queries_per_folder=queries_per_folder,
                    search_limit=search_limit,
                ),
                seed_selector=RandomSeedSelector(),
                embedder=embedder,
            )

            payload_json = payload.model_dump(mode="json")
            if out is not None:
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps(payload_json, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"[green]OK[/green] wrote {out}.")

            if dry_run:
                print(json.dumps(payload_json, ensure_ascii=False, indent=2))
                return

            result = client.upload_recommendations(payload)
            print(
                json.dumps(
                    {
                        "ok": True,
                        "run_id": str(result.id),
                        "created_at": str(result.created_at),
                        "items": len(result.items),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
    except Exception as e:  # noqa: BLE001
        try:
            import httpx
        except Exception:  # noqa: BLE001
            httpx = None  # type: ignore[assignment]

        if httpx is not None and isinstance(e, httpx.HTTPStatusError):
            code = int(e.response.status_code)
            if code == 404:
                print("[red]Server URL looks incorrect (404 Not Found).[/red]")
                print(f"- Requested: {e.request.method} {e.request.url}")
                print(
                    "- `SERVER_BASE_URL` must point to the running paper-review API server "
                    "(where `/health` returns `{ok:true}`), not your Supabase project URL."
                )
                print("- Example (local): `SERVER_BASE_URL=http://127.0.0.1:8000`")
                raise typer.Exit(code=1)

            if code == 401:
                print("[red]Unauthorized (401).[/red]")
                print(f"- Requested: {e.request.method} {e.request.url}")
                print("- Server auth is enabled. Use one of:")
                print("  - API key: set `API_KEY` on the server and pass `SERVER_API_KEY` (or `--api-key`).")
                print(
                    "  - Web login: run `paper-review recommend --web-username ... --web-password ...` "
                    "(for localhost, the CLI auto-uses `.env` WEB_USERNAME/WEB_PASSWORD if API_KEY is unset)."
                )
                raise typer.Exit(code=1)

        if httpx is not None and isinstance(e, (httpx.ConnectError, httpx.ConnectTimeout)):
            req_url = ""
            try:
                req_url = str(getattr(getattr(e, "request", None), "url", "") or "")
            except Exception:  # noqa: BLE001
                req_url = ""

            req_netloc = (urlparse(req_url).netloc or "").lower() if req_url else ""
            server_netloc = (urlparse(base_url).netloc or "").lower()
            ollama_netloc = (urlparse(settings.ollama_base_url).netloc or "").lower()

            if req_netloc and ollama_netloc and req_netloc == ollama_netloc:
                print("[red]Could not connect to Ollama.[/red]")
                print(f"- OLLAMA_BASE_URL: {settings.ollama_base_url}")
                print("- Start Ollama: `ollama serve` (or launch the Ollama app).")
                print("- Quick check: `curl http://127.0.0.1:11434/api/tags`")
                raise typer.Exit(code=1)

            if req_netloc and server_netloc and req_netloc == server_netloc:
                print("[red]Could not connect to the API server.[/red]")
                print(f"- SERVER_BASE_URL: {base_url}")
                print("- Check that the API server is running and reachable from this machine.")
                print("- Quick check: `curl http://127.0.0.1:8000/health` (or open it in a browser).")
                raise typer.Exit(code=1)

            print("[red]Could not connect to a required service.[/red]")
            if req_url:
                print(f"- URL: {req_url}")
            print(f"- SERVER_BASE_URL: {base_url}")
            print(f"- OLLAMA_BASE_URL: {settings.ollama_base_url}")
            raise typer.Exit(code=1)

        if httpx is not None and isinstance(e, httpx.ReadTimeout):
            req_url = ""
            try:
                req_url = str(getattr(getattr(e, "request", None), "url", "") or "")
            except Exception:  # noqa: BLE001
                req_url = ""

            req_netloc = (urlparse(req_url).netloc or "").lower() if req_url else ""
            server_netloc = (urlparse(base_url).netloc or "").lower()
            ollama_netloc = (urlparse(settings.ollama_base_url).netloc or "").lower()

            if req_netloc and ollama_netloc and req_netloc == ollama_netloc:
                print("[red]Ollama request timed out.[/red]")
                print(f"- OLLAMA_BASE_URL: {settings.ollama_base_url}")
                print("- The model may still be loading; try again after it is warmed up.")
                raise typer.Exit(code=1)

            if req_netloc and server_netloc and req_netloc == server_netloc:
                print("[red]Server request timed out.[/red]")
                print(f"- SERVER_BASE_URL: {base_url}")
                print("- The server may be down or blocked, or the URL/port is incorrect.")
                raise typer.Exit(code=1)

            print("[red]Request timed out.[/red]")
            if req_url:
                print(f"- URL: {req_url}")
            raise typer.Exit(code=1)

        if isinstance(e, RuntimeError) and "COOKIE_HTTPS_ONLY" in str(e):
            print(f"[red]{e}[/red]")
            raise typer.Exit(code=1)
        raise
