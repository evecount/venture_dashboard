"""Offline tests for the agent's role gating and tools. Run: python -m unittest discover tests"""
import json
import os
import sys
import unittest
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot_agent import Agent, build_tools  # noqa: E402


class Q:
    def __init__(self, data):
        self.data = data

    def __getattr__(self, _):
        return lambda *a, **k: self

    def execute(self):
        return NS(data=self.data)


class FakeSB:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return Q(self.tables.get(name, []))


class FakeMemory:
    def __init__(self):
        self.notes, self.tasks, self.facts_saved, self.log_rows = [], [], [], []
        self.ms, self.updates = [], []

    def history(self, *_):
        return []

    def log(self, uid, role, content):
        self.log_rows.append((role, content))

    def add_note(self, *a):
        self.notes.append(a)
        return True

    def add_task(self, *a):
        self.tasks.append(a)
        return True

    def open_tasks(self, *_a, **_k):
        return []

    def recent_notes(self, *_a, **_k):
        return []

    def facts(self, *_a, **_k):
        return []

    def recent_facts(self, *_a, **_k):
        return []

    def remember(self, *a):
        self.facts_saved.append(a)
        return True

    def complete_task(self, _):
        return True

    # milestones
    def milestones(self, startup_id=None, limit=40):
        items = [m for m in self.ms if startup_id is None or m["startup_id"] == startup_id]
        return items

    def add_milestone(self, startup_id, title, due, by, role):
        mid = f"mmmmmm{len(self.ms)}"
        self.ms.append({"id": mid, "startup_id": startup_id, "title": title, "due_date": due, "goals": [], "startups": {"name": "S"}})
        return mid

    def update_milestone(self, mid, patch):
        self.updates.append(("m", mid, patch))
        return True

    def add_goal(self, mid, title, by):
        for m in self.ms:
            if m["id"] == mid:
                m["goals"].append({"id": f"gggggg{len(m['goals'])}", "title": title, "done": False})
        return True

    def update_goal(self, gid, patch):
        self.updates.append(("g", gid, patch))
        return True

    def remove_goal(self, gid):
        self.updates.append(("rm", gid, None))
        return True


def fake_ai(calls, content=""):
    tool_calls = [NS(function=NS(name=n, arguments=json.dumps(a))) for n, a in calls]
    msg = NS(content=content, tool_calls=tool_calls)
    create = lambda **kw: NS(choices=[NS(message=msg)])  # noqa: E731
    return NS(chat=NS(completions=NS(create=create)))


STARTUPS = [{"id": "startup-auvira", "name": "Auvira", "stream": "GTM", "lead": "X"}]
FOUNDER = {"role": "founder", "slack_id": "U1", "name": "Sam", "context": {
    "founder_id": "f1", "startup_id": "startup-auvira", "startup_name": "Auvira", "name": "Sam",
    "stream": "GTM", "lead": "X", "deliverable": {"week": "WK 01", "title": "T", "due_date": "2026-10-16"}}}
MENTOR = {"role": "mentor", "slack_id": "UM", "name": "Mo"}


