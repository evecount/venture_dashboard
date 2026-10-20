"""The agent's tool loop, multi-card turns, skills and look-ups. Run: python -m unittest discover tests"""
import json
import os
import sys
import unittest
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot_agent  # noqa: E402
import bot_skills  # noqa: E402
import integrations  # noqa: E402
from bot_agent import Agent, build_tools  # noqa: E402
from test_bot_agent import FOUNDER, MENTOR, STARTUPS, FakeMemory, FakeSB  # noqa: E402


def call(name, args, cid=None):
    return NS(id=cid, function=NS(name=name, arguments=json.dumps(args)))


class Script:
    """A model that answers with the given messages in order (then plain text), recording every request."""

    def __init__(self, *turns):
        self.turns, self.requests = list(turns), []

    def create(self, **kw):
        self.requests.append({**kw, "messages": list(kw["messages"])})  # a snapshot: the agent keeps appending
        content, calls = self.turns.pop(0) if self.turns else ("", [])
        return NS(choices=[NS(message=NS(content=content, tool_calls=calls))])


def agent_with(script, tables=None, memory=None, **kw):
    mem = memory or FakeMemory()
    a = Agent(NS(chat=NS(completions=script)), "m", FakeSB(tables or {"startups": STARTUPS}), mem, **kw)
    a._context_parts = lambda ident: {"ctx": "CTX", "sched": "", "aware": "", "channels": ""}
    return a, mem


class LoopTests(unittest.TestCase):
    def test_look_up_then_act_in_one_message(self):
        s = Script(("", [call("startup_detail", {"startup": "Auvira"}, "c1")]),
                   ("", [call("add_task", {"title": "Chase pricing", "startup_id": "startup-auvira"}, "c2")]),
                   ("Added a follow-up.", []))
        a, mem = agent_with(s)
        out = a.respond(MENTOR, "look at Auvira and add a follow-up")
        self.assertEqual(len(mem.tasks), 1)
        self.assertIn("Task added", out["text"])
        self.assertEqual(s.requests[1]["messages"][-1]["tool_call_id"], "c1")  # the look-up result went back to the model
        self.assertIn("Auvira", s.requests[1]["messages"][-1]["content"])

    def test_plain_actions_need_a_single_call(self):
        s = Script(("On it.", [call("add_note", {"startup_id": "startup-auvira", "note": "x"})]))
        a, mem = agent_with(s)
        out = a.respond(MENTOR, "note it")
        self.assertEqual(len(s.requests), 1)
        self.assertEqual(out["text"], "On it.\n📝 Note saved.")

    def test_the_same_action_never_runs_twice_in_a_turn(self):
        same = call("add_task", {"title": "Once", "startup_id": "startup-auvira"})
        s = Script(("", [call("startup_detail", {"startup": "Auvira"}), same]), ("", [same]), ("Done.", []))
        a, mem = agent_with(s)
        a.respond(MENTOR, "x")
        self.assertEqual(len(mem.tasks), 1)

    def test_a_warning_goes_back_to_the_model_which_puts_it_right(self):
        s = Script(("", [call("add_note", {"startup_id": "nope", "note": "x"})]),
                   ("", [call("add_note", {"startup_id": "startup-auvira", "note": "x"})]), ("Saved on Auvira.", []))
        a, mem = agent_with(s)
        out = a.respond(MENTOR, "note on auvira")
        self.assertEqual(len(mem.notes), 1)
        self.assertNotIn("couldn't tell", out["text"])  # fixed, so the stale warning isn't shown
        self.assertIn("Note saved", out["text"])

    def test_the_last_round_has_no_tools_so_it_always_answers(self):
        looks = [("", [call("search_records", {"query": f"word{i}"})]) for i in range(bot_agent.MAX_ROUNDS)]
        s = Script(*looks)
        a, _ = agent_with(s)
        a.respond(MENTOR, "x")
        self.assertEqual(len(s.requests), bot_agent.MAX_ROUNDS)
        self.assertNotIn("tools", s.requests[-1])
        self.assertIn("tools", s.requests[0])

    def test_tool_calls_are_echoed_with_their_thought_signature(self):
        class SDKCall(NS):
            def model_dump(self, exclude_none=True):
                return {"id": self.id, "type": "function", "function": {"name": self.function.name, "arguments": self.function.arguments},
                        "extra_content": {"google": {"thought_signature": "SIG"}}}
        c = SDKCall(id="c9", function=NS(name="search_records", arguments='{"query": "pricing"}'))
        s = Script(("", [c]), ("Nothing yet.", []))
        a, _ = agent_with(s)
        a.respond(MENTOR, "pricing?")
        echoed = s.requests[1]["messages"][-2]
        self.assertEqual(echoed["tool_calls"][0]["extra_content"]["google"]["thought_signature"], "SIG")

    def test_several_cards_in_one_turn(self):
        tables = {"startups": STARTUPS, "founders": [{"name": "Ann", "email": "ann@a.io", "slack_user_id": "UANN00001", "startups": {"name": "Auvira"}}],
                  "mentors": [{"name": "Mo", "email": "mo@s.io", "slack_user_id": "UM"}]}
        mem = FakeMemory()
        ids = iter(["m1", "m2"])
        mem.save_meeting = lambda who, payload: next(ids)
        s = Script(("", [call("schedule_meeting", {"title": "Sprint", "date": "2099-01-01", "start_time": "15:00", "where": "virtual",
                                                   "attendees": ["everyone"]}),
                         call("announce", {"message": "Sprint is on", "audience": ["everyone"]})]))
        a, _ = agent_with(s, tables, mem, studio_connected=lambda: True)
        out = a.respond(MENTOR, "set up the sprint meeting and tell everyone")
        self.assertEqual([m["id"] for m in out["meetings"]], ["m1", "m2"])
        self.assertEqual(out["meeting"]["id"], "m1")


