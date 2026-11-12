"""
A chat client that uses the local model first (a locally hosted OpenAI-compatible server) and falls back to
the regular (Gemini) client when that server can't answer: unreachable, timed out, overloaded, or the model is missing.

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
    def __init__(self, primary, fallback, primary_model: str, primary_fast_model: str = "", fast_model: str = "", clock=time.monotonic):
        """Callers keep passing the fallback's model names (AI_MODEL / AI_FAST_MODEL); the primary gets its own: `primary_model`,
        or `primary_fast_model` for the calls made with the fallback's fast model (`fast_model`)."""
        self.primary, self.fallback, self.clock = primary, fallback, clock
        self.primary_model, self.primary_fast_model, self.fast_model = primary_model, primary_fast_model, fast_model
        self.down_until = 0.0
        self.chat = SimpleNamespace(completions=self)  # `client.chat.completions.create(...)`

    def _primary_kwargs(self, kw: dict) -> dict:
        fast = bool(self.fast_model) and kw.get("model") == self.fast_model
        return {**kw, "model": (self.primary_fast_model if fast and self.primary_fast_model else self.primary_model)}

    def create(self, **kw):
        if self.fallback is not None and self.clock() < self.down_until:
            return self.fallback.chat.completions.create(**kw)
        try:
            return self.primary.chat.completions.create(**self._primary_kwargs(kw))
        except Exception as e:  # noqa: BLE001
            if self.fallback is None or not should_fall_back(e):
                raise
            self.down_until = self.clock() + DOWN_FOR
            print(f"[LLM Fallback] {type(e).__name__}: {str(e)[:160]} -> using the fallback model for the next {DOWN_FOR}s")
            return self.fallback.chat.completions.create(**kw)
