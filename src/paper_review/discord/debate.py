from __future__ import annotations

import logging
import random
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session, selectinload

from paper_review.discord.library import paper_context_text
from paper_review.discord.personas import DiscordPersona
from paper_review.discord.webhook import send_discord_webhook
from paper_review.llm import get_llm
from paper_review.llm.providers import LLMOutputParseError
from paper_review.models import DiscordDebateThread, DiscordDebateTurn, Paper
from paper_review.semantic_scholar import search_papers as semantic_scholar_search
from paper_review.settings import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DebateCommand:
    action: str  # start|stop|resume|status|next
    topic: str | None = None


def parse_debate_command(text: str) -> DebateCommand | None:
    raw = (text or "").strip()
    if not raw:
        return None

    lowered = raw.lower()

    def strip_rest(matched_prefix: str) -> str:
        rest = raw[len(matched_prefix) :].strip()
        rest = rest.lstrip(":：-–— ").strip()
        return rest

    # Korean (allow optional spaces: "토론시작", "토론 시작", etc.)
    m = re.match(r"^토론\s*시작\b", raw)
    if m:
        topic = strip_rest(m.group(0))
        return DebateCommand(action="start", topic=topic or None)
    if re.match(r"^토론\s*(종료|끝|중단)\b", raw):
        return DebateCommand(action="stop")
    if re.match(r"^토론\s*(재개|이어|계속)\b", raw):
        return DebateCommand(action="resume")
    if re.match(r"^토론\s*상태\b", raw):
        return DebateCommand(action="status")
    if re.match(r"^토론\s*(다음|진행)\b", raw):
        return DebateCommand(action="next")

    # English
    m = re.match(r"^(debate|discussion)\s+start\b", lowered)
    if m:
        topic = strip_rest(raw[: m.end()])
        return DebateCommand(action="start", topic=topic or None)
    if re.match(r"^(debate|discussion)\s+(stop|end)\b", lowered):
        return DebateCommand(action="stop")
    if re.match(r"^(debate|discussion)\s+resume\b", lowered):
        return DebateCommand(action="resume")
    if re.match(r"^(debate|discussion)\s+status\b", lowered):
        return DebateCommand(action="status")
    if re.match(r"^(debate|discussion)\s+next\b", lowered):
        return DebateCommand(action="next")

    return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clamp_int(v: int, lo: int, hi: int) -> int:
    return max(lo, min(int(v), hi))


def _next_turn_at(now: datetime) -> datetime:
    lo = _clamp_int(settings.discord_debate_min_interval_seconds, 5, 24 * 3600)
    hi = _clamp_int(settings.discord_debate_max_interval_seconds, 5, 24 * 3600)
    if hi < lo:
        lo, hi = hi, lo
    return now + timedelta(seconds=random.randint(lo, hi))


def _duo_other(key: str) -> str:
    return "rei" if key == "hikari" else "hikari"


def _debate_turn_schema() -> dict:
    return {
        "name": "discord_debate_turn",
        "schema": {
            "type": "object",
            "properties": {"reply": {"type": "string"}},
            "required": ["reply"],
            "additionalProperties": False,
        },
        "strict": True,
    }


def _debate_turn_plan_schema() -> dict:
    return {
        "name": "discord_debate_turn_plan",
        "schema": {
            "type": "object",
            "properties": {
                "semantic_scholar_query": {"type": "string"},
                "reply": {"type": "string"},
            },
            "required": ["semantic_scholar_query", "reply"],
            "additionalProperties": False,
        },
        "strict": True,
    }


_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_HEADING_PREFIX_RE = re.compile(r"^\s*#{1,6}\s+")
_BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-*•]+|\d+[.)]|[a-zA-Z][.)])\s+")
_UUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b")