class SkillTests(unittest.TestCase):
    def test_every_skill_file_is_valid_and_names_real_tools(self):
        skills = bot_skills.Skills()
        self.assertIn("elid", skills.all)
        for name, s in skills.all.items():
            have = {t["function"]["name"] for role in s["roles"] for t in build_tools(role, skills)}
            self.assertTrue(set(s["tools"]) <= have, f"{name} names a tool no role has: {set(s['tools']) - have}")
            self.assertTrue(s["body"], name)

    def test_triggers_preload_a_skill_and_unlock_its_tools(self):
        s = Script(("ok", []))
        a, _ = agent_with(s)
        a.respond(MENTOR, "set up a meeting with Arthur on Thursday")
        names = {t["function"]["name"] for t in s.requests[0]["tools"]}
        self.assertIn("schedule_meeting", names)
        self.assertIn("### Skill: meetings", s.requests[0]["messages"][0]["content"])

    def test_skill_tools_stay_hidden_until_loaded_then_use_skill_unlocks_them(self):
        s = Script(("", [call("use_skill", {"names": ["routines"]})]), ("ok", []))
        a, _ = agent_with(s)
        a.respond(MENTOR, "can you handle the founders for me")
        first = {t["function"]["name"] for t in s.requests[0]["tools"]}
        second = {t["function"]["name"] for t in s.requests[1]["tools"]}
        self.assertNotIn("create_routine", first)
        self.assertIn("create_routine", second)
        self.assertIn("call create_routine", s.requests[1]["messages"][-1]["content"])  # the skill's instructions came back

    def test_founders_cannot_load_mentor_skills(self):
        s = Script(("", [call("use_skill", {"names": ["routines"]})]), ("ok", []))
        a, _ = agent_with(s)
        a.respond(FOUNDER, "hello")
        self.assertIn("No such skill", s.requests[1]["messages"][-1]["content"])
        self.assertNotIn("create_routine", {t["function"]["name"] for t in s.requests[1]["tools"]})

    def test_elid_loads_for_concept_questions(self):
        self.assertIn("elid", bot_skills.Skills().matching("founder", "what does a SAFE note mean?"))
        self.assertNotIn("elid", bot_skills.Skills().matching("founder", "what's due this week"))


