"""Offline smoke tests (04c section 8, AC-2). Run from the repo root:
python smoke/run_smoke.py. Prints SMOKE OK and exits 0 on success."""
import asyncio
import inspect
import os
import sys
import types
from io import BytesIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tg_ai_bot.bot import Stats
from tg_ai_bot.config import (
    MAX_INPUT_CHARS,
    BotConfig,
    ConfigError,
    mask_proxy,
    mask_token,
)
from tg_ai_bot.handlers import build_router
from tg_ai_bot.limits import RateLimiter
from tg_ai_bot.llm import GenerationResult, OllamaBadOutput, OllamaClient, OllamaError

# ---- config -----------------------------------------------------------------
# Token assembled at runtime: no literal token-shaped string in this file (section 7 gate).
cfg = BotConfig.from_env({"BOT_TOKEN": "123456:" + "f" * 30, "OWNER_ID": "1"})
assert (cfg.ollama_base_url, cfg.ollama_model, cfg.max_per_hour,
        cfg.summary_max_chars, cfg.timeout_s) == \
    ("http://localhost:11434", "llama3:8b", 10, 500, 120.0)
for bad in ({}, {"BOT_TOKEN": "123456:placeholder", "OWNER_ID": "1"},
            {"BOT_TOKEN": "123456:" + "f" * 30, "OWNER_ID": "abc"}):
    try:
        BotConfig.from_env(bad)
        raise AssertionError("ConfigError expected")
    except ConfigError:
        pass
assert mask_token("123456:" + "A" * 35) == "123456:***"
# TELEGRAM_PROXY: absent -> "", set -> stripped value; mask_proxy hides credentials (AC-8)
assert cfg.telegram_proxy == ""
proxy_env = {
    "BOT_TOKEN": "123456:" + "f" * 30,
    "OWNER_ID": "1",
    "TELEGRAM_PROXY": "  http://127.0.0.1:10809  ",
}
assert BotConfig.from_env(proxy_env).telegram_proxy == "http://127.0.0.1:10809"
assert mask_proxy("http://user:pass@proxy:1080") == "http://***@proxy:1080"
assert mask_proxy("http://127.0.0.1:10809") == "http://127.0.0.1:10809"
print("config ok")

# ---- rate limiter -------------------------------------------------------------
rl = RateLimiter(3)
assert [rl.check(1, 1000.0).allowed for _ in range(3)] == [True, True, True]
res = rl.check(1, 1000.0)
assert res.allowed is False and res.retry_seconds > 0
assert rl.check(1, 1000.0 + 3601).allowed  # window expiry
assert list(inspect.signature(RateLimiter.check).parameters) == ["self", "user_id", "now"]
print("rate limiter ok")  # admin bypass lives at the handler level (no admin param)


# ---- fakes ---------------------------------------------------------------------
class FakeMsg:
    def __init__(self, text, uid=42):
        self.text, self.from_user, self.document, self.replies = \
            text, types.SimpleNamespace(id=uid), None, []

    async def answer(self, text):
        self.replies.append(text)


class FakeOllamaClient(OllamaClient):
    def __init__(self, results):
        super().__init__(timeout=1.0)
        self.results = list(results)
        self.prompts = []

    def generate(self, model, prompt, *, response_json=True):
        self.prompts.append(prompt)
        item = self.results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def handler(router, name):
    for h in router.message.handlers:
        if getattr(h.callback, "__name__", "") == name:
            return h.callback
    raise AssertionError("handler not found: " + name)


# ---- LLM reply format ------------------------------------------------------------
llm = FakeOllamaClient([GenerationResult({"summary": "S" * 501}, 1, 1)])
r = build_router(cfg, llm, RateLimiter(10), Stats())
m = FakeMsg("hello world")
asyncio.run(handler(r, "handle_text")(m))
assert m.replies == ["S" * 500 + "\n(from 11 chars)"]
llm2 = FakeOllamaClient([GenerationResult({"summary": "ok"}, 1, 1)])
r2 = build_router(cfg, llm2, RateLimiter(10), Stats())
mb = FakeMsg("x" * (MAX_INPUT_CHARS + 4000))
asyncio.run(handler(r2, "handle_text")(mb))
assert mb.replies == [f"ok\n(from {MAX_INPUT_CHARS + 4000} chars)"]
assert "x" * MAX_INPUT_CHARS in llm2.prompts[0]  # input truncated, original length in reply
m3 = FakeMsg("   ")
asyncio.run(handler(r2, "handle_text")(m3))
assert m3.replies == [] and len(llm2.prompts) == 1  # empty text: no LLM call
print("llm reply format ok")

# ---- document handling --------------------------------------------------------------
class FakeBot:
    def __init__(self, payload):
        self.payload, self.calls = payload, 0

    async def download(self, doc):
        self.calls += 1
        return BytesIO(self.payload)


def doc_case(name, mime, size, payload):
    bot = FakeBot(payload)
    msg = FakeMsg(None)
    msg.document = types.SimpleNamespace(file_name=name, mime_type=mime,
                                         file_size=size, file_id="fid")
    router = build_router(cfg, FakeOllamaClient([GenerationResult({"summary": "ok"}, 1, 1)]),
                          RateLimiter(10), Stats())
    asyncio.run(handler(router, "handle_document")(msg, bot))
    return msg.replies, bot.calls


replies, calls = doc_case("notes.txt", "text/plain", 5, b"hello")
assert replies == ["ok\n(from 5 chars)"] and calls == 1
replies, _ = doc_case("notes.txt", "text/plain", 4, b"\xff\xfe\x00\x01")
assert replies == ["couldn't read this file (UTF-8 txt only)"]
replies, calls = doc_case("big.txt", "text/plain", 2000000, b"x")
assert replies == ["File is too large (max 1 MB)."] and calls == 0
replies, calls = doc_case("doc.pdf", "application/pdf", 10, b"x")
assert replies == ["I can only read .txt documents."] and calls == 0
print("document handling ok")

# ---- OllamaClient.generate (FakeOllamaClient, AC-2 literal) -----------------------------
g = FakeOllamaClient([GenerationResult({"summary": "s"}, 7, 3)]).generate("llama3:8b", "p")
assert (g.output, g.tokens_in, g.tokens_out) == ({"summary": "s"}, 7, 3)
bad = FakeOllamaClient([OllamaBadOutput("x")] * 3)
m4 = FakeMsg("broken")
asyncio.run(handler(build_router(cfg, bad, RateLimiter(10), Stats()), "handle_text")(m4))
assert m4.replies == ["model is busy, try later"] and len(bad.prompts) == 3  # x3 on bad JSON
err = FakeOllamaClient([OllamaError("model 'llama3:8b' not found")])
m5 = FakeMsg("down")
asyncio.run(handler(build_router(cfg, err, RateLimiter(10), Stats()), "handle_text")(m5))
assert m5.replies == ["model is busy, try later"] and len(err.prompts) == 1  # no retry on error
print("ollama client error paths ok")

print("SMOKE OK")
