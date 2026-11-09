"""Message router factory: command and message handlers as closures (04c section 4.5).

The signature grows with the stages: S1 (cfg, stats) -> S2 (cfg, llm, stats)
-> S4 final (cfg, llm, limiter, stats).
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from .bot import Stats
from .config import BotConfig


def build_router(cfg: BotConfig, stats: Stats) -> Router:
    """Build the message router; handlers are closures capturing cfg and stats."""
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

    async def handle_fallback(message: Message) -> None:
        await message.answer("I summarize text or .txt files. Send /help.")

    r.message.register(command_start, CommandStart())
    r.message.register(command_help, Command("help"))
    r.message.register(handle_fallback)
    return r
