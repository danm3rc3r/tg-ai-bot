"""Command-line interface: --check preflight and the bot entry point (04c section 4.1)."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from .bot import run_bot
from .config import (
    _TOKEN_RE,
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_MODEL,
    BotConfig,
    ConfigError,
    mask_token,
)
from .llm import OllamaClient

_log = logging.getLogger("tg_ai_bot")

PREFLIGHT_TIMEOUT_S = 10.0


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
    """Stage S2 preflight: token, Ollama reachability, model presence (exit 0 | 1 | 2).

    2 - token missing/placeholder; 1 - Ollama unreachable or model absent; 0 - all ok.
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

    base_url = (os.environ.get("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_BASE_URL).rstrip("/")
    model = os.environ.get("OLLAMA_MODEL") or DEFAULT_OLLAMA_MODEL
    client = OllamaClient(base_url, timeout=PREFLIGHT_TIMEOUT_S)
    try:
        if not client.is_available():
            print(f"[ollama] not reachable at {base_url} (connection error or timeout)",
                  file=sys.stderr)
            return 1
        print(f"[ollama] reachable at {base_url}", file=sys.stderr)
        if client.model_present(model):
            print(f"[model] present: {model}", file=sys.stderr)
            return 0
        print(f"[model] absent: {model} (run: ollama pull {model})", file=sys.stderr)
        return 1
    finally:
        client.close()


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
