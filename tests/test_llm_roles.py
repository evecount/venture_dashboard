"""Gemini answers first and the local model (over Tailscale) is the fallback; LOCAL_LLM_FIRST=1 swaps them back."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import llm_client  # noqa: E402


class Fake:
    def __init__(self, name, error=None):
        self.name, self.error, self.calls = name, error, []
        self.chat = type("C", (), {"completions": self})()

    def create(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        return f"answer from {self.name}"


def client(gemini_error=None, t=None):
    gem, local = Fake("gemini", gemini_error), Fake("local")
    wf = llm_client.WithFallback(gem, local, primary_model="local-big", primary_fast_model="local-small", fast_model="gemini-fast",
                                 rewrite_fallback=True, **({"clock": t} if t else {}))
    return wf, gem, local


class GeminiFirstTests(unittest.TestCase):
    def test_gemini_answers_with_the_callers_own_model_names_and_the_local_model_is_untouched(self):
        wf, gem, local = client()
        self.assertEqual(wf.chat.completions.create(model="gemini-main", messages=[]), "answer from gemini")
        self.assertEqual(gem.calls[0]["model"], "gemini-main")
        self.assertEqual(local.calls, [])

    def test_when_gemini_fails_the_local_model_answers_with_its_own_names(self):
        wf, gem, local = client(ConnectionError("down"))
        self.assertEqual(wf.chat.completions.create(model="gemini-main", messages=[1], tools=["t"]), "answer from local")
        self.assertEqual((local.calls[0]["model"], local.calls[0]["messages"], local.calls[0]["tools"]), ("local-big", [1], ["t"]))
        wf.chat.completions.create(model="gemini-fast", messages=[])
        self.assertEqual(local.calls[1]["model"], "local-small")  # small talk maps to the local light model
        self.assertEqual(len(gem.calls), 1)  # Gemini is skipped for the next minute instead of waiting on it again

    def test_gemini_is_tried_again_after_a_minute(self):
        t = [0.0]
        wf, gem, local = client(ConnectionError("down"), lambda: t[0])
        wf.chat.completions.create(model="gemini-main", messages=[])
        t[0] = 61
        wf.chat.completions.create(model="gemini-main", messages=[])
        self.assertEqual(len(gem.calls), 2)

    def test_a_bad_request_is_not_sent_to_the_local_model(self):
        class Bad(Exception):
            status_code = 400
        wf, gem, local = client(Bad("bad"))
        with self.assertRaises(Bad):
            wf.chat.completions.create(model="gemini-main", messages=[])
        self.assertEqual(local.calls, [])


if __name__ == "__main__":
    unittest.main()
