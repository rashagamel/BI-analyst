from __future__ import annotations

import contextvars
import re
import threading
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, Iterator, Protocol

if TYPE_CHECKING:
    from .config import Settings


class LLM(Protocol):
    def complete(self, system: str, user: str, *, agent: str) -> str:
        """`agent` names the caller (planner, sql_writer, ...). It lets you route
        different agents to different models later (cheap model for planning,
        strong model for SQL) without touching the agents themselves."""
        ...


# ---------------------------------------------------------------------------
# Per-request usage accounting (calls, tokens, seconds, grouped by agent).
# Uses a ContextVar, not a global, so concurrent requests never mix their numbers.
# ---------------------------------------------------------------------------
class UsageCollector:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._calls: list[tuple[str, int, int, float]] = []

    def add(self, agent: str, input_tokens: int, output_tokens: int, seconds: float) -> None:
        with self._lock:
            self._calls.append((agent, int(input_tokens), int(output_tokens), float(seconds)))

    def summary(self) -> dict:
        by_agent: dict[str, dict] = {}
        with self._lock:
            calls = list(self._calls)
        for agent, i, o, s in calls:
            d = by_agent.setdefault(agent, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "seconds": 0.0})
            d["calls"] += 1
            d["input_tokens"] += i
            d["output_tokens"] += o
            d["seconds"] = round(d["seconds"] + s, 3)
        total = {
            "calls": sum(d["calls"] for d in by_agent.values()),
            "input_tokens": sum(d["input_tokens"] for d in by_agent.values()),
            "output_tokens": sum(d["output_tokens"] for d in by_agent.values()),
            "seconds": round(sum(d["seconds"] for d in by_agent.values()), 3),
        }
        return {"by_agent": by_agent, "total": total}


_current_usage: contextvars.ContextVar[UsageCollector | None] = contextvars.ContextVar("bi_usage", default=None)


@contextmanager
def usage_scope() -> Iterator[UsageCollector]:
    collector = UsageCollector()
    token = _current_usage.set(collector)
    try:
        yield collector
    finally:
        _current_usage.reset(token)


def record_usage(agent: str, input_tokens: int, output_tokens: int, seconds: float) -> None:
    collector = _current_usage.get()
    if collector is not None:
        collector.add(agent, input_tokens, output_tokens, seconds)


class AnthropicLLM:
    def __init__(self, model: str, max_tokens: int = 4096):
        import anthropic

        self._client = anthropic.Anthropic()
        self._model = model
        self._max_tokens = max_tokens

    def complete(self, system: str, user: str, *, agent: str) -> str:
        t0 = time.perf_counter()
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        usage = getattr(msg, "usage", None)
        record_usage(agent, getattr(usage, "input_tokens", 0) or 0,
                     getattr(usage, "output_tokens", 0) or 0, time.perf_counter() - t0)
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


class FakeLLM:
    """Scripted LLM for tests: responses[agent] is consumed in order
    (the last response repeats once the queue is down to one item)."""

    def __init__(self, responses: dict[str, list[str]]):
        self._responses = {k: list(v) for k, v in responses.items()}
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str, *, agent: str) -> str:
        self.calls.append((agent, user))
        record_usage(agent, 0, 0, 0.0)
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
    def __init__(self, model: str, base_url: str, api_key: str, max_tokens: int = 4096):
        from openai import OpenAI

        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    def complete(self, system: str, user: str, *, agent: str) -> str:
        t0 = time.perf_counter()
        r = self._client.chat.completions.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=0,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        usage = getattr(r, "usage", None)
        record_usage(agent, getattr(usage, "prompt_tokens", 0) or 0,
                     getattr(usage, "completion_tokens", 0) or 0, time.perf_counter() - t0)
        return strip_reasoning(r.choices[0].message.content or "")


def make_llm(settings: "Settings") -> LLM:
    provider = settings.provider
    if provider == "anthropic":
        return AnthropicLLM(settings.model, settings.max_tokens)

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
    return OpenAICompatibleLLM(settings.model, base_url, api_key, settings.max_tokens)