def _compact_chat_reply(
    text: str,
    *,
    max_lines: int = 10,
    max_total_chars: int = 900,
    max_line_chars: int = 220,
) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""

    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw = _CODE_FENCE_RE.sub("", raw).strip()
    raw = re.sub(r"\n{3,}", "\n\n", raw).strip()

    cleaned: list[str] = []
    for line in raw.split("\n"):
        s = (line or "").strip()
        if not s:
            continue
        s = _HEADING_PREFIX_RE.sub("", s).strip()
        s = _BULLET_PREFIX_RE.sub("", s).strip()
        if s:
            cleaned.append(s)

    if not cleaned:
        return ""

    truncated = False
    if len(cleaned) > max_lines:
        cleaned = cleaned[:max_lines]
        truncated = True

    out_lines: list[str] = []
    for s in cleaned:
        if len(s) > max_line_chars:
            s = s[:max_line_chars].rstrip()
            if not s.endswith("…"):
                s += "…"
            truncated = True
        out_lines.append(s)

    out = "\n".join(out_lines).strip()
    if len(out) > max_total_chars:
        out = out[:max_total_chars].rstrip()
        if not out.endswith("…"):
            out += "…"
        truncated = True

    if truncated and out and not out.endswith("…"):
        out += "…"

    return out


def _extract_paper_ids(text: str, *, limit: int = 5) -> list[uuid.UUID]:
    raw = (text or "").strip()
    if not raw:
        return []
    out: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for m in _UUID_RE.finditer(raw):
        try:
            pid = uuid.UUID(m.group(0))
        except Exception:  # noqa: BLE001
            continue
        if pid in seen:
            continue
        out.append(pid)
        seen.add(pid)
        if len(out) >= max(1, int(limit)):
            break
    return out


def _load_recent_turns(db: Session, thread: DiscordDebateThread, limit: int = 18) -> list[DiscordDebateTurn]:
    started_at = thread.session_started_at
    return (
        db.execute(
            select(DiscordDebateTurn)
            .where(DiscordDebateTurn.thread_id == thread.id)
            .where(DiscordDebateTurn.created_at >= started_at)
            .order_by(desc(DiscordDebateTurn.created_at))
            .limit(max(1, int(limit)))
        )
        .scalars()
        .all()
    )[::-1]


def _turns_text(turns: list[DiscordDebateTurn]) -> str:
    lines: list[str] = []
    for t in turns:
        who = (t.speaker_key or "").strip() or "unknown"
        content = (t.content or "").strip()
        if not content:
            continue
        lines.append(f"[{who}] {content}")
    return "\n".join(lines).strip()


def _relevant_papers_text(db: Session, *, topic: str, history: str, limit: int = 3) -> str:
    limit = max(1, int(limit))

    ids: list[uuid.UUID] = []
    ids.extend(_extract_paper_ids(topic, limit=limit))
    ids.extend([x for x in _extract_paper_ids(history, limit=limit) if x not in set(ids)])

    blocks: list[str] = []
    exclude_ids: list[uuid.UUID] = []

    if ids:
        rows = (
            db.execute(
                select(Paper)
                .options(selectinload(Paper.metadata_row), selectinload(Paper.review))
                .where(Paper.id.in_(ids))
            )
            .scalars()
            .all()
        )
        by_id = {p.id: p for p in rows}
        for pid in ids:
            p = by_id.get(pid)
            if not p:
                continue
            blocks.append(paper_context_text(db, p))
            exclude_ids.append(p.id)
            if len(blocks) >= limit:
                return "\n\n---\n\n".join(blocks).strip()

    q = (topic or "").strip()
    if q:
        if len(q) > 120:
            q = q[:120]
        like = f"%{q}%"
        stmt = (
            select(Paper)
            .options(selectinload(Paper.metadata_row), selectinload(Paper.review))
            .where(
                (Paper.title.ilike(like))
                | (Paper.doi.ilike(like))
                | (Paper.memo.ilike(like))
                | (Paper.abstract.ilike(like))
            )
            .order_by(desc(Paper.updated_at))
            .limit(limit)
        )
        if exclude_ids:
            stmt = stmt.where(~Paper.id.in_(exclude_ids))

        papers = db.execute(stmt).scalars().all()
        for p in papers:
            blocks.append(paper_context_text(db, p))
            if len(blocks) >= limit:
                break

    return "\n\n---\n\n".join(blocks).strip()


