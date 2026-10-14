import os
import sys
import unittest
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import digest as d  # noqa: E402
import mentor_home  # noqa: E402

NOW = datetime(2026, 10, 19, 1, 0, tzinfo=timezone.utc)
TODAY = date(2026, 10, 19)  # a Monday


def sub(day, status="In progress", progress=50, blocker="None", sid="s-a"):
    return {"startup_id": sid, "founder_id": "f", "status": status, "progress": progress, "blocker": blocker,
            "digest": "did things", "created_at": f"{day}T03:00:00+00:00"}


class GapTests(unittest.TestCase):
    def test_flags_checkins_without_code_only_when_a_repo_is_tracked(self):
        none = {"commits": 0, "prs_opened": 0, "prs_merged": 0}
        self.assertTrue(d.building_gap(2, True, none))
        self.assertFalse(d.building_gap(2, False, none))                    # no repo tracked: no data, no flag
        self.assertFalse(d.building_gap(0, True, none))                     # not checking in: other signals cover it
        self.assertFalse(d.building_gap(2, True, {**none, "commits": 3}))   # there is code activity


class AlertTests(unittest.TestCase):
    def summaries(self, subs):
        startups = [{"id": "s-a", "name": "Auvira", "stream": "GTM", "lead": "x"}]
        return mentor_home.summarize_startups(startups, [{"name": "Ann", "startup_id": "s-a"}], subs, NOW)

    def test_blocked_for_three_days_alerts_once_per_episode(self):
        s = self.summaries([sub("2026-10-15", "Blocked", blocker="OCR drops fields")])
        alerts = d.alert_candidates(s, TODAY)
        self.assertEqual(len(alerts), 1)
        self.assertIn("blocked for 3 days", alerts[0]["text"])
        self.assertEqual(alerts[0]["key"], d.alert_candidates(s, TODAY)[0]["key"])  # stable key -> sent once

    def test_recently_blocked_is_not_yet_a_nudge(self):
        self.assertEqual(d.alert_candidates(self.summaries([sub("2026-10-19", "Blocked", blocker="x")]), TODAY), [])

    def test_quiet_startups_alert(self):
        alerts = d.alert_candidates(self.summaries([sub("2026-10-08")]), TODAY)
        self.assertEqual(len(alerts), 1)
        self.assertIn("hasn't checked in for 10 days", alerts[0]["text"])

    def test_every_nudge_names_the_startup_and_its_founders(self):
        blocked = d.alert_candidates(self.summaries([sub("2026-10-15", "Blocked", blocker="x")]), TODAY)[0]["text"]
        quiet = d.alert_candidates(self.summaries([sub("2026-10-08")]), TODAY)[0]["text"]
        s = self.summaries([sub("2026-10-18")])
        s[0]["gap"], s[0]["checkins_7d"] = True, 2
        gap = d.alert_candidates(s, TODAY)[0]["text"]
        for text in (blocked, quiet, gap):
            self.assertIn("*Auvira* (Ann)", text)

    def test_gap_alert_is_once_per_week(self):
        s = self.summaries([sub("2026-10-18")])
        s[0]["gap"], s[0]["checkins_7d"] = True, 2
        a1 = d.alert_candidates(s, TODAY)[0]
        a2 = d.alert_candidates(s, date(2026, 10, 21))[0]   # same ISO week
        a3 = d.alert_candidates(s, date(2026, 10, 26))[0]   # next week
        self.assertEqual(a1["key"], a2["key"])
        self.assertNotEqual(a1["key"], a3["key"])


class DigestTests(unittest.TestCase):
    def test_digest_shape_and_numbers(self):
        startups = [{"id": "s-a", "name": "Auvira", "stream": "GTM", "lead": "x"},
                    {"id": "s-b", "name": "SharedOut", "stream": "Tech", "lead": "y"}]
        founders = [{"name": "Ann", "startup_id": "s-a"}, {"name": "Bo", "startup_id": "s-b"}]
        subs = [sub("2026-10-18", sid="s-a"), sub("2026-10-16", "Blocked", blocker="stuck", sid="s-b")]
        s = mentor_home.summarize_startups(startups, founders, subs, NOW)
        for x in s:
            x["checkins_7d"], x["work"], x["gap"] = 1, "5 commits (last 7 days)", False
        s[0]["goals_total"], s[0]["goals_done"] = 4, 1
        blocks = d.build_digest_blocks(s, TODAY, [((TODAY, 540), "Today, 9:00 AM-10:00 AM: *Sprint*")], [])
        text = chr(10).join((b.get("text") or {}).get("text", "") for b in blocks if isinstance(b.get("text"), dict))
        self.assertIn("1 on track · 1 blocked · 0 quiet", blocks[1]["elements"][0]["text"])
        self.assertLess(text.index("SharedOut"), text.index("Auvira"))   # blocked first
        self.assertIn("1/4 milestone goals done", text)
        self.assertIn("Sprint", text)


if __name__ == "__main__":
    unittest.main()
