import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import slack_bot as b  # noqa: E402
import syllabus  # noqa: E402

CTX = {"founder_id": "f1", "name": "Ann Lee", "startup_id": "s1", "startup_name": "Auvira", "stream": "GTM", "lead": "Unassigned",
       "deliverable": {"id": "del-wk03", "week": "WK 03", "title": "Interview insight repo", "due_date": "2026-10-16"}}
PARSED = {"status": "In progress", "progress": 40, "blocker": "None", "digest": "Ran 3 customer interviews.", "stream": "GTM"}


def text_of(blocks):
    out = []
    for bl in blocks:
        out.append(b.blocks_to_text([bl]))
        out += [f["text"] for f in bl.get("fields", [])]
    return "\n".join(out)


class CheckinCardTests(unittest.TestCase):
    def test_card_speaks_to_the_founder_without_jargon(self):
        blocks = b.build_confirmation_card(CTX, PARSED, "raw")
        t = text_of(blocks)
        for word in ("Ran 3 customer interviews", "Look right?", "Interview insight repo", "Week 3: Interview", "Nothing is saved"):
            self.assertIn(word, t)
        for jargon in ("Synthesis", "Command Center", "Lead:", "Unassigned", "Sync"):
            self.assertNotIn(jargon, t)
        actions = next(bl for bl in blocks if bl["type"] == "actions")
        self.assertEqual([e["action_id"] for e in actions["elements"]], ["confirm_checkin", "edit_checkin"])
        self.assertEqual(json.loads(actions["elements"][0]["value"])["digest"], PARSED["digest"])

    def test_saved_card_has_no_buttons_and_offers_help_when_blocked(self):
        value = dict(PARSED, status="Blocked", blocker="No access to pilot data")
        blocks = b.saved_checkin_blocks(value)
        self.assertFalse(any(bl["type"] == "actions" for bl in blocks))
        t = text_of(blocks)
        self.assertIn("No access to pilot data", t)
        self.assertIn("set up a call", t)
        self.assertNotIn("set up a call", text_of(b.saved_checkin_blocks(PARSED)))


class WelcomeTests(unittest.TestCase):
    def test_welcome_explains_how_it_works_and_one_next_step(self):
        t = b.founder_welcome_text("Ann Lee", "Auvira")
        for bit in ("Welcome, Ann", "Auvira", "Nothing is saved until you press *Save*", "5 PM", "mentors see", "Try it now", "help"):
            self.assertIn(bit, t)
        self.assertNotIn("Command Center", t)

    def test_greeting_replies_by_role(self):
        with mock.patch.object(b, "safe_snapshot", return_value=[]):
            founder, _ = b.greeting_reply("founder", "Ann Lee", "hi")
            help_text, help_blocks = b.greeting_reply("founder", "Ann Lee", "help")
            stranger, _ = b.greeting_reply(None, "", "hello")
        self.assertIn("Hey Ann", founder)
        self.assertIn("Check in", b.blocks_to_text(help_blocks))
        self.assertNotEqual(help_blocks[0]["type"], "divider")
        self.assertIn("set up", stranger)


class GettingStartedTests(unittest.TestCase):
    def test_new_founder_sees_the_checklist(self):
        blocks = b.getting_started_blocks("f1", None, [], [], [])
        t = b.blocks_to_text(blocks)
        self.assertIn("1 of 4 done", t)
        self.assertIn("Send your first update", t)
        self.assertIn("Optional", t)

    def test_checklist_disappears_when_done(self):
        conns = [{"founder_id": "f1", "repos": [{"full_name": "a/b"}], "monitored": ["a/b"]}]
        with mock.patch.object(b.integrations, "monitored_repos", return_value=["a/b"]):
            blocks = b.getting_started_blocks("f1", {"status": "On Track"}, [{"created_by_role": "founder"}], conns, [])
        self.assertEqual(blocks, [])

    def test_mentor_milestones_tick_the_milestone_step(self):
        # A founder whose mentors already set milestones has something to work toward: no "set your first" nag.
        blocks = b.getting_started_blocks("f1", {"status": "On Track"}, [{"created_by_role": "mentor"}], [], [],
                                          github_ready=False)
        self.assertEqual(blocks, [])

    def test_home_no_longer_shows_an_advisor(self):
        with mock.patch.object(b, "github_link", return_value=None), mock.patch.object(b, "google_link", return_value=None):
            view = b.build_home_view(dict(CTX, lead="Mo"), None, [], [], [], [])
        self.assertNotIn("Advisor", json.dumps(view))
        self.assertIn("Getting started", json.dumps(view))


class ProgramOutlineTests(unittest.TestCase):
    def test_one_line_per_week(self):
        lines = syllabus.program_outline()
        self.assertEqual(len(lines), 12)
        self.assertTrue(lines[0].startswith("- Week 1 ("))


if __name__ == "__main__":
    unittest.main()
