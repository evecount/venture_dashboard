import base64
import os
import sys
import unittest
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import transcribe as t  # noqa: E402


class Resp:
    def __init__(self, data=None, js=None):
        self.content, self._js = data, js

    def json(self):
        return self._js


def gemini_reply(text):
    return Resp(js={"candidates": [{"content": {"parts": [{"text": text}]}}]})


class DetectionTests(unittest.TestCase):
    def test_slack_voice_clips_and_audio_files_are_detected(self):
        self.assertTrue(t.is_audio({"subtype": "slack_audio", "mimetype": "video/mp4"}))
        self.assertTrue(t.is_audio({"mimetype": "audio/mpeg"}))
        self.assertTrue(t.is_audio({"mimetype": "application/octet-stream", "filetype": "m4a"}))
        self.assertFalse(t.is_audio({"mimetype": "application/pdf", "filetype": "pdf"}))
        self.assertFalse(t.is_audio({"mimetype": "video/mp4", "filetype": "mp4"}))  # an ordinary video is not a voice note

    def test_mime_types_are_normalised_for_gemini(self):
        self.assertEqual(t.gemini_mime({"mimetype": "audio/x-m4a"}), "audio/mp4")
        self.assertEqual(t.gemini_mime({"subtype": "slack_audio", "mimetype": "video/mp4"}), "audio/mp4")
        self.assertEqual(t.gemini_mime({"mimetype": "audio/mpeg"}), "audio/mp3")
        self.assertEqual(t.gemini_mime({"mimetype": "audio/webm"}), "audio/webm")


class TranscribeTests(unittest.TestCase):
    def test_request_asks_for_a_faithful_singlish_transcript(self):
        seen = {}

        def http(method, url, headers=None, json=None):
            seen.update(url=url, headers=headers, body=json)
            return gemini_reply("Eh the pricing page can lah, I tested with 3 customers.")

        out = t.transcribe_audio(b"abc", "audio/mp3", "KEY", "gemini-x", http)
        self.assertEqual(out, "Eh the pricing page can lah, I tested with 3 customers.")
        self.assertIn("gemini-x:generateContent", seen["url"])
        self.assertEqual(seen["headers"]["x-goog-api-key"], "KEY")
        parts = seen["body"]["contents"][0]["parts"]
        self.assertIn("Singlish", parts[0]["text"])
        self.assertEqual(base64.b64decode(parts[1]["inline_data"]["data"]), b"abc")

    def test_known_names_are_passed_as_spelling_hints(self):
        seen = {}

        def http(method, url, headers=None, json=None):
            seen["prompt"] = json["contents"][0]["parts"][0]["text"]
            return gemini_reply("ok")

        t.transcribe_audio(b"x", "audio/wav", "K", "m", http, hints=["Auvira", "SharedOut", "Auvira"])
        self.assertIn("Auvira, SharedOut.", seen["prompt"])

    def test_no_speech_becomes_empty(self):
        self.assertEqual(t.transcribe_audio(b"x", "audio/wav", "K", "m", lambda *a, **k: gemini_reply("[no speech]")), "")

    def test_mp4_audio_retries_with_a_generic_type(self):
        calls = []

        def http(method, url, headers=None, json=None):
            m = json["contents"][0]["parts"][1]["inline_data"]["mime_type"]
            calls.append(m)
            if m == "audio/mp4":
                raise RuntimeError("unsupported")
            return gemini_reply("hello")

        self.assertEqual(t.transcribe_audio(b"x", "audio/mp4", "K", "m", http), "hello")
        self.assertEqual(calls, ["audio/mp4", "audio/aac"])

    def test_failure_raises_so_the_bot_can_apologise(self):
        def http(*a, **k):
            raise RuntimeError("boom")
        with self.assertRaises(RuntimeError):
            t.transcribe_audio(b"x", "audio/wav", "K", "m", http)


class DownloadTests(unittest.TestCase):
    def test_uses_the_bot_token_and_refuses_huge_files(self):
        seen = {}

        def http(method, url, headers=None):
            seen.update(url=url, auth=headers["Authorization"])
            return Resp(data=b"audio")

        self.assertEqual(t.download({"url_private_download": "https://files.slack.com/x"}, "xoxb-1", http), b"audio")
        self.assertEqual(seen["auth"], "Bearer xoxb-1")
        with self.assertRaises(ValueError):
            t.download({"url_private_download": "u", "size": t.MAX_BYTES + 1}, "xoxb-1", http)


if __name__ == "__main__":
    unittest.main()
