from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def load_dotenv(path: str = ".env") -> None:
    """Tiny .env loader (no extra dependency). Real environment variables win."""
    f = Path(path)
    if not f.is_file():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv()


@dataclass(frozen=True)
class Settings:
    db_url: str = field(default_factory=lambda: os.getenv("BI_DB_URL", "sqlite:///data/demo.db"))
    # LLM provider: anthropic | groq | gemini | openrouter | ollama | openai_compat
    provider: str = field(default_factory=lambda: os.getenv("BI_PROVIDER", "anthropic").lower())
    model: str = field(default_factory=lambda: os.getenv("BI_MODEL", "claude-sonnet-5-5"))
    base_url: str | None = field(default_factory=lambda: os.getenv("BI_BASE_URL") or None)
    api_key: str | None = field(default_factory=lambda: os.getenv("BI_API_KEY") or None)
    max_attempts: int = 3          # SQL generation attempts (1 initial + corrections)
    max_rows: int = 500            # hard cap on rows pulled back
    query_timeout_s: float = 10.0  # per-query execution timeout
    trace_dir: str = field(default_factory=lambda: os.getenv("BI_TRACE_DIR", "traces"))
    schema_top_k: int = 6          # tables kept by schema linking
