import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import studio_events as se  # noqa: E402

NOW = datetime(2026, 10, 15, 2, 0, tzinfo=timezone.utc)


def ev(**over):
    base = {
        "id": "e1", "summary": "Pitch practice", "status": "confirmed",
        "start": {"dateTime": "2026-10-15T15:00:00+08:00"}, "end": {"dateTime": "2026-10-15T16:00:00+08:00"},
        "hangoutLink": "https://meet.google.com/abc-defg-hij",
        "attendees": [
            {"email": "studio@example.com", "self": True},
            {"email": "Founder@Example.com", "displayName": "A Founder", "responseStatus": "accepted"},
        ],
    }
    base.update(over)
    return base


class Recorder:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def table(self, name):
        rec = self

        class Q:
            def __getattr__(self, op):
                def call(*a, **k):
                    rec.calls.append((name, op, a))
                    return self
                return call

            def execute(self):
                if rec.fail:
                    raise RuntimeError("relation does not exist")
                return None
        return Q()


class StudioEventsTests(unittest.TestCase):
    def test_rows_keep_what_the_dashboard_needs(self):
        [row] = se.event_rows([ev()], NOW)
        self.assertEqual(row["title"], "Pitch practice")
        self.assertEqual(row["meet_url"], "https://meet.google.com/abc-defg-hij")
        self.assertEqual(row["attendees"], [{"name": "A Founder", "email": "founder@example.com", "response": "accepted"}])

    def test_skips_cancelled_and_all_day_events(self):
        rows = se.event_rows([ev(status="cancelled"), ev(id="e2", start={"date": "2026-10-16"}, end={"date": "2026-10-17"})], NOW)
        self.assertEqual(rows, [])

    def test_not_connected_leaves_the_table_alone(self):
        sb = Recorder()
        self.assertEqual(se.sync(sb, None, NOW), 0)
        self.assertEqual(sb.calls, [])

    def test_sync_replaces_the_upcoming_window(self):
        sb = Recorder()
        self.assertEqual(se.sync(sb, [ev()], NOW), 1)
        ops = [op for _, op, _ in sb.calls if op in ("delete", "upsert")]
        self.assertEqual(ops[:2], ["delete", "upsert"])

    def test_missing_table_is_not_fatal(self):
        self.assertEqual(se.sync(Recorder(fail=True), [ev()], NOW), 0)


class StudioLockTests(unittest.TestCase):
    ROW = {"id": "primary", "account": "studio@example.com", "connected_by": "UCONNECTOR"}

    def test_only_the_developer_can_connect_or_reconnect(self):
        self.assertTrue(se.can_reconnect_studio(self.ROW, "UDEV", True))
        self.assertTrue(se.can_reconnect_studio(None, "UDEV", True))
        self.assertFalse(se.can_reconnect_studio(self.ROW, "UCONNECTOR", False))  # even whoever connected it
        self.assertFalse(se.can_reconnect_studio(None, "UANYONE", False))

    def test_a_different_account_is_refused_but_the_same_one_is_fine(self):
        self.assertIsNone(se.studio_account_refusal(self.ROW, "Studio@Example.com"))
        self.assertIn("studio@example.com", se.studio_account_refusal(self.ROW, "mentor@gmail.com"))
        self.assertIsNone(se.studio_account_refusal(None, "first@example.com"))


if __name__ == "__main__":
    unittest.main()
