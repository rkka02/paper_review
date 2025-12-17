from __future__ import annotations

import json
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

    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object.")
    return data


@dataclass(slots=True)
class OpenAIJsonLLM:
    model: str = field(default_factory=lambda: settings.openai_model)
    provider: str = "openai"

    def generate_json(self, *, system: str, user: str, json_schema: dict[str, Any]) -> dict[str, Any]:
        prompt = "\n\n".join([x for x in [(system or "").strip(), (user or "").strip()] if x])
        resp = create_response(prompt=prompt, file_id=None, json_schema=json_schema)
        return extract_output_json(resp)


@dataclass(slots=True)
class HuggingFaceJsonLLM:
    model: str = field(default_factory=lambda: settings.local_llm_model)
    device_map: str = field(default_factory=lambda: settings.local_llm_device_map)
    torch_dtype: str = field(default_factory=lambda: settings.local_llm_torch_dtype)
    trust_remote_code: bool = field(default_factory=lambda: settings.local_llm_trust_remote_code)
    max_new_tokens: int = field(default_factory=lambda: settings.local_llm_max_new_tokens)
    temperature: float = field(default_factory=lambda: settings.local_llm_temperature)
    top_p: float = field(default_factory=lambda: settings.local_llm_top_p)

    provider: str = "local"
    _impl: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        from paper_review.local_ai.llm import HuggingFaceLLM

        self._impl = HuggingFaceLLM(
            model_name=self.model,
            device_map=self.device_map,
            torch_dtype=self.torch_dtype,
            trust_remote_code=self.trust_remote_code,
            max_new_tokens=self.max_new_tokens,
            temperature=self.temperature,
            top_p=self.top_p,
        )

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
        raw = self._impl.generate(system=system, user=msg)
        return _coerce_json_object(raw)


LocalJsonLLM = HuggingFaceJsonLLM


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
