from __future__ import annotations

import asyncio
import threading

from fastapi import FastAPI

from paper_review.discord.bot import run_discord_bot

app = FastAPI(title="paper-review-discord-bot", version="0.1.0")


@app.on_event("startup")
def _startup() -> None:
    def runner() -> None:
        asyncio.run(run_discord_bot())

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    app.state.bot_thread = t


@app.get("/health")
def health() -> dict:
    t = getattr(app.state, "bot_thread", None)
    alive = bool(t and getattr(t, "is_alive", lambda: False)())
    return {"ok": True, "bot_alive": alive}