class AgentTests(unittest.TestCase):
    def agent(self, calls, content=""):
        mem = FakeMemory()
        return Agent(fake_ai(calls, content), "m", FakeSB({"startups": STARTUPS}), mem), mem

    def test_founder_has_no_mentor_tools(self):
        names = {t["function"]["name"] for t in build_tools("founder")}
        self.assertNotIn("add_note", names)
        self.assertNotIn("assign_startup", names)
        self.assertIn("propose_checkin", names)

    def test_mentor_has_no_checkin_tool(self):
        self.assertNotIn("propose_checkin", {t["function"]["name"] for t in build_tools("mentor")})

    def test_founder_cannot_use_mentor_tool_even_if_model_tries(self):
        agent, mem = self.agent([("add_note", {"startup_id": "startup-auvira", "note": "x"})])
        agent.respond(FOUNDER, "hi")
        self.assertEqual(mem.notes, [])

    def test_founder_task_pinned_to_own_startup(self):
        agent, mem = self.agent([("add_task", {"title": "Send deck", "startup_id": "startup-other", "due_date": "2026-10-20"})])
        agent.respond(FOUNDER, "remind me")
        self.assertEqual(mem.tasks[0][0], "startup-auvira")

    def test_mentor_note_saved_and_logged(self):
        agent, mem = self.agent([("add_note", {"startup_id": "startup-auvira", "note": "pricing unclear"})], "On it.")
        out = agent.respond(MENTOR, "note on Auvira")
        self.assertEqual(len(mem.notes), 1)
        self.assertIn("Note saved", out["text"])
        self.assertEqual([r for r, _ in mem.log_rows], ["user", "assistant"])

    def test_unknown_startup_rejected(self):
        agent, mem = self.agent([("add_note", {"startup_id": "nope", "note": "x"})])
        agent = Agent(fake_ai([("add_note", {"startup_id": "nope", "note": "x"})]), "m", FakeSB({"startups": []}), mem)
        self.assertIn("couldn't tell", agent.respond(MENTOR, "x")["text"])
        self.assertEqual(mem.notes, [])

    def test_checkin_proposal_clamped(self):
        agent, _ = self.agent([("propose_checkin", {"status": "Blocked", "progress": 250, "blocker": "b", "digest": "d"})])
        out = agent.respond(FOUNDER, "stuck")
        self.assertEqual(out["checkin"]["progress"], 100)

    def test_founder_remember_is_visible_audience(self):
        agent, mem = self.agent([("remember", {"fact": "Pivoting to B2B"})])
        agent.respond(FOUNDER, "we pivoted")
        self.assertEqual(mem.facts_saved[0][3], "all")

    def test_mentor_remember_is_private(self):
        agent, mem = self.agent([("remember", {"fact": "needs help", "startup_id": "startup-auvira"})])
        agent.respond(MENTOR, "x")
        self.assertEqual(mem.facts_saved[0][3], "mentors")

    # ---- milestones ----
    def test_founder_milestone_pinned_to_own_startup_with_goals(self):
        agent, mem = self.agent([("add_milestone", {"title": "10 interviews", "startup_id": "startup-other",
                                                    "due_date": "2026-10-23", "goals": ["Draft script", "Book 10 calls"]})])
        out = agent.respond(FOUNDER, "set a milestone")
        self.assertEqual(mem.ms[0]["startup_id"], "startup-auvira")
        self.assertEqual(len(mem.ms[0]["goals"]), 2)
        self.assertIn("2 goals", out["text"])

    def test_mentor_can_add_milestone_for_any_startup(self):
        agent, mem = self.agent([("add_milestone", {"title": "Pricing test", "startup_id": "startup-auvira"})])
        agent.respond(MENTOR, "x")
        self.assertEqual(mem.ms[0]["startup_id"], "startup-auvira")

    def test_tick_goal_by_ref(self):
        agent, mem = self.agent([("update_goal", {"goal_ref": "gggggg0", "done": True})])
        mem.ms.append({"id": "mmmmmm0", "startup_id": "startup-auvira", "title": "M", "goals": [
            {"id": "gggggg0-full", "title": "Draft script", "done": False}], "startups": {"name": "S"}})
        out = agent.respond(FOUNDER, "finished the script")
        self.assertEqual(mem.updates[0][2], {"done": True})
        self.assertIn("Goal done", out["text"])

    def test_founder_cannot_touch_other_startup_milestone(self):
        agent, mem = self.agent([("update_milestone", {"milestone_ref": "mmmmmm0", "status": "dropped"})])
        mem.ms.append({"id": "mmmmmm0", "startup_id": "startup-other", "title": "M", "goals": [], "startups": {"name": "O"}})
        # FakeMemory.milestones filters by startup, as the real one does, so the founder cannot resolve the ref
        out = agent.respond(FOUNDER, "drop it")
        self.assertEqual(mem.updates, [])
        self.assertIn("couldn't find", out["text"])

    def test_founder_cannot_edit_a_mentor_issued_milestone_but_can_tick_its_goals(self):
        agent, mem = self.agent([("update_milestone", {"milestone_ref": "mmmmmm0", "status": "dropped"}),
                                 ("add_goal", {"milestone_ref": "mmmmmm0", "title": "extra"}),
                                 ("update_goal", {"goal_ref": "gggggg0", "title": "renamed"}),
                                 ("remove_goal", {"goal_ref": "gggggg0"}),
                                 ("update_goal", {"goal_ref": "gggggg0", "done": True})])
        mem.ms.append({"id": "mmmmmm0", "startup_id": "startup-auvira", "title": "M", "created_by_role": "mentor",
                       "goals": [{"id": "gggggg0-x", "title": "G", "done": False}], "startups": {"name": "S"}})
        out = agent.respond(FOUNDER, "x")
        self.assertEqual(mem.updates, [("g", "gggggg0-x", {"done": True})])  # only the tick went through
        self.assertEqual(out["text"].count("set by your mentor"), 4)

    def test_mentor_can_edit_any_milestone(self):
        agent, mem = self.agent([("update_milestone", {"milestone_ref": "mmmmmm0", "status": "done"})])
        mem.ms.append({"id": "mmmmmm0", "startup_id": "startup-auvira", "title": "M", "created_by_role": "founder",
                       "goals": [], "startups": {"name": "S"}})
        agent.respond(MENTOR, "x")
        self.assertEqual(mem.updates[0][2], {"status": "done"})


if __name__ == "__main__":
    unittest.main()
