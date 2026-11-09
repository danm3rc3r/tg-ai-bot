"""Environment-driven configuration for the Telegram summarization bot."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "llama3:8b"
DEFAULT_MAX_PER_HOUR = 10
DEFAULT_SUMMARY_MAX_CHARS = 500
DEFAULT_TIMEOUT_S = 120.0

# Input cap before summarization (~ llama3:8b context). Documented as a Limitation.
MAX_INPUT_CHARS = 16_000
# Document limits (04 section 3): UTF-8 .txt, <= 1 MB.
MAX_DOC_BYTES = 1_000_000
ACCEPTED_DOC_MIME = "text/plain"
# Sliding-window rate-limit horizon (seconds).
WINDOW_SECONDS = 3600

SUMMARIZE_PROMPT = (
    "Summarize the following text in up to 3 short bullet points. "
    'Return JSON: {"summary": string}\n{text}'
)

_TOKEN_RE = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{30,}$")


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid (exit 2)."""


@dataclass(frozen=True)
class BotConfig:
    bot_token: str
    owner_id: int
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL
    ollama_model: str = DEFAULT_OLLAMA_MODEL
    max_per_hour: int = DEFAULT_MAX_PER_HOUR
    summary_max_chars: int = DEFAULT_SUMMARY_MAX_CHARS
    timeout_s: float = DEFAULT_TIMEOUT_S

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> BotConfig:
        e = os.environ if env is None else env
        token = (e.get("BOT_TOKEN") or "").strip()
        if not token:
            raise ConfigError("BOT_TOKEN is missing (set BOT_TOKEN in .env)")
        if _TOKEN_RE.fullmatch(token) is None:
            raise ConfigError("BOT_TOKEN looks like a placeholder (expected <id>:<secret>)")
        owner_raw = (e.get("OWNER_ID") or "").strip()
        if not owner_raw.isdigit():
            raise ConfigError("OWNER_ID must be a numeric Telegram user id (set in .env)")
        return cls(
            bot_token=token,
            owner_id=int(owner_raw),
            ollama_base_url=(e.get("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_BASE_URL).rstrip("/"),
            ollama_model=(e.get("OLLAMA_MODEL") or DEFAULT_OLLAMA_MODEL),
            max_per_hour=_positive_int(e.get("MAX_PER_HOUR"), DEFAULT_MAX_PER_HOUR),
            summary_max_chars=_positive_int(
                e.get("SUMMARY_MAX_CHARS"), DEFAULT_SUMMARY_MAX_CHARS
            ),
            timeout_s=float(e.get("OLLAMA_TIMEOUT_S") or DEFAULT_TIMEOUT_S),
        )


def _positive_int(raw: str | None, default: int) -> int:
    r = (raw or "").strip()
    if not r:
        return default
    if not r.isdigit() or int(r) <= 0:
        raise ConfigError(f"invalid positive-integer value: {r!r}")
    return int(r)


def mask_token(token: str) -> str:
    """Mask a bot token for logs: keep the numeric id, drop the secret (123456:***)."""
    head, _, _secret = token.partition(":")
    return f"{head}:***"
