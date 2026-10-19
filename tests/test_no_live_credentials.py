"""Tests never see the real .env: no live database, Slack token, AI key or Google credentials."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import slack_bot  # noqa: E402


class NoLiveCredentialsTests(unittest.TestCase):
    def test_running_under_tests_is_detected(self):
        self.assertTrue(slack_bot.UNDER_TEST)

    def test_no_live_clients(self):
        if os.environ.get("VITE_SUPABASE_URL") or os.environ.get("SUPABASE_URL"):
            self.skipTest("credentials were exported in the shell itself")
        self.assertIsNone(slack_bot.supabase)
        self.assertIsNone(slack_bot.ai_client)
        self.assertFalse(slack_bot.GOOGLE_CLIENT_SECRET)


if __name__ == "__main__":
    unittest.main()
