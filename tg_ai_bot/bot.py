"""Bot runtime: in-memory stats and the long-polling loop (04c sections 3.4/4.4)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramUnauthorizedError

from .config import BotConfig
from .limits import RateLimiter
from .llm import OllamaClient

_log = logging.getLogger("tg_ai_bot")


@dataclass
class Stats:
    """In-memory run statistics (single instance; not persisted by design)."""

    messages: int = 0
    summaries_ok: int = 0
    summaries_failed: int = 0
    errors: int = 0
    started_at: float = field(default_factory=time.monotonic)

    def ok(self) -> None:
        self.messages += 1
        self.summaries_ok += 1

    def fail(self) -> None:
        self.messages += 1
        self.summaries_failed += 1

    def error(self) -> None:
        self.errors += 1

    def report(self) -> str:
        up = int(time.monotonic() - self.started_at)
        return (
            f"uptime {up // 3600}h {up % 3600 // 60}m | "
            f"messages {self.messages} (ok {self.summaries_ok}, "
            f"failed {self.summaries_failed}) | errors {self.errors}"
        )


async def run_bot(cfg: BotConfig) -> None:
    """Assemble the bot, router and dispatcher, then start long polling."""
    # Imported here (not at module top) because handlers imports Stats from this module.
    from .handlers import build_router

    bot = Bot(token=cfg.bot_token)
    llm = OllamaClient(cfg.ollama_base_url, cfg.timeout_s)
    limiter = RateLimiter(cfg.max_per_hour)
    stats = Stats()
    dp = Dispatcher()
    dp.include_router(build_router(cfg, llm, limiter, stats))
    _log.info(
        "config ok: owner=%d model=%s limit=%d/h base=%s",
        cfg.owner_id,
        cfg.ollama_model,
        cfg.max_per_hour,
        cfg.ollama_base_url,
    )
    try:
        await dp.start_polling(bot)
    except TelegramUnauthorizedError:
        _log.error("bot token rejected by Telegram (check BOT_TOKEN)")
        raise SystemExit(2)
    finally:
        llm.close()
