# tg-ai-bot

A Telegram bot (aiogram 3.x) that summarizes text you send - or a `.txt` file you
upload - using a **local** LLM (Ollama). No cloud API, no token costs.
Built as a portfolio project.

## Features

- Text message -> short summary
- `.txt` document (<= 1 MB) -> short summary
- Sliding-window rate limit for non-admin users
- Owner-only `/stats`
- In-memory stats and graceful shutdown
- Docker Compose (optional local Ollama sidecar)
- Zero cloud API - everything runs on your machine

## Quickstart (5 min)

```
git clone https://github.com/danm3rc3r/tg-ai-bot.git
cd tg-ai-bot
uv venv .venv && source .venv/bin/activate        # or: python -m venv .venv
pip install -r requirements.txt
cp .env.example .env                               # set BOT_TOKEN (BotFather) + OWNER_ID
ollama serve                                       # terminal 2 (local LLM)
python -m tg_ai_bot                                # terminal 1
```

## Usage

| You | Bot |
|---|---|
| `/start` | short welcome |
| `/help` | usage hints |
| `/stats` | counters (owner only) |
| send text | summary of up to 500 chars + "(from N chars)" |
| send `.txt` (<= 1 MB) | summary of the document |

Example:

```
You: <paste a long article>
tg-ai-bot:
- Main point of the article.
- Second supporting point.
- Consequence / takeaway.
(from 4521 chars)
```

## Configuration

| Variable | Required | Default | Notes |
|---|---|---|---|
| `BOT_TOKEN` | yes | - | Telegram BotFather token; `.env` only, masked in logs |
| `OWNER_ID` | yes | - | your numeric Telegram user id |
| `OLLAMA_BASE_URL` | no | `http://localhost:11434` | |
| `OLLAMA_MODEL` | no | `llama3:8b` | must be pulled locally (`ollama pull`) |
| `MAX_PER_HOUR` | no | `10` | summaries per user per hour (non-admin) |
| `SUMMARY_MAX_CHARS` | no | `500` | |
| `OLLAMA_TIMEOUT_S` | no | `120` | |
| `TELEGRAM_PROXY` | no | - | optional http/socks proxy for Telegram API calls (aiohttp does not use the system proxy); credentials masked in logs |

The token is read from `.env` only and never printed in full (logs show `123456:***`).

## Docker

```
docker compose up --build                             # bot only (Ollama on the host)
docker compose --profile with-ollama up --build       # bot + local Ollama sidecar
```

## Dialog

Screenshots of a real dialog (text → summary, .txt → summary, rate limit) — to be added.

## Limitations

1. Single instance: rate limit and stats are in-memory (reset on restart).
2. `.txt` documents only (no docx/pdf).
3. Long input is truncated to the first 16000 characters.
4. One LLM model at a time (no multi-model).
5. No persistence of user data (by design).
6. Local Ollama required (the bot calls no cloud API).

## License

MIT
