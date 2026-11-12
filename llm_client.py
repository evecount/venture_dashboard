"""
A chat client that uses the configured model first (say a locally hosted OpenAI-compatible server) and falls back to
Gemini when that server can't answer: unreachable, timed out, overloaded, or the model is missing.

It looks like the OpenAI client to the rest of the bot (`client.chat.completions.create(**kwargs)`), so nothing else
changes. Problems with the request itself (HTTP 400/422) are NOT retried elsewhere: they are the caller's to handle.
While the first server is failing it is skipped for a minute, so every message doesn't wait for a timeout.
"""

import time
from types import SimpleNamespace

DOWN_FOR = 60  # seconds the primary is skipped after it fails
FALLBACK_ERRORS = {"APIConnectionError", "APITimeoutError", "InternalServerError", "RateLimitError", "NotFoundError",
                   "AuthenticationError", "PermissionDeniedError", "ConnectError", "ReadTimeout", "ConnectTimeout"}


def should_fall_back(error: Exception) -> bool:
    """Connection, timeout, server (5xx), rate-limit, missing-model or key problems, never a bad request (400/422)."""
    status = getattr(error, "status_code", None)
    if isinstance(status, int):
        return status >= 500 or status in (401, 403, 404, 408, 429)
    return type(error).__name__ in FALLBACK_ERRORS or isinstance(error, (ConnectionError, TimeoutError))


class WithFallback:
    def __init__(self, primary, fallback, fast_model: str = "", gemini_model: str = "", gemini_fast_model: str = "", clock=time.monotonic):
        self.primary, self.fallback, self.clock = primary, fallback, clock
        self.fast_model, self.gemini_model, self.gemini_fast_model = fast_model, gemini_model, gemini_fast_model
        self.down_until = 0.0
        self.chat = SimpleNamespace(completions=self)  # `client.chat.completions.create(...)`

    def _gemini_kwargs(self, kw: dict) -> dict:
        fast = bool(self.fast_model) and kw.get("model") == self.fast_model
        return {**kw, "model": (self.gemini_fast_model if fast else self.gemini_model) or kw.get("model")}

    def create(self, **kw):
        if self.fallback is None or self.clock() < self.down_until:
            return (self.fallback or self.primary).chat.completions.create(**self._gemini_kwargs(kw) if self.fallback else kw)
        try:
            return self.primary.chat.completions.create(**kw)
        except Exception as e:  # noqa: BLE001
            if not should_fall_back(e):
                raise
            self.down_until = self.clock() + DOWN_FOR
            print(f"[LLM Fallback] {type(e).__name__}: {str(e)[:160]} -> using Gemini for the next {DOWN_FOR}s")
            return self.fallback.chat.completions.create(**self._gemini_kwargs(kw))
