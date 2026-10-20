import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import slack_bot as b  # noqa: E402


def open_buttons(blocks):
    return [(i, e) for i, bl in enumerate(blocks) if bl.get("type") == "actions"
            for e in bl["elements"] if e.get("action_id") == "open_dashboard"]


class TopRowTests(unittest.TestCase):
    def setUp(self):
        self._old = (b.DASHBOARD_URL, b.STATE_SECRET)
        b.DASHBOARD_URL, b.STATE_SECRET = "https://dash.example/", "secret"

    def tearDown(self):
        b.DASHBOARD_URL, b.STATE_SECRET = self._old

    def test_founder_home_has_one_open_dashboard_button_right_under_the_title(self):
        ctx = {"founder_id": "f", "name": "Ann", "startup_id": "s", "startup_name": "Auvira", "stream": "GTM", "lead": "x",
               "deliverable": {"title": "T", "due_date": "2026-10-16"}}
        blocks = b.build_home_view(ctx, None, [], [], [], [])["blocks"]
        found = open_buttons(blocks)
        self.assertEqual([i for i, _ in found], [1])               # index 1 = directly below the header
        self.assertEqual(blocks[0]["type"], "header")

    def test_mentor_button_joins_the_mentor_view_switch_for_developers(self):
        blocks = [{"type": "header", "text": {"type": "plain_text", "text": "Mentor view"}},
                  {"type": "actions", "block_id": "home_mode", "elements": [{"type": "button", "action_id": "home_mode_mentor"},
                                                                          {"type": "button", "action_id": "home_mode_dev"}]},
                  {"type": "section", "text": {"type": "mrkdwn", "text": "x"}}]
        out = b.add_to_top_row(blocks, b.dashboard_button_element(slack_user_id="UMENTOR01"))
        self.assertEqual([e["action_id"] for e in out[1]["elements"]], ["home_mode_mentor", "home_mode_dev", "open_dashboard"])
        b.add_to_top_row(out, b.dashboard_button_element(slack_user_id="UMENTOR01"))   # idempotent
        self.assertEqual(len(open_buttons(out)), 1)

    def test_mentors_without_the_switch_get_a_top_row_of_their_own(self):
        blocks = [{"type": "header", "text": {"type": "plain_text", "text": "Mentor view"}}, {"type": "section", "text": {"type": "mrkdwn", "text": "x"}}]
        out = b.add_to_top_row(blocks, b.dashboard_button_element(slack_user_id="UMENTOR01"))
        self.assertEqual([i for i, _ in open_buttons(out)], [1])

    def test_mentor_home_no_longer_repeats_the_button_at_the_bottom(self):
        blocks = b.build_mentor_blocks([], title="Mentor view", slack_user_id="UMENTOR01", footer_button=False)
        self.assertEqual(open_buttons(blocks), [])
        self.assertEqual(len(open_buttons(b.build_mentor_blocks([], title="Cohort pulse", slack_user_id="UMENTOR01"))), 1)  # DMs keep it

    def test_nothing_is_added_when_no_dashboard_url_is_configured(self):
        b.DASHBOARD_URL = None
        blocks = [{"type": "header"}, {"type": "section"}]
        self.assertEqual(b.add_to_top_row(list(blocks), b.dashboard_button_element()), blocks)




class BrandLineTests(unittest.TestCase):
    def test_logo_and_name_come_first(self):
        with mock.patch.object(b, "DASHBOARD_URL", "https://dash.example/"):
            blocks = b.branded([{"type": "header"}])
        self.assertEqual(blocks[0]["block_id"], "brand")
        self.assertEqual(blocks[0]["elements"][0]["image_url"], "https://dash.example/email-logo.png")
        self.assertIn("Venture Studio", blocks[0]["elements"][1]["text"])
        self.assertEqual(blocks[1], {"type": "header"})

    def test_never_twice_never_past_the_block_limit_and_off_without_a_site(self):
        with mock.patch.object(b, "DASHBOARD_URL", "https://dash.example"):
            once = b.branded([{"type": "header"}])
            self.assertEqual(b.branded(once), once)
            full = [{"type": "divider"}] * 100
            self.assertEqual(b.branded(full), full)
        with mock.patch.object(b, "DASHBOARD_URL", None):
            self.assertEqual(b.branded([{"type": "header"}]), [{"type": "header"}])


if __name__ == "__main__":
    unittest.main()
