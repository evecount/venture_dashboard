"""Founder Home tab: friendly due dates, "no goals yet" instead of 0/0, and mentor milestones count as set."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import slack_bot  # noqa: E402
import syllabus  # noqa: E402


class MilestoneLinesTests(unittest.TestCase):
    def test_goal_less_milestone_reads_naturally(self):
        lines = slack_bot._milestone_lines([{"title": "Build UI/UX for app", "due_date": "2026-10-23", "goals": []}])
        self.assertIn("due Friday, Oct 23", lines[0])
        self.assertIn("no goals yet", lines[0])
        self.assertNotIn("0/0", lines[0])

    def test_goal_less_milestone_shows_its_estimate(self):
        lines = slack_bot._milestone_lines([{"title": "Build UI", "goals": [], "est_progress": 40}])
        self.assertIn("~40%", lines[0])
        self.assertIn("estimated", lines[0])

    def test_goal_counts_still_show(self):
        lines = slack_bot._milestone_lines([{"title": "Outreach", "goals": [{"title": "a", "done": True},
                                                                            {"title": "b", "done": False}]}])
        self.assertIn("1/2 goals", lines[0])

    def test_friendly_date(self):
        self.assertEqual(syllabus.friendly_date("2026-10-23T00:00:00+00:00"), "Friday, Oct 23")
        self.assertEqual(syllabus.friendly_date("someday"), "someday")


class GettingStartedTests(unittest.TestCase):
    def test_mentor_set_milestones_count(self):
        blocks = slack_bot.getting_started_blocks("f1", {"status": "On track"}, [{"created_by_role": "mentor"}], [], [],
                                                  github_ready=False)
        self.assertEqual(blocks, [])  # profile, update and a milestone: nothing left to nag about

    def test_no_milestones_still_asks(self):
        blocks = slack_bot.getting_started_blocks("f1", {"status": "On track"}, [], [], [], github_ready=False)
        self.assertIn("Set your first milestone", blocks[0]["text"]["text"])


class HowToTests(unittest.TestCase):
    def test_compact_reminder_is_one_line(self):
        blocks = slack_bot.how_to_blocks("founder", compact=True)
        self.assertEqual(len(blocks), 2)
        self.assertIn("help", blocks[1]["elements"][0]["text"])

    def test_full_guide_by_default(self):
        self.assertGreater(len(slack_bot.how_to_blocks("founder")), 3)


if __name__ == "__main__":
    unittest.main()
