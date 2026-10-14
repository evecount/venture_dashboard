import json
import os
import sys
import unittest
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import announce as a  # noqa: E402
import slack_bot as b  # noqa: E402
from bot_agent import Agent  # noqa: E402

FOUNDERS = [{"name": "Ann Founder", "slack_user_id": "UANN000001", "startups": {"name": "Auvira"}},
            {"name": "Bo Founder", "slack_user_id": "UBO0000001", "startups": {"name": "SharedOut"}},
            {"name": "Cy Pending", "slack_user_id": None, "startups": {"name": "Auvira"}}]
MENTORS = [{"name": "Mo Mentor", "slack_user_id": "UMENTOR001"}, {"name": "Di Mentor", "slack_user_id": "UMENTOR002"}]


class RecipientTests(unittest.TestCase):
    def test_everyone_means_founders_and_other_mentors_but_not_the_sender(self):
        got = a.resolve_recipients(["everyone"], FOUNDERS, MENTORS, "UMENTOR001")
        self.assertEqual({p["slack"] for p in got["people"]}, {"UANN000001", "UBO0000001", "UMENTOR002"})
        self.assertEqual(got["unreachable"], ["Cy Pending"])

    def test_groups_startups_and_names(self):
        self.assertEqual({p["name"] for p in a.resolve_recipients(["founders"], FOUNDERS, MENTORS, "UMENTOR001")["people"]}, {"Ann Founder", "Bo Founder"})
        self.assertEqual([p["name"] for p in a.resolve_recipients(["Auvira"], FOUNDERS, MENTORS, "UMENTOR001")["people"]], ["Ann Founder"])
        self.assertEqual([p["name"] for p in a.resolve_recipients(["<@UBO0000001>"], FOUNDERS, MENTORS, "UMENTOR001")["people"]], ["Bo Founder"])
        got = a.resolve_recipients(["Zed"], FOUNDERS, MENTORS, "UMENTOR001")
        self.assertEqual((got["people"], got["unknown"]), ([], ["Zed"]))


class Q:
    def __init__(self, data):
        self.data = data

    def __getattr__(self, _):
        return lambda *a, **k: self

    def execute(self):
        return NS(data=self.data)


class SB:
    def table(self, name):
        return Q({"founders": FOUNDERS, "mentors": MENTORS}.get(name, []))


class Mem:
    def __init__(self):
        self.saved = []

    def history(self, *_):
        return []

    def log(self, *_):
        pass

    def save_meeting(self, who, payload):
        self.saved.append(payload)
        return "ann-1"

    def __getattr__(self, _):
        return lambda *x, **k: []


def ai(call):
    msg = NS(content="", tool_calls=[NS(function=NS(name=call[0], arguments=json.dumps(call[1])))])
    return NS(chat=NS(completions=NS(create=lambda **kw: NS(choices=[NS(message=msg)]))))


class AnnounceAgentTests(unittest.TestCase):
    MENTOR = {"role": "mentor", "slack_id": "UMENTOR001", "name": "Mo Mentor"}
    FOUNDER = {"role": "founder", "slack_id": "UANN000001", "name": "Ann",
               "context": {"founder_id": "f", "startup_id": "s", "startup_name": "S", "name": "Ann", "stream": "GTM", "lead": "x", "deliverable": {}}}

    def run_agent(self, ident, args):
        mem = Mem()
        return Agent(ai(("announce", args)), "m", SB(), mem).respond(ident, "tell everyone"), mem

    def test_mentor_announcement_is_a_proposal_with_recipients(self):
        out, mem = self.run_agent(self.MENTOR, {"message": "Office hours moved to 4 PM", "audience": ["everyone"]})
        self.assertEqual(out["meeting"]["kind"], "announce")
        self.assertEqual(len(out["meeting"]["recipients"]), 3)
        self.assertEqual(mem.saved[0]["requester_slack"], "UMENTOR001")

    def test_founders_cannot_announce(self):
        out, mem = self.run_agent(self.FOUNDER, {"message": "hi", "audience": ["everyone"]})
        self.assertIsNone(out["meeting"])
        self.assertEqual(mem.saved, [])

    def test_the_card_shows_who_gets_it_and_who_does_not(self):
        m = {"id": "x", "kind": "announce", "message": "Office hours moved to 4 PM", "recipients": [{"name": "Ann", "slack": "U1"}],
             "unreachable": ["Cy Pending"], "unknown": []}
        text = b.blocks_to_text(b.build_meeting_card(m))
        self.assertIn("1 people", text.replace("*", ""))
        self.assertIn("Office hours moved to 4 PM", text)
        self.assertIn("Cy Pending", text)


class ChecklistTests(unittest.TestCase):
    CTX = {"founder_id": "f1", "startup_id": "s1"}

    def test_new_founder_sees_what_is_left(self):
        text = b.blocks_to_text(b.setup_checklist_blocks(self.CTX, None, [], [], []))
        self.assertIn("1 of 5 done", text)
        self.assertIn("⬜ Send your first check-in", text)

    def test_progress_is_ticked_off_and_hidden_when_complete(self):
        gh = [{"founder_id": "f1", "repos": ["a/b"], "selected_repos": ["a/b"]}]
        ms = [{"created_by_role": "founder", "title": "x"}]
        part = b.blocks_to_text(b.setup_checklist_blocks(self.CTX, {"status": "In progress"}, ms, gh, []))
        self.assertIn("4 of 5 done", part)
        self.assertIn("⬜ Connect Google Calendar", part)
        self.assertEqual(b.setup_checklist_blocks(self.CTX, {"status": "x"}, ms, gh, [{"founder_id": "f1"}]), [])

    def test_a_mentor_issued_milestone_or_someone_elses_connection_does_not_count_as_yours(self):
        gh = [{"founder_id": "other", "repos": ["a/b"], "selected_repos": ["a/b"]}]
        text = b.blocks_to_text(b.setup_checklist_blocks(self.CTX, None, [{"created_by_role": "mentor"}], gh, [{"founder_id": "other"}]))
        self.assertIn("1 of 5 done", text)


if __name__ == "__main__":
    unittest.main()
