import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import slack_bot as b  # noqa: E402


class ChannelChatterTests(unittest.TestCase):
    def test_greetings_are_only_answered_in_direct_messages(self):
        self.assertTrue(b.is_direct_message({"channel_type": "im", "text": "hello"}))
        for channel_type in ("channel", "group", "mpim", None):
            self.assertFalse(b.is_direct_message({"channel_type": channel_type, "text": "hello"}), channel_type)

    def test_only_whole_message_greetings_match(self):
        for ok in ("hello", "Hi!", "hey there", "  help  ", "get started"):
            self.assertTrue(b.GREETING_RE.match(ok), ok)
        for no in ("hiring a designer next week", "history of the project", "hello team, which location are we meeting at?"):
            self.assertFalse(b.GREETING_RE.match(no), no)


if __name__ == "__main__":
    unittest.main()
