from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from paper_review.openai_http import create_response, extract_output_json
from paper_review.settings import settings


class JsonLLM(Protocol):
    provider: str
    model: str

    def generate_json(self, *, system: str, user: str, json_schema: dict[str, Any]) -> dict[str, Any]: ...


def _coerce_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        raise ValueError("Empty LLM output.")

    if "```" in text:
        lines = []
        in_block = False
        for line in text.splitlines():
            if line.strip().startswith("```"):
                in_block = not in_block
                continue
            if in_block:
                lines.append(line)
        if lines:
            text = "\n".join(lines).strip()

    start_obj = text.find("{")
    end_obj = text.rfind("}")
    if start_obj != -1 and end_obj != -1 and end_obj > start_obj:
        text = text[start_obj : end_obj + 1].strip()

    def escape_control_chars_in_strings(s: str) -> str:
        out: list[str] = []
        in_str = False
        esc = False
        i = 0
        while i < len(s):
            ch = s[i]
            if in_str:
                if esc:
                    out.append(ch)
                    esc = False
                else:
                    if ch == "\\":
                        out.append(ch)
                        esc = True
                    elif ch == '"':
                        out.append(ch)
                        in_str = False
                    elif ch == "\n":
                        out.append("\\n")
                    elif ch == "\r":
                        if i + 1 < len(s) and s[i + 1] == "\n":
                            out.append("\\n")
                            i += 1
                        else:
                            out.append("\\n")
                    elif ch == "\t":
                        out.append("\\t")
                    else:
                        out.append(ch)
            else:
                if ch == '"':
                    out.append(ch)
                    in_str = True
                else:
                    out.append(ch)
            i += 1
        return "".join(out)

    def remove_trailing_commas(s: str) -> str:
        # Best-effort: turn `,}` / `,]` into `}` / `]`
        return re.sub(r",(\s*[}\]])", r"\1", s)

    last_err: Exception | None = None
    for attempt in range(3):
        try:
            candidate = text
            if attempt == 1:
                candidate = escape_control_chars_in_strings(candidate)
            elif attempt == 2:
                candidate = remove_trailing_commas(escape_control_chars_in_strings(candidate))

            data = json.loads(candidate)
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object.")
            return data
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue

    snippet = (text[:400] + "...") if len(text) > 400 else text
    raise ValueError(f"Invalid JSON output: {last_err}. Output snippet:\n{snippet}") from last_err


class LLMOutputParseError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        provider: str,
        model: str,
        raw_output: str,
        raw_response: str | None = None,
    ):
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.raw_output = raw_output
        self.raw_response = raw_response


@dataclass(slots=True)
class OpenAIJsonLLM:
    model: str = field(default_factory=lambda: settings.openai_model)
    provider: str = "openai"

    def generate_json(self, *, system: str, user: str, json_schema: dict[str, Any]) -> dict[str, Any]:
        prompt = "\n\n".join([x for x in [(system or "").strip(), (user or "").strip()] if x])
        resp = create_response(prompt=prompt, file_id=None, json_schema=json_schema)
        return extract_output_json(resp)


