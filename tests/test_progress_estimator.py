import os
import sys
import unittest
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import progress_estimator as pe  # noqa: E402

G1 = {"id": "goal-1", "title": "Create landing page", "milestone": "Wireframe & Landing Page", "done": False,
      "progress": None, "est_progress": 20}
G2 = {"id": "goal-2", "title": "Contact 5 SMEs", "milestone": "Outreach", "done": False, "progress": 40, "est_progress": None}
G3 = {"id": "goal-3", "title": "Wireframe", "milestone": "Wireframe & Landing Page", "done": True}


class EstimatorTests(unittest.TestCase):
    def test_display_prefers_done_then_estimate_then_official(self):
        self.assertEqual(pe.goal_value(G3), (100, False))
        self.assertEqual(pe.goal_value(G1), (20, True))
        self.assertEqual(pe.goal_value(G2), (40, False))
        self.assertEqual(pe.milestone_value([G1, G3]), (60, True))

    def test_reply_parsing_tolerates_fences_and_junk(self):
        self.assertEqual(pe.parse_reply('```json\n{"updates": [{"goal": "g1", "progress": 50}]}\n```'),
                         [{"goal": "g1", "progress": 50}])
        self.assertEqual(pe.parse_reply("no idea"), [])
        self.assertEqual(pe.parse_reply('{"updates": "nope"}'), [])

    def test_estimates_only_go_up_cap_at_95_and_skip_done_or_unknown_goals(self):
        refs = {"g1": G1, "g2": G2, "g3": G3}
        out = pe.decide(refs, [
            {"goal": "g1", "progress": 60, "reason": "PR #3 adds the signup form"},
            {"goal": "g2", "progress": 30},          # below official 40: ignored
            {"goal": "g3", "progress": 80},          # already done
            {"goal": "g9", "progress": 80},          # unknown
            {"goal": "g1", "progress": "lots"},      # not a number
        ])
        self.assertEqual([(c["goal"]["id"], c["new"], c["old"]) for c in out], [("goal-1", 60, 20)])
        capped = pe.decide(refs, [{"goal": "g1", "progress": 100, "looks_done": True}])
        self.assertEqual(capped[0]["new"], 95)
        self.assertTrue(capped[0]["looks_done"])

    def test_card_offers_done_only_when_it_looks_finished(self):
        c = {"goal": G1, "new": 60, "old": 20, "reason": "PR #3", "looks_done": False}
        ids = [e["action_id"] for e in pe.card(c)[1]["elements"]]
        self.assertEqual(ids, ["confirm_goal_estimate", "set_goal_progress"])
        self.assertIn("mark_goal_done", [e["action_id"] for e in pe.card({**c, "looks_done": True})[1]["elements"]])


class FakeTable:
    def __init__(self, db, name):
        self.db, self.name, self.op, self.payload = db, name, "select", None

    def __getattr__(self, _):
        return lambda *a, **k: self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def upsert(self, payload):
        self.op, self.payload = "upsert", payload
        return self

    def execute(self):
        if self.op != "select":
            self.db.writes.append((self.name, self.op, self.payload))
            return NS(data=None)
        return NS(data=self.db.tables.get(self.name, []))


class FakeDB:
    def __init__(self, tables):
        self.tables, self.writes = tables, []

    def table(self, name):
        return FakeTable(self, name)


def fake_ai(text):
    msg = NS(content=text)
    return NS(chat=NS(completions=NS(create=lambda **k: NS(choices=[NS(message=msg)]))))


class RunTests(unittest.TestCase):
    def db(self):
        return FakeDB({
            "integrations": [{"startup_id": "s1", "repos": ["a/web"], "selected_repos": None}],
            "progress_estimate_state": [],
            "signals": [{"id": "x", "type": "pull_request", "headline": "PR #3 merged", "detail": "Add signup form",
                         "meta": {"repo": "a/web"}, "created_at": "2026-10-15T05:00:00+00:00"},
                        {"id": "y", "type": "commit", "headline": "push to other repo", "detail": None,
                         "meta": {"repo": "a/old"}, "created_at": "2026-10-15T06:00:00+00:00"}],
            "milestones": [{"title": "Wireframe & Landing Page", "goals": [dict(G1)]}],
        })

    def test_stores_the_estimate_notifies_and_remembers_the_work(self):
        db, sent = self.db(), []
        n = pe.run(db, fake_ai('{"updates": [{"goal": "g1", "progress": 60, "reason": "signup form"}]}'), "m",
                   notify=lambda sid, blocks, text: sent.append(sid))
        self.assertEqual(n, 1)
        self.assertIn(("goals", "update", {"est_progress": 60, "est_reason": "signup form", "est_at": unittest.mock.ANY}),
                      [(t, o, p) for t, o, p in db.writes])
        self.assertEqual(sent, ["s1"])
        state = [p for t, o, p in db.writes if t == "progress_estimate_state"][0]
        self.assertEqual(state["last_signal_at"], "2026-10-15T05:00:00+00:00")  # only monitored-repo work counted

    def test_no_goals_leaves_work_unassessed(self):
        db = self.db()
        db.tables["milestones"] = []
        pe.run(db, fake_ai("{}"), "m")
        self.assertEqual(db.writes, [])


import unittest.mock  # noqa: E402

if __name__ == "__main__":
    unittest.main()