def _semantic_scholar_search_text(query: str, limit: int = 3) -> tuple[str, list[str]]:
    q = (query or "").strip()
    if not q:
        return "", []
    try:
        rows = semantic_scholar_search(q, limit=max(1, int(limit)), offset=0)
    except Exception as e:  # noqa: BLE001
        detail = f"{type(e).__name__}: {e}"
        if len(detail) > 260:
            detail = detail[:260].rstrip() + "..."
        return f"(Semantic Scholar error: {detail})", []
    if not rows:
        return "", []

    lines: list[str] = []
    urls: list[str] = []
    for r in rows[: max(1, int(limit))]:
        title = (r.get("title") or "").strip()
        year = r.get("year")
        venue = (r.get("venue") or "").strip()
        url = (r.get("url") or "").strip()
        doi = (r.get("doi") or "").strip()
        head = title or "(untitled)"
        tail_parts: list[str] = []
        if year:
            tail_parts.append(str(year))
        if venue:
            tail_parts.append(venue)
        if doi:
            tail_parts.append(f"doi:{doi}")
        if url:
            tail_parts.append(url)
            urls.append(url)
        tail = " | ".join(tail_parts)
        lines.append(f"- {head}" + (f" ({tail})" if tail else ""))
    return "\n".join(lines).strip(), urls


def _append_semantic_scholar_sources(reply: str, urls: list[str], *, max_urls: int = 2) -> str:
    text = (reply or "").strip()
    if not text:
        return text
    if not urls:
        return text
    if "http://" in text or "https://" in text:
        return text

    uniq: list[str] = []
    seen: set[str] = set()
    for u in urls:
        u = (u or "").strip()
        if not u or u in seen:
            continue
        uniq.append(u)
        seen.add(u)
        if len(uniq) >= max(1, int(max_urls)):
            break

    if not uniq:
        return text
    return text + "\n" + ("참고(S2): " + " ".join(uniq))


def _build_system_prompt(*, persona: DiscordPersona, role: str) -> str:
    prompt = persona.load_prompt()
    base = [
        f"You are '{persona.display_name}', speaking in a Discord thread.",
        "한국어로 답해.",
        "기본 말투는 '친근한 반말'로 해. '합니다/하세요/드립니다' 같은 존댓말은 쓰지 마.",
        "문장 끝을 자연스러운 반말 종결(~해/~했어/~야/~지)로 마무리해.",
        "너무 길게 말하지 말고, '중간 정도' 길이로 써(대략 6~10줄 정도).",
        "실제 사람이 채팅하는 것처럼 자연스럽게 써(목록/소제목/장문 금지).",
        "Hikari and Rei are rivals but also friends. Keep the vibe competitive but friendly (no insults).",
    ]
    if role == "moderator":
        base.append(
            "You are the moderator. Every time you speak, check if the debate drifted away from the topic. "
            "If it drifted: clearly steer it back with a concrete focus question. "
            "If it did not drift: give a short checkpoint summary and tell them to continue."
        )
    return "\n\n".join([x for x in [*base, prompt] if x]).strip()


def _build_user_prompt(
    *,
    topic: str,
    persona_key: str,
    history: str,
    db_context: str,
    semantic_scholar_snippets: str,
    semantic_scholar_tool_available: bool,
    allow_semantic_scholar_query: bool,
) -> str:
    parts: list[str] = []
    parts.append(f"Topic:\n{topic.strip()}\n")
    parts.append(
        "Rules:\n"
        "- Stay on-topic and build on the ongoing debate.\n"
        "- Ground your claims (use DB context / Semantic Scholar snippets when relevant).\n"
        "- Avoid hallucinating missing fields.\n"
        "- Keep your reply medium-length (~6–10 short lines).\n"
    )
    parts.append(
        "Tools:\n"
        "- DB: available (papers).\n"
        f"- Semantic Scholar search: {'available' if semantic_scholar_tool_available else 'disabled'}.\n"
    )
    if allow_semantic_scholar_query:
        if semantic_scholar_tool_available:
            parts.append(
                "Semantic Scholar tool call (only when topic is paper-related):\n"
                "- If you need external paper facts/related work: set semantic_scholar_query to a short keyword query (<= 120 chars).\n"
                "- Otherwise set semantic_scholar_query to \"\".\n"
                "- If semantic_scholar_query is non-empty, set reply to \"\" (we will call you again with tool results).\n"
            )
        else:
            parts.append('Semantic Scholar tool is disabled: set semantic_scholar_query to "".\n')
    elif semantic_scholar_snippets:
        parts.append(
            "Citation:\n"
            "- If you use Semantic Scholar snippets, include at least 1 URL from the snippets in your reply.\n"
        )
    if persona_key in {"hikari", "rei"}:
        parts.append(
            "Goal:\n"
            "- Make 1–2 short concrete points.\n"
            "- Respond to the previous speaker.\n"
            "- End with 1 short question or next step.\n"
        )
    else:
        parts.append(
            "Moderator goal:\n"
            "- Decide if it drifted away from topic.\n"
            "- If drifted: correct course with a focus question.\n"
            "- If not: give a short checkpoint summary and say '계속해'.\n"
        )

    if history:
        parts.append("Thread history:\n" + history)
    if db_context:
        parts.append("\nRelevant papers from our DB:\n" + db_context)
    if semantic_scholar_snippets:
        parts.append("\nSemantic Scholar search snippets:\n" + semantic_scholar_snippets)
    return "\n\n".join([x for x in parts if x]).strip()


