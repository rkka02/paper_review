from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _parse_torch_dtype(torch: Any, name: str | None) -> Any | None:
    n = (name or "").strip().lower()
    if not n or n == "auto":
        return None
    if n in {"float16", "fp16"}:
        return torch.float16
    if n in {"bfloat16", "bf16"}:
        return torch.bfloat16
    if n in {"float32", "fp32"}:
        return torch.float32
    raise ValueError(f"Unsupported torch dtype: {name!r} (use auto/float16/bfloat16/float32)")


@dataclass(slots=True)
class HuggingFaceLLM:
    """
    Minimal local LLM wrapper using HuggingFace Transformers.

    This keeps dependencies optional; callers should install:
    - torch (CUDA build recommended)
    - transformers
    - accelerate (recommended when using device_map='auto')
    """

    model_name: str
    device_map: str = "auto"
    torch_dtype: str = "auto"
    trust_remote_code: bool = False

    max_new_tokens: int = 256
    temperature: float = 0.2
    top_p: float = 0.95

    _tokenizer: Any = field(init=False, repr=False)
    _model: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(
                "Missing dependencies for local LLM. Install `transformers`, `torch` "
                "(and `accelerate` for device_map='auto')."
            ) from e

        dtype = _parse_torch_dtype(torch, self.torch_dtype)
        tok = AutoTokenizer.from_pretrained(self.model_name, trust_remote_code=self.trust_remote_code)
        if tok.pad_token_id is None and tok.eos_token_id is not None:
            tok.pad_token = tok.eos_token

        model_kwargs: dict[str, Any] = {"trust_remote_code": self.trust_remote_code}
        if dtype is not None:
            model_kwargs["torch_dtype"] = dtype
        if self.device_map:
            model_kwargs["device_map"] = self.device_map

        model = AutoModelForCausalLM.from_pretrained(self.model_name, **model_kwargs)
        model.eval()

        self._tokenizer = tok
        self._model = model

    def generate(self, *, system: str, user: str) -> str:
        system = (system or "").strip()
        user = (user or "").strip()
        if not user:
            return ""

        if hasattr(self._tokenizer, "apply_chat_template"):
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": user})
            prompt = self._tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        else:
            prompt = f"{system}\n\nUser:\n{user}\n\nAssistant:\n".strip() + "\n"

        inputs = self._tokenizer(prompt, return_tensors="pt")
        if hasattr(self._model, "device"):
            inputs = {k: v.to(self._model.device) for k, v in inputs.items()}

        do_sample = float(self.temperature) > 0
        gen_kwargs: dict[str, Any] = {
            "max_new_tokens": int(self.max_new_tokens),
            "do_sample": do_sample,
            "pad_token_id": self._tokenizer.pad_token_id,
            "eos_token_id": self._tokenizer.eos_token_id,
        }
        if do_sample:
            gen_kwargs["temperature"] = float(self.temperature)
            gen_kwargs["top_p"] = float(self.top_p)

        out = self._model.generate(**inputs, **gen_kwargs)
        text = self._tokenizer.decode(out[0], skip_special_tokens=True)
        return text
