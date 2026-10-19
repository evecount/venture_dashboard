import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cohorts  # noqa: E402
import daily_checkin  # noqa: E402
import mentor_home  # noqa: E402
import syllabus  # noqa: E402


class CohortDeliverableTests(unittest.TestCase):
    """Check-ins are filed against the founder's own cohort week (what slack_bot.cohort_deliverable relies on)."""

    def test_two_cohorts_on_the_same_day_are_on_different_weeks(self):
        today = date(2026, 10, 19)
        one = cohorts.this_weeks_deliverable(date(2026, 10, 5), today)
        two = cohorts.this_weeks_deliverable(date(2026, 10, 19), today)
        self.assertEqual((one["week"], one["due"]), (3, date(2026, 10, 23)))
        self.assertEqual((two["week"], two["due"]), (1, date(2026, 10, 23)))
        self.assertNotEqual(one["title"], two["title"])

    def test_nothing_before_a_cohort_starts(self):
        self.assertIsNone(cohorts.this_weeks_deliverable(date(2026, 11, 2), date(2026, 10, 19)))



MVP1, MVP2 = date(2026, 10, 5), date(2026, 10, 19)
COHORTS = [{"id": "sg-01", "name": "MVP#1", "start": MVP1, "weeks": 12, "startup_ids": ["a"]},
           {"id": "sg-02", "name": "MVP#2", "start": MVP2, "weeks": 12, "startup_ids": ["b"]}]


class CohortCalendarTests(unittest.TestCase):
    """Everything the bot says about 'this week' follows the person's own cohort."""

    def test_syllabus_on_each_cohorts_calendar(self):
        today = date(2026, 10, 20)
        self.assertEqual(syllabus.current(today)["week"], "WK 03")              # file dates = MVP#1
        self.assertEqual(syllabus.current(today, MVP1)["week"], "WK 03")
        self.assertEqual(syllabus.current(today, MVP2)["week"], "WK 01")
        self.assertEqual(syllabus.current_deliverable(today, MVP2)["id"], "del-wk01")
        self.assertIn("Program week: WK 01", syllabus.schedule_lines(today, MVP2)[0])
        self.assertIsNone(syllabus.current(date(2026, 10, 16), MVP2))         # before MVP#2 starts

    def test_program_days_run_to_each_cohorts_own_end(self):
        jan8 = date(2027, 1, 8)  # MVP#2's last Friday, after MVP#1 has finished
        self.assertFalse(daily_checkin._session_day(jan8, None, MVP1))
        self.assertTrue(daily_checkin._session_day(jan8, None, MVP2))

    def test_mentors_see_every_running_cohort(self):
        today = date(2026, 10, 20)
        self.assertEqual(cohorts.week_labels(COHORTS, today), "MVP#1 week 3 · MVP#2 week 1")
        lines = mentor_home.coming_up(today, [], cohort_list=COHORTS)
        self.assertTrue(any("MVP#1 deliverable due" in l and "Interview insight" in l for l in lines))
        self.assertTrue(any("MVP#2 deliverable due" in l and "venture thesis" in l for l in lines))


if __name__ == "__main__":
    unittest.main()
