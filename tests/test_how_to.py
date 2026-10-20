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
        self.assertIn("What I can do", b.blocks_to_text(view["blocks"]))

    def test_home_guide_is_a_short_grid_per_role(self):
        for role in ("founder", "mentor"):
            grid = b.home_features_blocks(role)[1]
            self.assertLessEqual(len(grid["fields"]), 10)  # Slack's limit per section
            for f in grid["fields"]:
                self.assertLess(len(f["text"]), 120)  # a glance, not a paragraph
        founder = " ".join(f["text"] for f in b.home_features_blocks("founder")[1]["fields"])
        mentor = " ".join(f["text"] for f in b.home_features_blocks("mentor")[1]["fields"])
        self.assertIn("Check in", founder)
        self.assertNotIn("Check in", mentor)
        self.assertIn("Who's blocked", mentor)




class GreetingTests(unittest.TestCase):
    def test_bare_greetings_match(self):
        for t in ["hi", "Hello!", "hey there", "help", "start", "hi 👋", "  Hey  "]:
            self.assertTrue(b.GREETING_RE.match(t), t)

    def test_updates_that_start_like_a_greeting_reach_the_agent(self):
        for t in ["Hired a designer today", "Started customer interviews, 3 calls done", "Help, I'm stuck on pricing",
                  "Highlights: shipped login", "hey I finished the deck", "hi, quick question about gate 3"]:
            self.assertFalse(b.GREETING_RE.match(t), t)


if __name__ == "__main__":
    unittest.main()