def record_human_message(
    db: Session,
    *,
    discord_thread_id: int,
    author_id: int,
    content: str,
) -> bool:
    """
    Records a human message into an active debate thread (if any).
    Returns True if recorded.
    """
    thread = (
        db.execute(
            select(DiscordDebateThread).where(
                (DiscordDebateThread.discord_thread_id == int(discord_thread_id))
                & (DiscordDebateThread.is_active.is_(True))
            )
        )
        .scalars()
        .first()
    )
    if not thread:
        return False

    text = (content or "").strip()
    if not text:
        return False

    db.add(
        DiscordDebateTurn(
            thread_id=thread.id,
            speaker_key=f"user:{author_id}",
            source="human",
            content=text,
        )
    )
    if thread.next_turn_at is None or thread.next_turn_at > _now():
        thread.next_turn_at = _now()
    db.add(thread)
    return True


def start_debate(
    db: Session,
    *,
    discord_thread_id: int,
    discord_channel_id: int,
    discord_guild_id: int | None,
    author_id: int,
    topic: str,
    start_duo_speaker_key: str = "hikari",
) -> DiscordDebateThread:
    now = _now()
    start_duo_speaker_key = start_duo_speaker_key if start_duo_speaker_key in {"hikari", "rei"} else "hikari"

    thread = (
        db.execute(select(DiscordDebateThread).where(DiscordDebateThread.discord_thread_id == int(discord_thread_id)))
        .scalars()
        .first()
    )
    if not thread:
        thread = DiscordDebateThread(
            discord_thread_id=int(discord_thread_id),
            discord_channel_id=int(discord_channel_id),
            discord_guild_id=int(discord_guild_id) if discord_guild_id is not None else None,
            created_by_user_id=int(author_id),
            topic=topic.strip(),
            is_active=True,
            session_started_at=now,
            max_turns=int(settings.discord_debate_max_turns_per_thread),
            next_duo_speaker_key=start_duo_speaker_key,
            next_speaker_key=start_duo_speaker_key,
            duo_turns_since_moderation=0,
            turn_count=0,
            last_turn_at=None,
            next_turn_at=now,
        )
        db.add(thread)
        db.flush()
    else:
        thread.discord_channel_id = int(discord_channel_id)
        thread.discord_guild_id = int(discord_guild_id) if discord_guild_id is not None else None
        thread.topic = topic.strip()
        thread.is_active = True
        thread.session_started_at = now
        thread.max_turns = int(settings.discord_debate_max_turns_per_thread)
        thread.next_duo_speaker_key = start_duo_speaker_key
        thread.next_speaker_key = start_duo_speaker_key
        thread.duo_turns_since_moderation = 0
        thread.turn_count = 0
        thread.last_turn_at = None
        thread.next_turn_at = now
        db.add(thread)

    db.add(
        DiscordDebateTurn(
            thread_id=thread.id,
            speaker_key=f"user:{author_id}",
            source="system",
            content=f"Debate started. Topic: {thread.topic}",
        )
    )
    db.flush()
    db.refresh(thread)
    return thread


def stop_debate(db: Session, *, discord_thread_id: int, author_id: int) -> bool:
    thread = (
        db.execute(select(DiscordDebateThread).where(DiscordDebateThread.discord_thread_id == int(discord_thread_id)))
        .scalars()
        .first()
    )
    if not thread:
        return False
    if not thread.is_active:
        return True
    thread.is_active = False
    thread.next_turn_at = None
    db.add(thread)
    db.add(
        DiscordDebateTurn(
            thread_id=thread.id,
            speaker_key=f"user:{author_id}",
            source="system",
            content="Debate stopped by user.",
        )
    )
    return True


