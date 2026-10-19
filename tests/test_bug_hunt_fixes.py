import json
import os
import sys
import unittest
from datetime import date, datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import digest  # noqa: E402
import mentor_home  # noqa: E402
import slack_bot as b  # noqa: E402
import studio_events  # noqa: E402


class BlockedAlertKeyTests(unittest.TestCase):
    def test_key_is_stable_while_the_same_blocked_run_continues(self):
        subs = [{"startup_id": "s", "founder_id": "f", "status": "Blocked", "progress": 10, "blocker": "x",
                 "digest": "d", "created_at": "2026-10-10T03:00:00+00:00"}]
        keys = set()
        for day in (13, 14, 15):
            now = datetime(2026, 10, day, 3, tzinfo=timezone.utc)
            sm = mentor_home.summarize_startups([{"id": "s", "name": "S"}], [], subs, now)
            keys |= {a["key"] for a in digest.alert_candidates(sm, date(2026, 10, day))}
        self.assertEqual(len(keys), 1)


class CheckinCardTests(unittest.TestCase):
    def test_button_value_stays_under_slacks_2000_characters_with_non_ascii_text(self):
        ctx = {"startup_id": "startup-x", "founder_id": "founder-u0abcdefg", "startup_name": "X", "stream": "GTM",
               "deliverable": {"id": "del-wk01", "week": "WK 01", "title": "T"}}
        parsed = {"status": "On Track", "progress": 50, "stream": "GTM", "blocker": "“" * 300, "digest": "é" * 400}
        blocks = b.build_confirmation_card(ctx, parsed, "😀" * 500)
        for el in next(x for x in blocks if x["type"] == "actions")["elements"]:
            self.assertLessEqual(len(el["value"]), 2000)
            json.loads(el["value"])

    def test_commit_reports_failure_instead_of_pretending(self):
        failing = mock.MagicMock()
        failing.table.return_value.insert.return_value.execute.side_effect = RuntimeError("db down")
        value = {"startup_id": "s", "deliverable_id": "d", "founder_id": "f", "status": "In progress",
                 "progress": 5, "blocker": "None", "digest": "x"}
        with mock.patch.object(b, "supabase", failing):
            self.assertFalse(b.commit_checkin(value, "a"))
        ok = mock.MagicMock()
        with mock.patch.object(b, "supabase", ok):
            self.assertTrue(b.commit_checkin(value, "a"))


class GoalEstimateTests(unittest.TestCase):
    def test_stale_confirm_does_not_reset_progress(self):
        sb = mock.MagicMock()
        sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [{"est_progress": None}]
        client = mock.MagicMock()
        body = {"actions": [{"value": "g1"}], "user": {"id": "U1"}}
        with mock.patch.object(b, "supabase", sb), mock.patch.object(b, "_settle_goal") as settle:
            b.handle_confirm_goal_estimate(lambda: None, body, client)
        settle.assert_not_called()
        client.chat_postMessage.assert_called_once()


class StudioSyncTests(unittest.TestCase):
    def test_google_error_leaves_dashboard_meetings_alone(self):
        gcal = mock.MagicMock()
        gcal.events.side_effect = RuntimeError("google down")
        with mock.patch.object(b, "gcal", gcal), mock.patch.object(b, "studio_row", return_value={"refresh_token": "t"}):
            self.assertEqual(b.studio_events_fn(30), [])
            self.assertIsNone(b.studio_events_fn(30, strict=True))
        sb = mock.MagicMock()
        self.assertEqual(studio_events.sync(sb, None), 0)
        sb.table.assert_not_called()


if __name__ == "__main__":
    unittest.main()