@dataclass(slots=True)
class OllamaJsonLLM:
    model: str = field(default_factory=lambda: settings.local_llm_model)
    base_url: str = field(default_factory=lambda: settings.ollama_base_url)
    timeout_seconds: int = field(default_factory=lambda: settings.ollama_timeout_seconds)

    max_new_tokens: int = field(default_factory=lambda: settings.local_llm_max_new_tokens)
    temperature: float = field(default_factory=lambda: settings.local_llm_temperature)
    top_p: float = field(default_factory=lambda: settings.local_llm_top_p)

    provider: str = "ollama"

    def generate_json(self, *, system: str, user: str, json_schema: dict[str, Any]) -> dict[str, Any]:
        schema = (json_schema or {}).get("schema") or {}
        hint = json.dumps(schema, ensure_ascii=False, indent=2)

        system = (system or "").strip()
        user = (user or "").strip()
        msg = (
            f"{user}\n\n"
            "Output format:\n"
            "- Output ONLY a JSON object.\n"
            "- Do not wrap in ```.\n"
            f"- Must follow this JSON Schema:\n{hint}\n"
        )

        base = (self.base_url or "").strip().rstrip("/")
        if not base:
            raise RuntimeError("OLLAMA_BASE_URL is not set.")

        options: dict[str, Any] = {
            "temperature": float(self.temperature),
            "top_p": float(self.top_p),
            "num_predict": int(self.max_new_tokens),
        }

        timeout = httpx.Timeout(
            connect=10.0,
            read=float(self.timeout_seconds),
            write=float(self.timeout_seconds),
            pool=10.0,
        )

        def extract_text(payload: Any) -> Any:
            if not isinstance(payload, dict):
                return None
            if payload.get("error"):
                raise RuntimeError(f"Ollama error: {payload.get('error')}")
            message = payload.get("message")
            if isinstance(message, dict) and message.get("content") is not None:
                return message.get("content")
            if payload.get("response") is not None:
                return payload.get("response")
            return None

        with httpx.Client(timeout=timeout) as client:
            chat_url = base + "/api/chat"
            gen_url = base + "/api/generate"

            messages = [{"role": "system", "content": system}, {"role": "user", "content": msg}] if system else [{"role": "user", "content": msg}]
            prompt = "\n\n".join([x for x in [system, msg] if x])

            last_payload: Any = None
            text: Any = None

            def try_chat(*, json_mode: bool) -> None:
                nonlocal last_payload, text
                body: dict[str, Any] = {
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "options": options,
                }
                if json_mode:
                    body["format"] = "json"
                r = client.post(chat_url, json=body)
                if r.status_code == 404:
                    return
                r.raise_for_status()
                last_payload = r.json()
                text = extract_text(last_payload)

            def try_generate(*, json_mode: bool) -> None:
                nonlocal last_payload, text
                body: dict[str, Any] = {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": options,
                }
                if json_mode:
                    body["format"] = "json"
                r = client.post(gen_url, json=body)
                r.raise_for_status()
                last_payload = r.json()
                text = extract_text(last_payload)

            # Preferred path: chat + JSON mode.
            try_chat(json_mode=True)
            if not str(text or "").strip():
                # Some models behave better with generate endpoint.
                try_generate(json_mode=True)
            if not str(text or "").strip():
                # Fallback: no JSON mode (we still parse JSON from raw text).
                try_chat(json_mode=False)
            if not str(text or "").strip():
                try_generate(json_mode=False)

            if not str(text or "").strip():
                snippet = ""
                try:
                    snippet = json.dumps(last_payload, ensure_ascii=False) if last_payload is not None else ""
                except Exception:  # noqa: BLE001
                    snippet = str(last_payload or "")
                raise RuntimeError(
                    "Ollama returned empty output. "
                    "Try warming up the model (first response can be slow) and ensure the model supports chat/generate."
                    + (f"\nResponse: {snippet[:500]}" if snippet else "")
                )

        if isinstance(text, dict):
            return text
        return _coerce_json_object(str(text or ""))