def resume_debate(db: Session, *, discord_thread_id: int, author_id: int) -> bool:
    thread = (
        db.execute(select(DiscordDebateThread).where(DiscordDebateThread.discord_thread_id == int(discord_thread_id)))
        .scalars()
        .first()
    )
    if not thread:
        return False
    thread.is_active = True
    if thread.next_speaker_key not in {"hikari", "rei", "tsugumi"}:
        thread.next_speaker_key = thread.next_duo_speaker_key or "hikari"
    thread.next_turn_at = _now()
    db.add(thread)
    db.add(
        DiscordDebateTurn(
            thread_id=thread.id,
            speaker_key=f"user:{author_id}",
            source="system",
            content="Debate resumed by user.",
        )
    )
    return True


def debate_status_text(db: Session, *, discord_thread_id: int) -> str:
    thread = (
        db.execute(select(DiscordDebateThread).where(DiscordDebateThread.discord_thread_id == int(discord_thread_id)))
        .scalars()
        .first()
    )
    if not thread:
        return "이 스레드에는 저장된 토론 세션이 없어."

    state = "ON" if thread.is_active else "OFF"
    next_at = thread.next_turn_at.isoformat() if thread.next_turn_at else "-"
    return (
        f"토론 상태: {state}\n"
        f"- 주제: {thread.topic}\n"
        f"- 다음 화자: {thread.next_speaker_key}\n"
        f"- 다음 예정: {next_at}\n"
        f"- 턴: {thread.turn_count}/{thread.max_turns} (duo_since_mod={thread.duo_turns_since_moderation})"
    ).strip()


def nudge_debate(db: Session, *, discord_thread_id: int) -> bool:
    thread = (
        db.execute(select(DiscordDebateThread).where(DiscordDebateThread.discord_thread_id == int(discord_thread_id)))
        .scalars()
        .first()
    )
    if not thread or not thread.is_active:
        return False
    thread.next_turn_at = _now()
    db.add(thread)
    return True


