from __future__ import annotations

import asyncio
import logging
import re

from paper_review.db import db_session, init_db
from paper_review.discord.library import latest_papers, lookup_paper_for_message, paper_context_text
from paper_review.discord.personas import (
    DiscordPersona,
    allowed_discord_guild_ids,
    allowed_discord_user_ids,
    load_discord_personas,
)
from paper_review.discord.webhook import send_discord_webhook
from paper_review.llm import get_llm
from paper_review.llm.providers import LLMOutputParseError
from paper_review.settings import settings


def _strip_role_mentions(text: str, role_ids: set[int]) -> str:
    out = str(text or "")
    for rid in role_ids:
        out = out.replace(f"<@&{rid}>", "")
    out = re.sub(r"\s+", " ", out).strip()
    return out


def _persona_schema() -> dict:
    return {
        "name": "discord_persona_reply",
        "schema": {
            "type": "object",
            "properties": {"reply": {"type": "string"}},
            "required": ["reply"],
            "additionalProperties": False,
        },
        "strict": True,
    }


def _generate_reply_sync(*, persona: DiscordPersona, user_text: str, author_id: int) -> str:
    init_db()
    with db_session() as db:
        lookup = lookup_paper_for_message(db, user_text)
        if lookup.paper is not None:
            ctx = paper_context_text(db, lookup.paper)
        else:
            ctx = ""

        candidates = lookup.candidates if lookup.paper is None else []
        if not ctx and not candidates:
            recents = latest_papers(db, limit=5)
            lines = []
            for p in recents:
                title = (p.title or "").strip() or "(untitled)"
                doi = (p.doi or "").strip()
                tail = f"doi:{doi}" if doi else f"id:{p.id}"
                lines.append(f"- {title} ({tail})")
            hint = "\n".join(lines)
            return (
                "어떤 논문인지 확인이 필요해요.\n"
                "DOI(예: 10.xxxx/...) 또는 paper id(UUID)를 같이 보내주세요.\n\n"
                "최근 논문(참고):\n"
                f"{hint}"
            ).strip()

        if not ctx and candidates:
            lines = []
            for p in candidates:
                title = (p.title or "").strip() or "(untitled)"
                doi = (p.doi or "").strip()
                tail = f"doi:{doi}" if doi else f"id:{p.id}"
                lines.append(f"- {title} ({tail})")
            hint = "\n".join(lines)
            return (
                "요청이 어떤 논문을 말하는지 애매해요. 아래 중 하나를 DOI/ID로 지정해줘요.\n\n"
                f"{hint}"
            ).strip()

    prompt = persona.load_prompt()
    system = "\n\n".join(
        [
            f"You are '{persona.display_name}', responding in a Discord channel.",
            "Write in Korean.",
            "Be concise (<= 15 lines).",
            prompt,
        ]
    ).strip()

    user = (
        f"Discord author: <@{author_id}>\n\n"
        f"User message:\n{user_text.strip()}\n\n"
        "Paper context (do NOT invent missing fields):\n"
        f"{ctx}\n"
    )

    llm = get_llm(persona.llm_provider)
    payload = llm.generate_json(system=system, user=user, json_schema=_persona_schema())
    reply = str((payload or {}).get("reply") or "").strip()
    if not reply:
        raise ValueError("Empty LLM output.")
    return reply


def _split_discord_chunks(text: str, *, chunk_size: int = 1500) -> list[str]:
    s = str(text or "")
    if not s:
        return [""]
    out: list[str] = []
    i = 0
    while i < len(s):
        out.append(s[i : i + chunk_size])
        i += chunk_size
    return out


async def run_discord_bot() -> None:
    token = (settings.discord_bot_token or "").strip()
    if not token:
        raise RuntimeError("DISCORD_BOT_TOKEN is not set.")

    webhook_url = (settings.discord_webhook_url or "").strip()
    if not webhook_url:
        raise RuntimeError("DISCORD_WEBHOOK_URL is not set (required to send persona replies).")

    allowed_users = allowed_discord_user_ids()
    allowed_guilds = allowed_discord_guild_ids()
    personas = load_discord_personas()
    persona_by_role = {p.role_id: p for p in personas}
    if not persona_by_role:
        raise RuntimeError(
            "No personas configured. Set DISCORD_PERSONAS_JSON or DISCORD_PERSONA_*_ROLE_ID in .env."
        )

    try:
        import discord  # type: ignore
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(
            "Missing dependency: discord.py.\n"
            "Install it in the *same* Python environment you use to run `paper-review`:\n"
            "- `pip install -e .`\n"
            "- or `pip install -r requirements.txt`\n"
            "- or `pip install discord.py`\n"
            "\n"
            "Tip (Windows): activate the venv first: `.venv\\Scripts\\Activate.ps1`."
        ) from e

    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.messages = True

    client = discord.Client(intents=intents)
    lock = asyncio.Lock()

    @client.event
    async def on_ready() -> None:
        logging.getLogger(__name__).info("Discord bot logged in as %s", client.user)

    @client.event
    async def on_message(message) -> None:  # type: ignore[no-redef]
        if getattr(message.author, "bot", False):
            return

        guild = getattr(message, "guild", None)
        if allowed_guilds and guild and int(guild.id) not in allowed_guilds:
            return

        if allowed_users and int(message.author.id) not in allowed_users:
            return

        role_mentions = getattr(message, "role_mentions", None) or []
        mentioned_role_ids = {int(r.id) for r in role_mentions}
        persona: DiscordPersona | None = None
        for rid in mentioned_role_ids:
            if rid in persona_by_role:
                persona = persona_by_role[rid]
                break
        if persona is None:
            return

        user_text = _strip_role_mentions(str(getattr(message, "content", "") or ""), {persona.role_id})
        author_id = int(message.author.id)

        if lock.locked():
            try:
                await asyncio.to_thread(
                    send_discord_webhook,
                    url=webhook_url,
                    content=f"<@{author_id}> 지금은 다른 요청을 처리 중이에요. 잠시 후 다시 멘션해주세요.",
                    username=persona.display_name,
                    avatar_url=persona.avatar_url,
                )
            except Exception:
                pass
            return

        async with lock:
            messages: list[str] = []
            try:
                reply = await asyncio.to_thread(
                    _generate_reply_sync, persona=persona, user_text=user_text, author_id=author_id
                )
                messages = [f"<@{author_id}> {reply}"]
            except LLMOutputParseError as e:
                messages = [
                    f"<@{author_id}> Error: {type(e).__name__}: {e}\n"
                    f"(provider={e.provider} model={e.model})\n"
                    "아래는 디버깅용 원본 출력입니다:",
                ]
                raw = e.raw_output or ""
                chunks = _split_discord_chunks(raw, chunk_size=1500)
                total = len(chunks)
                for idx, chunk in enumerate(chunks, start=1):
                    messages.append(f"Gemini raw output ({idx}/{total}):\n```text\n{chunk}\n```")
            except Exception as e:  # noqa: BLE001
                messages = [f"<@{author_id}> Error: {type(e).__name__}: {e}"]

            for msg in messages:
                try:
                    await asyncio.to_thread(
                        send_discord_webhook,
                        url=webhook_url,
                        content=msg,
                        username=persona.display_name,
                        avatar_url=persona.avatar_url,
                    )
                except Exception as e:  # noqa: BLE001
                    logging.getLogger(__name__).warning("Discord webhook send failed: %s", e)

    await client.start(token)
