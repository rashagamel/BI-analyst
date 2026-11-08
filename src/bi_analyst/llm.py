from __future__ import annotations

import re
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .config import Settings


class LLM(Protocol):
    def complete(self, system: str, user: str, *, agent: str) -> str:
        """`agent` names the caller (planner, sql_writer, ...). It lets you route
        different agents to different models later (cheap model for planning,
        strong model for SQL) without touching the agents themselves."""
        ...


class AnthropicLLM:
    def __init__(self, model: str, max_tokens: int = 1500):
        import anthropic

        self._client = anthropic.Anthropic()
        self._model = model
        self._max_tokens = max_tokens

    def complete(self, system: str, user: str, *, agent: str) -> str:
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


class FakeLLM:
    """Scripted LLM for tests: responses[agent] is consumed in order
    (the last response repeats once the queue is down to one item)."""

    def __init__(self, responses: dict[str, list[str]]):
        self._responses = {k: list(v) for k, v in responses.items()}
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str, *, agent: str) -> str:
        self.calls.append((agent, user))
        queue = self._responses.get(agent)
        if not queue:
            raise RuntimeError(f"FakeLLM has no scripted response left for agent '{agent}'")
        return queue.pop(0) if len(queue) > 1 else queue[0]


# ---------------------------------------------------------------------------
# Free / alternative providers (anything that speaks the OpenAI chat format)
# ---------------------------------------------------------------------------

# provider -> default base URL. Model names change often: always set BI_MODEL
# to a name shown in your provider's console.
PRESET_BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama": "http://localhost:11434/v1",
}

_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)


def strip_reasoning(text: str) -> str:
    """Some open models emit <think>...</think>; the SQL extractor must not see it."""
    return _THINK.sub("", text).strip()


class OpenAICompatibleLLM:
    def __init__(self, model: str, base_url: str, api_key: str, max_tokens: int = 1500):
        from openai import OpenAI

        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    def complete(self, system: str, user: str, *, agent: str) -> str:
        r = self._client.chat.completions.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=0,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return strip_reasoning(r.choices[0].message.content or "")


def make_llm(settings: "Settings") -> LLM:
    provider = settings.provider
    if provider == "anthropic":
        return AnthropicLLM(settings.model)

    if settings.model.lower().startswith("claude"):
        raise ValueError(
            f"BI_PROVIDER={provider} needs BI_MODEL set to a model name from that provider "
            "(the default 'claude-...' only works with provider 'anthropic')."
        )
    base_url = settings.base_url or PRESET_BASE_URLS.get(provider)
    if not base_url:
        raise ValueError(f"Unknown provider '{provider}'. Use one of: anthropic, "
                         f"{', '.join(PRESET_BASE_URLS)}, or openai_compat with BI_BASE_URL.")
    api_key = settings.api_key or ("ollama" if provider == "ollama" else None)
    if not api_key:
        raise ValueError(f"BI_API_KEY is not set (needed for provider '{provider}').")
    return OpenAICompatibleLLM(settings.model, base_url, api_key)
