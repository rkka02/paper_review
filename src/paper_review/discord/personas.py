from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from paper_review.settings import settings


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _parse_id_list(raw: str | None) -> set[int]:
    if not raw:
        return set()
    out: set[int] = set()
    for part in str(raw).split(","):
        p = part.strip()
        if not p:
            continue
        try:
            out.add(int(p))
        except Exception:  # noqa: BLE001
            continue
    return out


@dataclass(frozen=True, slots=True)
class DiscordPersona:
    key: str
    display_name: str
    role_id: int
    prompt_path: Path
    llm_provider: str
    avatar_url: str | None = None

    def load_prompt(self) -> str:
        try:
            return self.prompt_path.read_text(encoding="utf-8").strip()
        except Exception:  # noqa: BLE001
            return ""


def load_discord_personas() -> list[DiscordPersona]:
    raw_json = (settings.discord_personas_json or "").strip()
    if raw_json:
        items = json.loads(raw_json)
        if not isinstance(items, list):
            raise ValueError("DISCORD_PERSONAS_JSON must be a JSON list.")

        root = _repo_root()
        out: list[DiscordPersona] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            name = str(item.get("display_name") or "").strip()
            role_id = item.get("role_id")
            prompt_path = str(item.get("prompt_path") or "").strip()
            if not key or not name or not role_id or not prompt_path:
                continue
            provider = str(item.get("llm_provider") or settings.discord_persona_default_llm_provider or "openai").strip()
            avatar_url = str(item.get("avatar_url") or "").strip() or None

            path = Path(prompt_path)
            if not path.is_absolute():
                path = root / path

            out.append(
                DiscordPersona(
                    key=key,
                    display_name=name,
                    role_id=int(role_id),
                    prompt_path=path,
                    llm_provider=provider,
                    avatar_url=avatar_url,
                )
            )
        return out

    root = _repo_root()
    default_provider = (settings.discord_persona_default_llm_provider or "openai").strip()

    out: list[DiscordPersona] = []

    if settings.discord_persona_hikari_role_id:
        out.append(
            DiscordPersona(
                key="hikari",
                display_name="히카리",
                role_id=int(settings.discord_persona_hikari_role_id),
                prompt_path=root / "docs" / "personas" / "hikari.md",
                llm_provider=default_provider,
                avatar_url=(settings.discord_persona_hikari_avatar_url or "").strip() or None,
            )
        )

    if settings.discord_persona_rei_role_id:
        out.append(
            DiscordPersona(
                key="rei",
                display_name="레이",
                role_id=int(settings.discord_persona_rei_role_id),
                prompt_path=root / "docs" / "personas" / "rei.md",
                llm_provider=default_provider,
                avatar_url=(settings.discord_persona_rei_avatar_url or "").strip() or None,
            )
        )

    if settings.discord_persona_tsugumi_role_id:
        out.append(
            DiscordPersona(
                key="tsugumi",
                display_name="츠구미",
                role_id=int(settings.discord_persona_tsugumi_role_id),
                prompt_path=root / "docs" / "personas" / "tsugumi.md",
                llm_provider=default_provider,
                avatar_url=(settings.discord_persona_tsugumi_avatar_url or "").strip() or None,
            )
        )

    return out


def allowed_discord_user_ids() -> set[int]:
    return _parse_id_list(settings.discord_allowed_user_ids)


def allowed_discord_guild_ids() -> set[int]:
    return _parse_id_list(settings.discord_allowed_guild_ids)

