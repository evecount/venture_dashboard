import unittest
from datetime import datetime, timedelta, timezone

from channel_memory import clean_text, format_context
from dev_controls import DEFAULTS, LogTee, Settings


def ts(minutes_ago: int) -> str:
    return f"{(datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).timestamp():.6f}"


class CleanTextTest(unittest.TestCase):
    def test_slack_markup_becomes_plain_text(self):
        out = clean_text("hi <@U123> see <#C9|launch> and <https://x.co|the doc> &amp; <https://y.co>", {"U123": "Sam"})
        self.assertEqual(out, "hi @Sam see #launch and the doc (https://x.co) & https://y.co")


class FormatContextTest(unittest.TestCase):
    def test_groups_by_channel_oldest_first_with_threads(self):
        root, reply, later = ts(30), ts(20), ts(10)
        msgs = [  # newest first, as the database returns them
            {"channel_id": "C1", "ts": later, "thread_ts": None, "user_name": "Ana", "text": "shipped"},
            {"channel_id": "C1", "ts": reply, "thread_ts": root, "user_name": "Bo", "text": "agreed"},
            {"channel_id": "C1", "ts": root, "thread_ts": root, "user_name": "Ana", "text": "price at $20?"},
            {"channel_id": "C2", "ts": later, "thread_ts": None, "user_name": "Cy", "text": "hello"},
        ]
        out = format_context({"C1": "launch", "C2": "general"}, msgs).splitlines()
        self.assertEqual(out[0], "#launch:")
        self.assertIn("Ana: price at $20?", out[1])
        self.assertTrue(out[2].startswith("  ↳ ") and "Bo: agreed" in out[2])
        self.assertIn("Ana: shipped", out[3])
        self.assertEqual(out[4], "#general:")

    def test_keeps_newest_when_over_budget(self):
        msgs = [{"channel_id": "C1", "ts": ts(i), "thread_ts": None, "user_name": "A", "text": f"m{i} " + "x" * 50}
                for i in range(10)]
        out = format_context({"C1": "c"}, msgs, max_chars=200)
        self.assertIn("m0 ", out)
        self.assertNotIn("m9 ", out)

    def test_empty(self):
        self.assertEqual(format_context({"C1": "c"}, []), "")


class DevControlsTest(unittest.TestCase):
    def test_settings_default_without_database(self):
        self.assertEqual(Settings(None).all(), DEFAULTS)
        self.assertTrue(Settings(None).get("daily_checkin"))

    def test_log_tee_queues_complete_lines(self):
        class Sink:
            def __init__(self):
                self.out = ""

            def write(self, s):
                self.out += s

            def flush(self):
                pass

        sink = Sink()
        tee = LogTee(sink)
        tee.write("[Agent Error] boom\npartial")
        self.assertEqual(tee.drain(), ["[Agent Error] boom"])
        tee.write(" line\n")
        self.assertEqual(tee.drain(), ["partial line"])
        self.assertEqual(sink.out, "[Agent Error] boom\npartial line\n")


if __name__ == "__main__":
    unittest.main()
