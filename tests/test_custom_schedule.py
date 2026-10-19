import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import custom_schedule as c  # noqa: E402


def ms(n, sprint, title, end, goals=()):
    return {"title": f"Week {n} (Sprint {sprint}): {title}", "due_date": end, "status": "open", "goals": [{"title": g} for g in goals]}


ROWS = [ms(1, 1, "Thesis", "2026-10-25", ["1-page thesis"]), ms(2, 1, "Concept", "2026-11-01"),
        ms(3, 2, "Verification", "2026-11-08"), ms(4, 2, "Review & pause (family vacation)", "2026-11-15"),
        {"title": "Launch waitlist", "due_date": "2026-10-30", "status": "open", "goals": []}]


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.weeks = c.weeks_from_milestones(ROWS)

    def test_reads_weeks_and_ignores_other_milestones(self):
        self.assertEqual([w["n"] for w in self.weeks], [1, 2, 3, 4])
        self.assertEqual(self.weeks[0]["start"], date(2026, 10, 19))
        self.assertEqual(c.weeks_from_milestones(ROWS[:2]), [])  # two stray weeks are not a schedule

    def test_current_week_and_deliverable(self):
        self.assertEqual(c.current(self.weeks, date(2026, 10, 21))["n"], 1)
        self.assertIsNone(c.current(self.weeks, date(2026, 10, 18)))
        self.assertIsNone(c.current(self.weeks, date(2026, 11, 16)))
        d = c.deliverable(self.weeks, date(2026, 10, 21), {"id": "del-wk09", "week": "Week 9"})
        self.assertEqual((d["id"], d["week"], d["due_date"], d["sprint_phase"]), ("del-wk01", "Week 1", "2026-10-25", "Sprint 1"))
        self.assertIn("1-page thesis", d["title"])
        self.assertEqual(c.progress(self.weeks, date(2026, 11, 9)), {"week": 4, "total": 4, "phase": "Sprint 2", "paused": True})

    def test_session_days_skip_weekends_and_pause_weeks(self):
        self.assertTrue(c.is_session_day(self.weeks, date(2026, 10, 21)))   # Wed
        self.assertFalse(c.is_session_day(self.weeks, date(2026, 10, 24)))  # Sat
        self.assertFalse(c.is_session_day(self.weeks, date(2026, 11, 11)))  # pause week
        self.assertFalse(c.is_session_day(self.weeks, date(2026, 12, 1)))   # after the schedule

    def test_agent_lines(self):
        text = "\n".join(c.agent_lines(self.weeks, date(2026, 10, 21)))
        self.assertIn("Program week: 1 of 4", text)
        self.assertIn("CUSTOM", text)
        self.assertIn("Next week: Week 2", text)


if __name__ == "__main__":
    unittest.main()