class RoutingTests(unittest.TestCase):
    def test_small_talk_goes_to_the_fast_model_but_confirmations_do_not(self):
        s = Script(("You're welcome!", []), ("ok", []))
        a, _ = agent_with(s, fast_model="lite")
        a.respond(FOUNDER, "thanks so much! 🙏")
        a.respond(FOUNDER, "ok")
        self.assertEqual([r["model"] for r in s.requests], ["lite", "m"])

    def test_chat_thinks_least_and_analysis_skills_think_more(self):
        s = Script(("hi", []), ("digest", []))
        a, _ = agent_with(s)
        a.respond(MENTOR, "who is blocked?")
        a.respond(MENTOR, "catch me up on the cohort")
        self.assertEqual([r["reasoning_effort"] for r in s.requests], ["none", "low"])

    def test_a_model_that_refuses_a_thinking_level_is_asked_without_it(self):
        seen = []

        def create(**kw):
            seen.append("reasoning_effort" in kw)
            if "reasoning_effort" in kw:
                raise RuntimeError("Error code: 400 - Request contains an invalid argument.")
            return NS(choices=[NS(message=NS(content="ok", tool_calls=None))])
        a, _ = agent_with(NS(create=create))
        a.respond(MENTOR, "x")
        a.respond(MENTOR, "y")
        self.assertEqual(seen, [True, False, False])  # tried once, then remembered


class LookupTests(unittest.TestCase):
    def test_founder_detail_is_pinned_to_their_startup_and_has_no_notes(self):
        mem = FakeMemory()
        mem.recent_notes = lambda *a, **k: [{"created_at": "2026-10-01", "author_name": "Mo", "body": "SECRET NOTE"}]
        s = Script(("", [call("startup_detail", {"startup": "startup-other"})]), ("ok", []))
        a, _ = agent_with(s, memory=mem)
        a.respond(FOUNDER, "show me everything")
        result = s.requests[1]["messages"][-1]["content"]
        self.assertIn("Auvira", result)
        self.assertNotIn("SECRET NOTE", result)

    def test_mentor_detail_includes_notes(self):
        mem = FakeMemory()
        mem.recent_notes = lambda *a, **k: [{"created_at": "2026-10-01", "author_name": "Mo", "body": "pricing unclear"}]
        a, _ = agent_with(Script(), memory=mem)
        self.assertIn("pricing unclear", a._startup_detail(MENTOR, {"startup": "auvira"}))

    def test_unknown_startup_is_a_warning(self):
        a, _ = agent_with(Script())
        self.assertTrue(a._startup_detail(MENTOR, {"startup": "zzz"}).startswith("⚠️"))


class ActivityTests(unittest.TestCase):
    def test_batched_activity_matches_the_per_startup_count(self):
        rows = [{"startup_id": "a", "type": "commit", "meta": {"repo": "o/a", "commits": 3}, "created_at": "2026-10-19"},
                {"startup_id": "a", "type": "commit", "meta": {"repo": "o/old", "commits": 9}, "created_at": "2026-10-18"},
                {"startup_id": "b", "type": "pull_request", "meta": {"repo": "o/b", "merged": True}, "created_at": "2026-10-17"}]
        gh = [{"startup_id": "a", "repos": ["o/a"]}, {"startup_id": "b", "repos": ["o/b", "o/c"], "selected_repos": ["o/b"]}]
        got = integrations.activity_from_rows(rows, gh)
        self.assertEqual(got["a"]["commits"], 3)  # the deselected repo doesn't count
        self.assertEqual(got["b"]["prs_merged"], 1)


if __name__ == "__main__":
    unittest.main()
