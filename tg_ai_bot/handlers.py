"""Message router factory: command and message handlers as closures (04c section 4.5).

The signature grows with the stages: S2 (cfg, llm, stats) -> S4 final
(cfg, llm, limiter, stats).
"""

from __future__ import annotations

import logging
import time

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from .bot import Stats
from .config import MAX_INPUT_CHARS, SUMMARIZE_PROMPT, BotConfig
from .llm import GenerationResult, OllamaBadOutput, OllamaClient, OllamaError

_log = logging.getLogger("tg_ai_bot")

BUSY_REPLY = "model is busy, try later"


def build_router(cfg: BotConfig, llm: OllamaClient, stats: Stats) -> Router:
    """Build the message router; handlers are closures capturing cfg, llm and stats."""
    r = Router()

    async def command_start(message: Message) -> None:
        await message.answer(
            "Hi! I summarize text for you.\n"
            "Send me a message or a .txt file and I'll return a short summary.\n"
            "/help - usage, /stats - for the owner."
        )

    async def command_help(message: Message) -> None:
        await message.answer(
            "Send text or a .txt document (<= 1 MB). "
            "I return a summary of up to 500 chars."
        )

    async def _summarize(message: Message, source: str, text: str, size: int | None = None) -> None:
        """Truncate -> llm.generate (3 attempts on bad output) -> summary reply.

        Reply format (04c section 3.3): summary <= cfg.summary_max_chars +
        "(from N chars)", where N is the ORIGINAL input length (pre-truncation).
        Logs carry user_id/length/source only - never message content (D12).
        """
        user_id = message.from_user.id if message.from_user else 0
        original_len = len(text)
        prompt = SUMMARIZE_PROMPT.replace("{text}", text[:MAX_INPUT_CHARS])
        started = time.monotonic()
        result: GenerationResult | None = None
        reason = "unknown"
        for _attempt in range(3):  # initial call + 2 retries on OllamaBadOutput
            try:
                result = llm.generate(cfg.ollama_model, prompt)
                break
            except OllamaBadOutput as exc:
                reason = f"bad-output: {exc}"
            except OllamaError as exc:
                reason = f"{type(exc).__name__}: {exc}"
                break
        if result is None:
            stats.fail()
            _log.warning("summary-fail user=%d reason=%s", user_id, reason)
            await message.answer(BUSY_REPLY)
            return
        ms = int((time.monotonic() - started) * 1000)
        summary = str(result.output["summary"])[: cfg.summary_max_chars]
        await message.answer(f"{summary}\n(from {original_len} chars)")
        stats.ok()
        if source == "doc":
            _log.info("doc user=%d bytes=%d ok=%dms", user_id, size, ms)
        else:
            _log.info("text user=%d len=%d ok=%dms", user_id, original_len, ms)

    async def handle_text(message: Message) -> None:
        text = (message.text or "").strip()
        if not text or text.startswith("/"):  # emptiness / unknown command: no LLM call
            return
        await _summarize(message, source="text", text=text)

    async def handle_fallback(message: Message) -> None:
        await message.answer("I summarize text or .txt files. Send /help.")

    r.message.register(command_start, CommandStart())
    r.message.register(command_help, Command("help"))
    r.message.register(handle_text, F.text)  # the "/..." guard lives inside
    r.message.register(handle_fallback)  # stickers/photos/etc. -> "send /help"
    return r
