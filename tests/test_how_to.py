import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import slack_bot as b  # noqa: E402


class HowToTests(unittest.TestCase):
    def test_roles_get_different_guidance(self):
        founder = b.blocks_to_text(b.how_to_blocks("founder"))
        mentor = b.blocks_to_text(b.how_to_blocks("mentor"))
        self.assertIn("Check in", founder)
        self.assertNotIn("Check in", mentor)
        self.assertIn("Who's blocked", mentor)
        self.assertNotIn("Who's blocked", founder)
        self.assertIn("Monday 9:00 AM digest", mentor)

    def test_blocks_fit_slacks_limits(self):
        for role in ("founder", "mentor"):
            blocks = b.how_to_blocks(role)
            self.assertLess(len(blocks), 20)
            for bl in blocks:
                if isinstance(bl.get("text"), dict):
                    self.assertLessEqual(len(bl["text"]["text"]), 3000)

    def test_founder_home_shows_the_section_and_stays_under_the_block_limit(self):
        ctx = {"founder_id": "f", "name": "Ann", "startup_id": "s", "startup_name": "Auvira", "stream": "GTM", "lead": "x",
               "deliverable": {"title": "T", "due_date": "2026-10-16"}}
        view = b.build_home_view(ctx, None, [], [], [], [], meeting_lines=["- x"])
        self.assertLess(len(view["blocks"]), 100)
        self.assertIn("How to use Venture Buddy", b.blocks_to_text(view["blocks"]))


if __name__ == "__main__":
    unittest.main()
