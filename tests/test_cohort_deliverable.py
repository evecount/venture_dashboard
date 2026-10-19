import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cohorts  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
