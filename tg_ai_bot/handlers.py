"""Message router factory: command and message handlers as closures (04c section 4.5)."""

from __future__ import annotations

import logging
import time

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from .bot import Stats
from .config import (
    ACCEPTED_DOC_MIME,
    MAX_DOC_BYTES,
    MAX_INPUT_CHARS,
    SUMMARIZE_PROMPT,
    BotConfig,
)
from .limits import RateLimiter
from .llm import GenerationResult, OllamaBadOutput, OllamaClient, OllamaError

_log = logging.getLogger("tg_ai_bot")

BUSY_REPLY = "model is busy, try later"


def build_router(cfg: BotConfig, llm: OllamaClient, limiter: RateLimiter, stats: Stats) -> Router:
    """Build the message router; handlers are closures capturing cfg, llm, limiter, stats."""
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

    async def command_stats(message: Message) -> None:
        if message.from_user is None or message.from_user.id != cfg.owner_id:
            return  # non-admin: silent ignore (not "not allowed")
        await message.answer(stats.report())

    async def _summarize(message: Message, source: str, text: str, size: int | None = None) -> None:
        """admin check -> limiter (non-admin) -> truncate MAX_INPUT_CHARS -> llm.generate
        (retry x2 on OllamaBadOutput) -> summary reply (04c section 3.3) -> stats + log.
        LLM down -> BUSY_REPLY. Logs carry user_id/length/source only (D12)."""
        user_id = message.from_user.id if message.from_user else 0
        if user_id != cfg.owner_id:
            limit = limiter.check(user_id, time.monotonic())
            if not limit.allowed:
                _log.warning("rate-limit user=%d retry=%ds", user_id, limit.retry_seconds)
                await message.answer(
                    f"Limit of {cfg.max_per_hour} summaries per hour reached. "
                    f"Try again in {limit.retry_seconds} s."
                )
                return
        original_len = len(text)
        prompt = SUMMARIZE_PROMPT.replace("{text}", text[:MAX_INPUT_CHARS])
        started = time.monotonic()
        result: GenerationResult | None = None
        reason = ""
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
        stats.ok()
        if source == "doc":
            _log.info("doc user=%d bytes=%d ok=%dms", user_id, size if size is not None else original_len, ms)
        else:
            _log.info("text user=%d len=%d ok=%dms", user_id, original_len, ms)
        await message.answer(f"{summary}\n(from {original_len} chars)")

    async def handle_text(message: Message) -> None:
        text = (message.text or "").strip()
        if not text or text.startswith("/"):  # emptiness / unknown command: no LLM call
            return
        await _summarize(message, source="text", text=text)

    async def handle_document(message: Message, bot: Bot) -> None:
        """Validate a .txt document (mime, extension, size), download, summarize."""
        doc = message.document
        if (
            doc is None
            or doc.mime_type != ACCEPTED_DOC_MIME
            or not (doc.file_name or "").lower().endswith(".txt")
        ):
            await message.answer("I can only read .txt documents.")
            return
        if doc.file_size and doc.file_size > MAX_DOC_BYTES:
            await message.answer("File is too large (max 1 MB).")
            return
        data = await bot.download(doc)  # wrapper: -> io.BytesIO (04c section 4.5)
        raw = data.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            await message.answer("couldn't read this file (UTF-8 txt only)")
            return
        await _summarize(message, source="doc", text=text, size=len(raw))

    async def handle_fallback(message: Message) -> None:
        await message.answer("I summarize text or .txt files. Send /help.")

    r.message.register(command_start, CommandStart())
    r.message.register(command_help, Command("help"))
    r.message.register(command_stats, Command("stats"))  # admin-only inside
    r.message.register(handle_text, F.text)  # the "/..." guard lives inside
    r.message.register(handle_document, F.document)  # txt-only guards inside
    r.message.register(handle_fallback)  # stickers/photos/etc. -> "send /help"
    return r
