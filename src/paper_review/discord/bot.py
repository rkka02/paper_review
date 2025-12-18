from __future__ import annotations

import asyncio
import logging
import re

from paper_review.db import db_session, init_db
from paper_review.discord.debate import (
    debate_status_text,
    nudge_debate,
    parse_debate_command,
    record_human_message,
    resume_debate,
    run_due_debate_turn_with_db,
    start_debate,
    stop_debate,
)
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
            "한국어로 답해.",
            "말투는 '친근한 반말'로 해.",
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


def _format_debug_blocks(label: str, raw_text: str) -> list[str]:
    chunks = _split_discord_chunks(raw_text or "", chunk_size=1500)
    total = len(chunks)
    msgs: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        msgs.append(f"{label} ({idx}/{total}):\n```text\n{chunk}\n```")
    return msgs


def _run_due_debate_once_sync(*, webhook_url: str, personas_by_key: dict[str, DiscordPersona]) -> None:
    init_db()
    with db_session() as db:
        run_due_debate_turn_with_db(db, webhook_url=webhook_url, personas_by_key=personas_by_key)


def _record_human_debate_message_sync(*, discord_thread_id: int, author_id: int, content: str) -> None:
    init_db()
    with db_session() as db:
        record_human_message(db, discord_thread_id=discord_thread_id, author_id=author_id, content=content)


