"""A developer marks a feature request implemented and the person who asked gets one DM."""
import os
import sys
import unittest
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import personal  # noqa: E402
from bot_agent import Agent, build_tools  # noqa: E402
from test_bot_agent import FOUNDER, MENTOR, FakeMemory, fake_ai  # noqa: E402


class MemSB:
    """Just enough of the Supabase client for the memories table."""

    def __init__(self, rows):
        self.rows = rows

    def table(self, name):
        return MemQuery(self.rows)


class MemQuery:
    def __init__(self, rows):
        self.rows, self.filters, self.patch, self.op = rows, [], None, "select"

    def select(self, *_a):
        return self

    def eq(self, k, v):
        self.filters.append((k, v))
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a):
        return self

    def update(self, patch):
        self.op, self.patch = "update", patch
        return self

    def execute(self):
        hit = [r for r in self.rows if all(r.get(k) == v for k, v in self.filters)]
        if self.op == "update":
            for r in hit:
                r.update(self.patch)
        return NS(data=hit)


def rows():
    return [{"id": "aaaaaaaa-1", "subject_type": "feature_request", "subject_id": "UWAI", "fact": "Leung Wai-Leng: Kanban board", "created_at": "2026-11-17T09:00:00"},
            {"id": "bbbbbbbb-2", "subject_type": "feature_request", "subject_id": "USAM", "fact": "Sam Lee: Dark mode", "created_at": "2026-11-18T09:00:00"}]


def agent(data, developer=True, sent=None):
    sent = sent if sent is not None else []
    a = Agent(fake_ai([]), "m", MemSB(data), FakeMemory(), is_developer=lambda sid: developer, notify_user=lambda sid, text: sent.append((sid, text)))
    return a, sent


class MarkTests(unittest.TestCase):
    def test_marks_it_and_dms_the_originator_by_given_name_once(self):
        data = rows()
        a, sent = agent(data)
        out = a._mark_feature(MENTOR, {"ref": "aaaaaa", "message": "Say 'start <task>' to move a task."})
        self.assertIn("Marked implemented", out)
        self.assertEqual(sent[0][0], "UWAI")
        self.assertIn("Hi Wai Leng", sent[0][1])
        self.assertIn("Kanban board", sent[0][1])
        self.assertIn("start <task>", sent[0][1])
        self.assertTrue(data[0]["fact"].startswith("[implemented "))
        again = a._mark_feature(MENTOR, {"ref": "aaaaaa"})
        self.assertIn("already marked", again)
        self.assertEqual(len(sent), 1)  # never twice

    def test_only_developers_can_close_a_request(self):
        a, sent = agent(rows(), developer=False)
        self.assertIn("Only the developers", a._mark_feature(MENTOR, {"ref": "aaaaaa"}))
        self.assertEqual(sent, [])

    def test_an_unknown_or_vague_ref_changes_nothing(self):
        data = rows()
        a, sent = agent(data)
        self.assertIn("couldn't tell which", a._mark_feature(MENTOR, {"ref": "zzzzzz"}))
        self.assertIn("couldn't tell which", a._mark_feature(MENTOR, {"ref": "a"}))
        self.assertFalse(data[0]["fact"].startswith("[implemented"))
        self.assertEqual(sent, [])

    def test_a_failed_dm_is_reported_not_hidden(self):
        data = rows()
        a, _ = agent(data)
        a.notify_user = lambda sid, text: (_ for _ in ()).throw(RuntimeError("no dm"))
        self.assertIn("couldn't DM", a._mark_feature(MENTOR, {"ref": "bbbbbb"}))

    def test_the_list_shows_refs_to_mentors_and_the_status(self):
        data = rows()
        a, _ = agent(data)
        a._mark_feature(MENTOR, {"ref": "aaaaaa"})
        listing = a._run_calls(MENTOR, [NS(id="c", function=NS(name="list_feature_requests", arguments="{}"))], {"meetings": []}, set())[0]
        self.assertIn("[aaaaaa]", listing)
        self.assertIn("✅ implemented", listing)
        founder_view = a._run_calls({**FOUNDER, "slack_id": "USAM"}, [NS(id="c", function=NS(name="list_feature_requests", arguments="{}"))], {"meetings": []}, set())[0]
        self.assertNotIn("[bbbbbb]", founder_view)  # refs are for mentors

    def test_only_mentors_are_offered_the_tool(self):
        names = lambda role: {t["function"]["name"] for t in build_tools(role)}  # noqa: E731
        self.assertIn("mark_feature_implemented", names("mentor"))
        self.assertNotIn("mark_feature_implemented", names("founder"))

    def test_a_request_marked_done_is_parsed_back(self):
        data = rows()
        personal.mark_implemented(MemSB(data), "bbbbbb")
        listed = {r["by"]: r for r in personal.list_requests(MemSB(data))}
        self.assertTrue(listed["Sam Lee"]["done"])
        self.assertEqual(listed["Sam Lee"]["text"], "Dark mode")
        self.assertFalse(listed["Leung Wai-Leng"]["done"])


if __name__ == "__main__":
    unittest.main()
