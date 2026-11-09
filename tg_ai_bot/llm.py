"""Minimal Ollama HTTP client (no SDK). Same interface as llm-batch-pipeline (04c section 4.3)."""

import json
import logging
from dataclasses import dataclass

import httpx

from .config import DEFAULT_OLLAMA_BASE_URL, DEFAULT_TIMEOUT_S

_log = logging.getLogger("tg_ai_bot")


class OllamaError(RuntimeError):
    """Base error for Ollama client failures (transport, HTTP, model missing)."""


class OllamaBadOutput(OllamaError):
    """The model response is not a valid JSON object."""


@dataclass(frozen=True)
class GenerationResult:
    """Parsed model output plus the token counters from the same response."""

    output: dict
    tokens_in: int  # prompt_eval_count (0 when absent)
    tokens_out: int  # eval_count (0 when absent)


class OllamaClient:
    """Minimal Ollama HTTP client (no SDK). One httpx.Client per run."""

    def __init__(
        self,
        base_url: str = DEFAULT_OLLAMA_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._http = httpx.Client(timeout=timeout)

    def is_available(self) -> bool:
        """Return True when GET /api/version answers 200 (no exceptions)."""
        try:
            resp = self._http.get(f"{self._base}/api/version")
        except httpx.HTTPError:
            return False
        return resp.status_code == 200

    def model_present(self, model: str) -> bool:
        """Return True when the model name is listed by GET /api/tags."""
        try:
            resp = self._http.get(f"{self._base}/api/tags")
            resp.raise_for_status()
            body = resp.json()
        except (httpx.HTTPError, ValueError):
            return False
        return model in [m.get("name") for m in body.get("models", [])]

    def generate(self, model: str, prompt: str, *, response_json: bool = True) -> GenerationResult:
        """Call POST /api/generate once and return the parsed output with token counts."""
        payload: dict = {"model": model, "prompt": prompt, "stream": False}
        if response_json:
            payload["format"] = "json"
        try:
            resp = self._http.post(f"{self._base}/api/generate", json=payload)
        except httpx.HTTPError as exc:
            raise OllamaError(f"Ollama request failed: {exc}") from exc
        if resp.status_code == 404:
            raise OllamaError(f"model '{model}' not found; run: ollama pull {model}")
        if resp.status_code >= 500:
            raise OllamaError(f"server error: {resp.status_code}")
        resp.raise_for_status()
        body = resp.json()
        text = body.get("response", "")
        if response_json:
            try:
                output = json.loads(text)
            except json.JSONDecodeError as exc:
                raise OllamaBadOutput(f"model returned invalid JSON: {text[:80]!r}") from exc
            if not isinstance(output, dict) or "summary" not in output:
                raise OllamaBadOutput(f"model returned invalid JSON: {text[:80]!r}")
        else:
            output = {"raw": text}
        return GenerationResult(
            output=output,
            tokens_in=body.get("prompt_eval_count", 0),
            tokens_out=body.get("eval_count", 0),
        )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http.close()
