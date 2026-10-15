import os
import sys
import unittest
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import transcribe  # noqa: E402
import voice_compare as vc  # noqa: E402


class FakeTable:
    def __init__(self, fail=False):
        self.rows, self.fail = [], fail

    def table(self, _name):
        return self

    def insert(self, row):
        if self.fail:
            raise RuntimeError("relation voice_comparisons does not exist")
        self.rows.append(row)
        return self

    def execute(self):
        return NS(data=self.rows)


class DedicatedModelTests(unittest.TestCase):
    def test_request_shape_and_reply_parsing(self):
        seen = {}

        def http(method, url, headers=None, json=None):
            seen.update(url=url, body=json)
            return NS(json=lambda: {"steps": [{"type": "model_output", "content": [{"type": "text", "text": " Stuck on pricing lah "}]}]})

        text = transcribe.transcribe_dedicated(b"abc", "audio/mp4", "k", http=http, vocab=["Auvira", "Auvira"])
        self.assertEqual(text, "Stuck on pricing lah")
        self.assertTrue(seen["url"].endswith("/interactions"))
        audio = seen["body"]["input"][0]
        self.assertEqual((audio["type"], audio["mime_type"]), ("audio", "audio/m4a"))
        vocab = seen["body"]["generation_config"]["transcription_config"]["custom_vocabulary"]
        self.assertEqual(vocab.count("Auvira"), 1)
        self.assertIn("lah", vocab)


class CompareTests(unittest.TestCase):
    def test_similarity_ignores_case_and_punctuation(self):
        self.assertEqual(vc.similarity("Stuck on pricing, lah!", "stuck on pricing lah"), 1.0)
        self.assertLess(vc.similarity("stuck on pricing lah", "stuck on pricing law"), 1.0)
        self.assertEqual(vc.word_diff("stuck on pricing lah", "stuck on pricing law"), ["lah → law"])

    def test_records_result_and_survives_candidate_errors(self):
        sb = FakeTable()
        row = vc.compare(sb, b"x", "audio/wav", "hello there", 900, lambda d, m: "hello there", "m")
        self.assertEqual(row["similarity"], 1.0)
        bad = vc.compare(sb, b"x", "audio/wav", "hello", 900, lambda d, m: (_ for _ in ()).throw(RuntimeError("400")), "m")
        self.assertIsNone(bad["similarity"])
        self.assertIn("400", bad["error"])
        self.assertEqual(len(sb.rows), 2)
        self.assertNotIn("slack_user_id", row)  # no link back to the founder

    def test_missing_table_falls_back_to_memory(self):
        vc._memory.clear()
        vc.compare(FakeTable(fail=True), b"x", "audio/wav", "a b", 1, lambda d, m: "a b", "m")
        self.assertEqual(len(vc._memory), 1)

    def test_report(self):
        self.assertIn("No voice notes compared yet", vc.report([]))
        rows = [{"model": "gemini-3.5-transcribe", "similarity": 0.8, "current_ms": 3000, "candidate_ms": 5000,
                 "current_text": "stuck on pricing lah", "candidate_text": "stuck on pricing law"},
                {"model": "gemini-3.5-transcribe", "similarity": 1.0, "current_ms": 1000, "candidate_ms": 1000,
                 "current_text": "ok", "candidate_text": "ok"},
                {"model": "gemini-3.5-transcribe", "similarity": None, "error": "HTTP 400", "current_ms": 1, "candidate_ms": 1}]
        text = vc.report(rows)
        for bit in ("compared: 3", "90% on average", "identical 1/2", "2.0s", "3.0s", "failed on 1: HTTP 400", "lah → law"):
            self.assertIn(bit, text)


if __name__ == "__main__":
    unittest.main()