def run_due_debate_turn_with_db(
    db: Session,
    *,
    webhook_url: str,
    personas_by_key: dict[str, DiscordPersona],
) -> bool:
    """
    Runs at most one due debate turn. Returns True if a turn was produced.
    """
    now = _now()
    thread = (
        db.execute(
            select(DiscordDebateThread)
            .where(DiscordDebateThread.is_active.is_(True))
            .where(or_(DiscordDebateThread.next_turn_at.is_(None), DiscordDebateThread.next_turn_at <= now))
            .order_by(DiscordDebateThread.next_turn_at.asc().nullsfirst())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if not thread:
        return False

    if thread.turn_count >= thread.max_turns:
        thread.is_active = False
        thread.next_turn_at = None
        db.add(thread)
        try:
            send_discord_webhook(
                url=webhook_url,
                thread_id=int(thread.discord_thread_id),
                content="오늘 토론은 너무 길어져서 여기서 멈출게. 필요하면 `토론 재개`로 이어가자.",
                username=(personas_by_key.get(thread.moderator_key) or next(iter(personas_by_key.values()))).display_name,
                avatar_url=(personas_by_key.get(thread.moderator_key) or next(iter(personas_by_key.values()))).avatar_url,
            )
        except Exception:
            pass
        return False

    speaker_key = (thread.next_speaker_key or "").strip() or (thread.next_duo_speaker_key or "hikari")
    persona = personas_by_key.get(speaker_key)
    if not persona:
        thread.is_active = False
        thread.next_turn_at = None
        db.add(thread)
        return False

    role = "moderator" if speaker_key == thread.moderator_key else "duo"

    try:
        turns = _load_recent_turns(db, thread, limit=18)
        history = _turns_text(turns)
        db_context = _relevant_papers_text(db, topic=thread.topic, history=history, limit=3)
        ss_snips = ""
        ss_urls: list[str] = []

        system = _build_system_prompt(
            persona=persona,
            role=role,
        )

        llm = get_llm(persona.llm_provider)

        plan_user = _build_user_prompt(
            topic=thread.topic,
            persona_key=speaker_key,
            history=history,
            db_context=db_context,
            semantic_scholar_snippets="",
            semantic_scholar_tool_available=settings.discord_debate_semantic_scholar,
            allow_semantic_scholar_query=True,
        )

        plan_payload = llm.generate_json(system=system, user=plan_user, json_schema=_debate_turn_plan_schema())
        ss_query = str((plan_payload or {}).get("semantic_scholar_query") or "").strip()
        reply = str((plan_payload or {}).get("reply") or "").strip()

        if ss_query and settings.discord_debate_semantic_scholar:
            ss_snips, ss_urls = _semantic_scholar_search_text(ss_query, limit=3)
            tool_user = _build_user_prompt(
                topic=thread.topic,
                persona_key=speaker_key,
                history=history,
                db_context=db_context,
                semantic_scholar_snippets=(f"Query: {ss_query}\n{ss_snips}".strip() if ss_snips else f"Query: {ss_query}\n(no results)"),
                semantic_scholar_tool_available=True,
                allow_semantic_scholar_query=False,
            )
            payload = llm.generate_json(system=system, user=tool_user, json_schema=_debate_turn_schema())
            reply = str((payload or {}).get("reply") or "").strip()

        if not reply:
            fallback_user = _build_user_prompt(
                topic=thread.topic,
                persona_key=speaker_key,
                history=history,
                db_context=db_context,
                semantic_scholar_snippets="",
                semantic_scholar_tool_available=settings.discord_debate_semantic_scholar,
                allow_semantic_scholar_query=False,
            )
            payload = llm.generate_json(system=system, user=fallback_user, json_schema=_debate_turn_schema())
            reply = str((payload or {}).get("reply") or "").strip()

        if not reply:
            raise ValueError("Empty LLM output.")
        reply = _append_semantic_scholar_sources(reply, ss_urls)
        reply = _compact_chat_reply(reply) or reply
    except Exception as e:  # noqa: BLE001
        detail = f"{type(e).__name__}: {e}"
        if isinstance(e, LLMOutputParseError):
            detail = f"{type(e).__name__}: {e} (provider={e.provider} model={e.model})"
        if len(detail) > 450:
            detail = detail[:450].rstrip() + "..."

        logger.warning("debate turn failed thread_id=%s speaker=%s err=%s", thread.discord_thread_id, speaker_key, detail)

        thread.next_turn_at = _next_turn_at(now)
        db.add(thread)
        db.add(
            DiscordDebateTurn(
                thread_id=thread.id,
                speaker_key=thread.moderator_key,
                source="system",
                content=f"Turn failed: {detail}",
            )
        )
        try:
            moderator = personas_by_key.get(thread.moderator_key) or persona
            send_discord_webhook(
                url=webhook_url,
                thread_id=int(thread.discord_thread_id),
                content=(
                    "토론 턴 만들다가 에러가 났어. 잠깐만 확인해줘.\n"
                    f"- {detail}\n"
                    "필요하면 `토론 다음`으로 다시 시도할 수 있어."
                ),
                username=moderator.display_name,
                avatar_url=moderator.avatar_url,
            )
        except Exception:
            pass
        return False

    send_discord_webhook(
        url=webhook_url,
        thread_id=int(thread.discord_thread_id),
        content=reply,
        username=persona.display_name,
        avatar_url=persona.avatar_url,
    )

    db.add(
        DiscordDebateTurn(
            thread_id=thread.id,
            speaker_key=speaker_key,
            source="agent",
            content=reply,
        )
    )

    thread.turn_count += 1
    thread.last_turn_at = now

    if speaker_key == thread.moderator_key:
        thread.duo_turns_since_moderation = 0
        thread.next_speaker_key = thread.next_duo_speaker_key or "hikari"
    else:
        thread.duo_turns_since_moderation = int(thread.duo_turns_since_moderation or 0) + 1
        thread.next_duo_speaker_key = _duo_other(speaker_key)
        if thread.duo_turns_since_moderation >= 6:
            thread.next_speaker_key = thread.moderator_key
        else:
            thread.next_speaker_key = thread.next_duo_speaker_key

    thread.next_turn_at = _next_turn_at(now)
    db.add(thread)
    return True