def _handle_debate_command_sync(
    *,
    cmd,
    discord_thread_id: int,
    discord_channel_id: int,
    discord_guild_id: int | None,
    author_id: int,
    start_speaker_key: str,
) -> str:
    init_db()
    with db_session() as db:
        action = str(getattr(cmd, "action", "") or "").strip().lower()
        topic = str(getattr(cmd, "topic", "") or "").strip()

        if action == "start":
            if not topic:
                return "주제도 같이 줘. 예) `토론 시작: 요즘 읽는 분야에서 뭐가 핵심 병목이야?`"
            speaker = start_speaker_key if start_speaker_key in {"hikari", "rei"} else "hikari"
            start_debate(
                db,
                discord_thread_id=discord_thread_id,
                discord_channel_id=discord_channel_id,
                discord_guild_id=discord_guild_id,
                author_id=author_id,
                topic=topic,
                start_duo_speaker_key=speaker,
            )
            return (
                "오케이, 이 스레드에서 토론 시작할게.\n"
                f"- 주제: {topic}\n"
                "- 진행: 히카리↔레이 번갈아 말하고, 3턴마다 츠구미가 방향 점검해.\n"
                "- 멈추기: `토론 종료`\n"
                "- 이어가기: `토론 재개`\n"
                "- 상태: `토론 상태`\n"
                "- 다음 턴 바로: `토론 다음`\n"
                "\n"
                "중간에 네가 그냥 메시지로 방향/조건/제약 던져주면 그거 반영해서 계속 이어갈게."
            ).strip()

        if action == "stop":
            ok = stop_debate(db, discord_thread_id=discord_thread_id, author_id=author_id)
            return "오케이, 여기서 멈출게. 다시 이어가려면 `토론 재개` 해줘." if ok else "여긴 아직 토론 세션이 없어."

        if action == "resume":
            ok = resume_debate(db, discord_thread_id=discord_thread_id, author_id=author_id)
            return "오케이, 이어갈게. 다음 턴 곧 올릴게." if ok else "먼저 `토론 시작: ...`로 세션을 만들어줘."

        if action == "status":
            return debate_status_text(db, discord_thread_id=discord_thread_id)

        if action == "next":
            ok = nudge_debate(db, discord_thread_id=discord_thread_id)
            return "오케이, 다음 턴 바로 돌릴게." if ok else "지금은 켜진 토론이 없어. `토론 시작` 또는 `토론 재개`부터 해줘."

        return "지원하지 않는 토론 명령이야."


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
    persona_by_key = {p.key: p for p in personas}
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
    debate_task: asyncio.Task | None = None

    @client.event
    async def on_ready() -> None:
        logging.getLogger(__name__).info("Discord bot logged in as %s", client.user)
        nonlocal debate_task
        if not settings.discord_debate_enabled:
            return
        if debate_task is not None:
            return

        poll = max(3, int(settings.discord_debate_poll_seconds))

        async def debate_loop() -> None:
            while not client.is_closed():
                await asyncio.sleep(poll)
                if lock.locked():
                    continue
                async with lock:
                    try:
                        await asyncio.to_thread(
                            _run_due_debate_once_sync,
                            webhook_url=webhook_url,
                            personas_by_key=persona_by_key,
                        )
                    except Exception as e:  # noqa: BLE001
                        logging.getLogger(__name__).warning("debate loop failed: %s", e)

        debate_task = asyncio.create_task(debate_loop())

    @client.event
    async def on_message(message) -> None:  # type: ignore[no-redef]
        if getattr(message.author, "bot", False):
            return

        guild = getattr(message, "guild", None)
        if allowed_guilds and guild and int(guild.id) not in allowed_guilds:
            return

        if allowed_users and int(message.author.id) not in allowed_users:
            return

        author_id = int(message.author.id)

        thread_id: int | None = None
        channel_id: int | None = None
        guild_id: int | None = None
        try:
            channel_id = int(getattr(message.channel, "id", 0) or 0) or None
            guild_id = int(getattr(guild, "id", 0) or 0) or None
            if isinstance(getattr(message, "channel", None), discord.Thread):  # type: ignore[attr-defined]
                thread_id = int(message.channel.id)
                parent_id = getattr(message.channel, "parent_id", None)
                if parent_id:
                    channel_id = int(parent_id)
        except Exception:
            thread_id = None

        role_mentions = getattr(message, "role_mentions", None) or []
        mentioned_role_ids = {int(r.id) for r in role_mentions}
        persona: DiscordPersona | None = None
        for rid in mentioned_role_ids:
            if rid in persona_by_role:
                persona = persona_by_role[rid]
                break

        if persona is None:
            cmd = parse_debate_command(str(getattr(message, "content", "") or ""))
            if cmd is not None and thread_id is not None and channel_id is not None:
                try:
                    out = await asyncio.to_thread(
                        _handle_debate_command_sync,
                        cmd=cmd,
                        discord_thread_id=thread_id,
                        discord_channel_id=channel_id,
                        discord_guild_id=guild_id,
                        author_id=author_id,
                        start_speaker_key="hikari",
                    )
                except Exception as e:  # noqa: BLE001
                    out = f"토론 명령 처리하다가 에러 났어: {type(e).__name__}: {e}"

                moderator = (
                    persona_by_key.get("tsugumi")
                    or persona_by_key.get("hikari")
                    or next(iter(persona_by_key.values()))
                )
                try:
                    await asyncio.to_thread(
                        send_discord_webhook,
                        url=webhook_url,
                        thread_id=thread_id,
                        content=out,
                        username=moderator.display_name,
                        avatar_url=moderator.avatar_url,
                    )
                except Exception:
                    pass

                action = str(getattr(cmd, "action", "") or "").strip().lower()
                if settings.discord_debate_enabled and action in {"start", "resume", "next"}:
                    async def _kick() -> None:
                        async with lock:
                            try:
                                await asyncio.to_thread(
                                    _run_due_debate_once_sync,
                                    webhook_url=webhook_url,
                                    personas_by_key=persona_by_key,
                                )
                            except Exception as e:  # noqa: BLE001
                                logging.getLogger(__name__).warning("debate kick failed: %s", e)

                    asyncio.create_task(_kick())
                return

            if thread_id is not None:
                try:
                    await asyncio.to_thread(
                        _record_human_debate_message_sync,
                        discord_thread_id=thread_id,
                        author_id=author_id,
                        content=str(getattr(message, "content", "") or ""),
                    )
                except Exception:
                    pass
            return

        user_text = _strip_role_mentions(str(getattr(message, "content", "") or ""), {persona.role_id})

        cmd = parse_debate_command(user_text)
        if cmd is not None:
            if thread_id is None or channel_id is None:
                try:
                    await asyncio.to_thread(
                        send_discord_webhook,
                        url=webhook_url,
                        content=f"<@{author_id}> 토론은 스레드에서만 할 수 있어. 스레드에서 `토론 시작: ...` 해줘.",
                        username=persona.display_name,
                        avatar_url=persona.avatar_url,
                    )
                except Exception:
                    pass
                return

            try:
                out = await asyncio.to_thread(
                    _handle_debate_command_sync,
                    cmd=cmd,
                    discord_thread_id=thread_id,
                    discord_channel_id=channel_id,
                    discord_guild_id=guild_id,
                    author_id=author_id,
                    start_speaker_key=persona.key,
                )
            except Exception as e:  # noqa: BLE001
                out = f"토론 명령 처리하다가 에러 났어: {type(e).__name__}: {e}"

            moderator = persona_by_key.get("tsugumi") or persona
            try:
                await asyncio.to_thread(
                    send_discord_webhook,
                    url=webhook_url,
                    thread_id=thread_id,
                    content=out,
                    username=moderator.display_name,
                    avatar_url=moderator.avatar_url,
                )
            except Exception:
                pass

            action = str(getattr(cmd, "action", "") or "").strip().lower()
            if settings.discord_debate_enabled and action in {"start", "resume", "next"}:
                async def _kick() -> None:
                    async with lock:
                        try:
                            await asyncio.to_thread(
                                _run_due_debate_once_sync,
                                webhook_url=webhook_url,
                                personas_by_key=persona_by_key,
                            )
                        except Exception as e:  # noqa: BLE001
                            logging.getLogger(__name__).warning("debate kick failed: %s", e)

                asyncio.create_task(_kick())
            return

        if lock.locked():
            try:
                await asyncio.to_thread(
                    send_discord_webhook,
                    url=webhook_url,
                    content=f"<@{author_id}> 지금은 다른 요청을 처리 중이에요. 잠시 후 다시 멘션해주세요.",
                    username=persona.display_name,
                    avatar_url=persona.avatar_url,
                    thread_id=thread_id,
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
                messages.extend(_format_debug_blocks("Gemini raw output", e.raw_output or ""))
                if e.raw_response:
                    messages.append("Gemini raw response payload:")
                    messages.extend(_format_debug_blocks("Gemini raw response", e.raw_response))
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
                        thread_id=thread_id,
                    )
                except Exception as e:  # noqa: BLE001
                    if thread_id is not None:
                        try:
                            await asyncio.to_thread(
                                send_discord_webhook,
                                url=webhook_url,
                                content=msg,
                                username=persona.display_name,
                                avatar_url=persona.avatar_url,
                                thread_id=None,
                            )
                        except Exception as e2:  # noqa: BLE001
                            logging.getLogger(__name__).warning("Discord webhook send failed: %s", e2)
                    else:
                        logging.getLogger(__name__).warning("Discord webhook send failed: %s", e)

    await client.start(token)
