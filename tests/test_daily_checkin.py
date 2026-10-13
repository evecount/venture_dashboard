import os
import sys
import unittest
from datetime import datetime
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import daily_checkin as d  # noqa: E402


class Q:
    def __init__(self, data):
        self.data = data

    def __getattr__(self, _):
        return lambda *a, **k: self

    def execute(self):
        return NS(data=self.data)


FOUNDERS = [
    {"id": "a", "name": "Priya Rao", "startup_id": "s", "slack_user_id": "U0ABC12345"},
    {"id": "b", "name": "Demo", "startup_id": "s", "slack_user_id": "U_NEXUS_LEAD"},
    {"id": "c", "name": "Alex Lee", "startup_id": "t", "slack_user_id": None},
]


class SB:
    def __init__(self, replied=False):
        self.replied = replied

    def table(self, name):
        if name == "founders":
            return Q(FOUNDERS)
        return Q([{"id": 1}] if self.replied else [])


class Mem:
    def milestones(self, _):
        return [{"goals": [{"title": "Book calls", "done": False}, {"title": "Draft", "done": True}]}]

    def log(self, *_):
        pass


class Client:
    def __init__(self):
        self.sent = []

    def chat_postMessage(self, **kw):
        self.sent.append(kw)


TUE = datetime(2026, 10, 13, 17, 0, tzinfo=d.SGT)
SAT = datetime(2026, 10, 17, 17, 0, tzinfo=d.SGT)
WED_AM = datetime(2026, 10, 14, 9, 30, tzinfo=d.SGT)


class DailyTests(unittest.TestCase):
    def test_only_real_linked_founders_are_prompted(self):
        c = Client()
        sent = d.send_daily_prompts(c, SB(), Mem(), TUE)
        self.assertEqual([u for u, _ in sent], ["U0ABC12345"])
        self.assertEqual(len(c.sent), 1)

    def test_prompt_mentions_only_open_goals(self):
        text = d.send_daily_prompts(Client(), SB(), Mem(), TUE)[0][1]
        self.assertIn("Book calls", text)
        self.assertNotIn("Draft", text)

    def test_no_prompt_on_days_without_a_session(self):
        self.assertEqual(d.send_daily_prompts(Client(), SB(), Mem(), SAT), [])

    def test_nudge_only_if_no_reply(self):
        self.assertEqual(len(d.send_nudges(Client(), SB(replied=False), Mem(), WED_AM)), 1)
        self.assertEqual(len(d.send_nudges(Client(), SB(replied=True), Mem(), WED_AM)), 0)

    def test_dry_run_sends_nothing(self):
        c = Client()
        d.send_daily_prompts(c, SB(), Mem(), TUE, dry_run=True)
        self.assertEqual(c.sent, [])


if __name__ == "__main__":
    unittest.main()