@dataclass(slots=True)
class GoogleJsonLLM:
    """
    Gemini (Google Generative Language API) JSON helper.

    Uses REST (no extra dependency) and requests JSON output.
    """

    model: str = field(default_factory=lambda: settings.google_ai_model)
    api_key: str | None = field(default_factory=lambda: settings.google_ai_api_key)
    timeout_seconds: int = field(default_factory=lambda: settings.google_ai_timeout_seconds)
    max_output_tokens: int = field(default_factory=lambda: settings.google_ai_max_output_tokens)

    provider: str = "google"

    @staticmethod
    def _sanitize_response_schema(schema: Any) -> Any:
        """
        Google `responseSchema` uses a restricted schema dialect.

        At minimum it does not accept `additionalProperties`, so we strip it recursively.
        """
        if isinstance(schema, dict):
            out: dict[str, Any] = {}
            for k, v in schema.items():
                if k == "additionalProperties":
                    continue
                out[k] = GoogleJsonLLM._sanitize_response_schema(v)
            return out
        if isinstance(schema, list):
            return [GoogleJsonLLM._sanitize_response_schema(x) for x in schema]
        return schema

    def generate_json(self, *, system: str, user: str, json_schema: dict[str, Any]) -> dict[str, Any]:
        key = (self.api_key or "").strip() or (settings.google_ai_api_key or "").strip()
        if not key:
            raise RuntimeError("GOOGLE_AI_API_KEY is not set.")

        system = (system or "").strip()
        user = (user or "").strip()

        schema = (json_schema or {}).get("schema") or {}
        schema_hint = ""
        try:
            schema_hint = json.dumps(schema, ensure_ascii=False, indent=2) if schema else ""
        except Exception:  # noqa: BLE001
            schema_hint = ""

        msg = user
        if schema_hint:
            msg = (
                f"{msg}\n\n"
                "Output format:\n"
                "- Output ONLY a JSON object.\n"
                "- Do not wrap in ```.\n"
                f"- Must follow this JSON Schema:\n{schema_hint}\n"
            )
        else:
            msg = (
                f"{msg}\n\n"
                "Output format:\n"
                "- Output ONLY a JSON object.\n"
                "- Do not wrap in ```.\n"
            )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"

        base_generation_config: dict[str, Any] = {
            "temperature": 0.2,
            "maxOutputTokens": int(self.max_output_tokens),
            "responseMimeType": "application/json",
        }

        gen_with_schema = dict(base_generation_config)
        if isinstance(schema, dict) and schema:
            gen_with_schema["responseSchema"] = self._sanitize_response_schema(schema)

        body_base: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": msg}]}],
        }
        if system:
            body_base["systemInstruction"] = {"parts": [{"text": system}]}

        timeout = httpx.Timeout(
            connect=10.0,
            read=float(self.timeout_seconds),
            write=float(self.timeout_seconds),
            pool=10.0,
        )
        with httpx.Client(timeout=timeout) as client:
            last_exc: Exception | None = None
            payload: Any = None
            for gen in [
                gen_with_schema,
                base_generation_config,  # retry without responseSchema (schema dialect mismatch)
                {
                    "temperature": 0.2,
                    "maxOutputTokens": int(self.max_output_tokens),
                },  # retry without responseMimeType/responseSchema
            ]:
                try:
                    body = dict(body_base)
                    body["generationConfig"] = gen
                    r = client.post(url, params={"key": key}, json=body)
                    r.raise_for_status()
                    payload = r.json()
                    last_exc = None
                    break
                except httpx.HTTPStatusError as e:
                    last_exc = e
                    status = getattr(e.response, "status_code", None)
                    if status not in {400, 404}:
                        raise
                    continue
                except httpx.HTTPError as e:
                    last_exc = e
                    raise

            if last_exc is not None and payload is None:
                raise last_exc

        if isinstance(payload, dict) and payload.get("error"):
            raise RuntimeError(f"Google AI error: {payload.get('error')}")

        text = ""
        if isinstance(payload, dict):
            for cand in payload.get("candidates") or []:
                if not isinstance(cand, dict):
                    continue
                content = cand.get("content")
                if not isinstance(content, dict):
                    continue
                parts = content.get("parts") or []
                if not isinstance(parts, list):
                    continue
                chunk = "".join(
                    str(p.get("text") or "")
                    for p in parts
                    if isinstance(p, dict) and (p.get("text") is not None)
                )
                if chunk.strip():
                    text = chunk
                    break

        if not str(text or "").strip():
            raise ValueError("Empty LLM output.")
        raw = str(text)
        try:
            return _coerce_json_object(raw)
        except Exception as e:  # noqa: BLE001
            hint = ""
            try:
                finish_reason = None
                if isinstance(payload, dict):
                    cands = payload.get("candidates") or []
                    if isinstance(cands, list) and cands and isinstance(cands[0], dict):
                        finish_reason = cands[0].get("finishReason")
                if finish_reason == "MAX_TOKENS":
                    hint = (
                        f" Hint: output may be truncated (finishReason=MAX_TOKENS). "
                        f"Increase GOOGLE_AI_MAX_OUTPUT_TOKENS (currently {self.max_output_tokens})."
                    )
            except Exception:  # noqa: BLE001
                hint = ""
            raw_response = None
            try:
                raw_response = json.dumps(payload, ensure_ascii=False, indent=2)
            except Exception:  # noqa: BLE001
                raw_response = str(payload)
            raise LLMOutputParseError(
                f"Failed to parse JSON output ({type(e).__name__}: {e}).{hint}",
                provider=self.provider,
                model=self.model,
                raw_output=raw,
                raw_response=raw_response,
            ) from e
