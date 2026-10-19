import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class NoJobsOnImportTests(unittest.TestCase):
    """Importing the bot (tests, dry runs, scripts) must not start its timed jobs against live Slack and Supabase."""

    def test_scheduler_is_not_running_after_import(self):
        import slack_bot
        sched = getattr(slack_bot, "scheduler", None)
        self.assertTrue(sched is None or not sched.running)


if __name__ == "__main__":
    unittest.main()
