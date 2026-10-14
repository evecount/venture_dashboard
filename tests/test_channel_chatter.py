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


    def test_channel_messages_never_reach_the_assistant_but_dms_do(self):
        calls, said = [], []
        old = (b.process_inbound_message, b.channels.ingest)
        b.process_inbound_message = lambda *a, **k: calls.append(a)
        b.channels.ingest = lambda msg: None
        try:
            for text in ("hello team", "/checkin I finished the deck", "can someone check the pricing page?"):
                b.handle_direct_or_channel_message({"channel_type": "channel", "text": text, "user": "U1"}, said.append)
            self.assertEqual((calls, said), ([], []))          # silent in channels, even for /checkin
            b.handle_direct_or_channel_message({"channel_type": "im", "text": "finished the deck", "user": "U1"}, said.append)
            self.assertEqual(len(calls), 1)                    # a DM is still answered
        finally:
            b.process_inbound_message, b.channels.ingest = old


if __name__ == "__main__":
    unittest.main()
