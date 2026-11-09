# tg-ai-bot - Telegram text summarization bot backed by local Ollama (no cloud API).
FROM python:3.11-slim

WORKDIR /app

# Core dependencies only (requirements.txt is fully pinned).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code.
COPY tg_ai_bot/ ./

# Run as a non-root user.
RUN useradd --create-home appuser
USER appuser

# Secrets are injected at runtime (BOT_TOKEN/OWNER_ID from env); none in the image.
CMD ["python", "-m", "tg_ai_bot"]
