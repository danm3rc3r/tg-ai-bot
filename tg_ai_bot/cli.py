"""Command-line interface: --check preflight and the bot entry point (04c section 4.1)."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from .bot import run_bot
from .config import _TOKEN_RE, BotConfig, ConfigError, mask_token

_log = logging.getLogger("tg_ai_bot")


def _parse() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="tg_ai_bot",
        description="Telegram bot that summarizes text and .txt files with a local Ollama LLM.",
    )
    parser.add_argument(
        "--check", action="store_true", help="Run preflight checks and exit (no polling)."
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    return parser.parse_args()


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )


def _preflight() -> int:
    """Stage S1 preflight: BOT_TOKEN presence and shape (exit 0 | 2).

    The Ollama and model sections join at stage S2 (exit 0 | 1 | 2).
    """
    token = (os.environ.get("BOT_TOKEN") or "").strip()
    if not token:
        print("[token] BOT_TOKEN: missing (set BOT_TOKEN in .env)", file=sys.stderr)
        return 2
    if _TOKEN_RE.fullmatch(token) is None:
        print("[token] BOT_TOKEN: looks like a placeholder (expected <id>:<secret>)",
              file=sys.stderr)
        return 2
    print(f"[token] ok ({mask_token(token)} )", file=sys.stderr)
    return 0


def main() -> None:
    args = _parse()
    _setup_logging(args.verbose)
    if args.check:
        raise SystemExit(_preflight())  # 0 | 1 | 2, report to stderr
    try:
        cfg = BotConfig.from_env()
    except ConfigError as exc:
        _log.error("config error: %s", exc)
        raise SystemExit(2)
    asyncio.run(run_bot(cfg))
