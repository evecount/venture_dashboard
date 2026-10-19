import json
import os
import sys
import unittest
from datetime import date
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import syllabus_import as s  # noqa: E402

WEEKS = [
    {"week": 1, "sprint": 1, "title": "Founder thesis", "start": "2026-10-19", "end": "2026-10-25",
     "notes": "", "milestones": ["1-page venture thesis", "Top 10 risk assumptions ranked", "Outreach list of 20+ compliance officers"]},
    {"week": 2, "sprint": 1, "title": "Concept selection", "start": "2026-10-26", "end": "2026-11-01", "notes": "Course A", "milestones": ["8-12 discovery conversations"]},
]


class Table:
    def __init__(self, db, name):
        self.db, self.name, self.op, self.filters, self.payload = db, name, None, {}, None

    def insert(self, p): self.op, self.payload = "insert", p; return self
    def delete(self): self.op = "delete"; return self
    def eq(self, k, v): self.filters[k] = v; return self

    def execute(self):
        rows = self.db.rows.setdefault(self.name, [])
        if self.op == "insert":
            items = self.payload if isinstance(self.payload, list) else [self.payload]
            new = [{**i, "id": f"{self.name}-{len(rows) + n}"} for n, i in enumerate(items)]
            rows.extend(new)
            return NS(data=new)
        if self.op == "delete":
            keep = [r for r in rows if not all(r.get(k) == v for k, v in self.filters.items())]
            self.db.rows[self.name] = keep
            return NS(data=[])
        return NS(data=[])


class FakeDb:
    def __init__(self): self.rows = {}
    def table(self, n): return Table(self, n)


class PlanTests(unittest.TestCase):
    def test_everything_new_is_added_one_milestone_per_week(self):
        plan = s.plan_import(WEEKS, [])
        self.assertEqual([a["due"] for a in plan["add"]], ["2026-10-25", "2026-11-01"])
        self.assertEqual(len(plan["add"][0]["goals"]), 3)
        self.assertEqual(plan["add"][1]["title"], "Week 2 (Sprint 1): Concept selection (Course A)")

    def test_existing_milestones_win_over_matching_syllabus_items(self):
        existing = [{"title": "Rank top 10 risk assumptions", "status": "open", "goals": []},
                    {"title": "Customer discovery", "status": "open", "goals": [{"title": "Run 8-12 discovery conversations"}]}]
        plan = s.plan_import(WEEKS, existing)
        self.assertEqual(plan["add"][0]["goals"], ["1-page venture thesis", "Outreach list of 20+ compliance officers"])
        self.assertEqual(plan["skipped_weeks"], ["Week 2 (Sprint 1): Concept selection (Course A)"])  # its only item was covered
        self.assertEqual({c["by"] for c in plan["covered"]}, {"Rank top 10 risk assumptions", "Customer discovery"})

    def test_dropped_milestones_do_not_block_and_reimport_is_idempotent(self):
        plan = s.plan_import(WEEKS, [{"title": "Rank top 10 risk assumptions", "status": "dropped", "goals": []}])
        self.assertEqual(len(plan["add"][0]["goals"]), 3)
        have = [{"title": a["title"], "status": "open", "goals": [{"title": g} for g in a["goals"]]} for a in plan["add"]]
        again = s.plan_import(WEEKS, have)
        self.assertEqual((again["add"], len(again["have"])), ([], 2))

    def test_replace_only_removes_untouched_syllabus_milestones(self):
        imported = {"id": "a", "title": "Week 1 (Sprint 1): Founder thesis", "status": "open", "goals": [{"title": "x", "done": False}]}
        started = {"id": "b", "title": "Week 2 (Sprint 1): Concept selection", "status": "open", "goals": [{"title": "y", "done": True}]}
        manual = {"id": "c", "title": "Launch the waitlist", "status": "open", "goals": []}
        self.assertEqual([m["id"] for m in s.removable([imported, started, manual])], ["a"])


class SupersedeTests(unittest.TestCase):
    def test_new_milestone_replaces_overlapping_syllabus_goal_and_empty_week(self):
        db = FakeDb()
        s.load_existing = lambda sb, sid: [
            {"id": "m1", "title": "Week 2 (Sprint 1): Concept selection", "status": "open", "goals": [{"title": "8-12 discovery conversations", "done": False}]},
            {"id": "m2", "title": "Week 1 (Sprint 1): Founder thesis", "status": "open",
             "goals": [{"title": "1-page venture thesis", "done": False}, {"title": "Top 10 risk assumptions ranked", "done": False}]},
            {"id": "m3", "title": "Mine", "status": "open", "goals": [{"title": "Run 10 discovery conversations", "done": False}]}]
        db.rows = {"milestones": [{"id": "m1"}, {"id": "m2"}, {"id": "m3"}], "goals": [
            {"milestone_id": "m1", "title": "8-12 discovery conversations"}, {"milestone_id": "m2", "title": "1-page venture thesis"},
            {"milestone_id": "m2", "title": "Top 10 risk assumptions ranked"}, {"milestone_id": "m3", "title": "Run 10 discovery conversations"}]}
        gone = s.supersede(db, "st", "new", ["Discovery conversations with 8-12 compliance officers"])
        self.assertEqual(gone, ["8-12 discovery conversations"])
        self.assertEqual([m["id"] for m in db.rows["milestones"]], ["m2", "m3"])  # the emptied syllabus week went; the person's own stayed


class ReadingTests(unittest.TestCase):
    def test_clean_and_extract(self):
        raw = json.dumps({"participant": "Adrian Lin Daoqin", "company": "Adrish Holdings", "venture": "GRC Nexus", "weeks": [
            {"week": 2, "sprint": 1, "title": "B", "end": "2026-11-01", "milestones": ["x; "]},
            {"week": 1, "sprint": "1", "title": "A", "start": "2026-10-19", "end": "2026-10-25", "milestones": ["y"]},
            {"week": 3, "title": "no date"}]})
        http = lambda *a, **k: NS(json=lambda: {"candidates": [{"content": {"parts": [{"text": "```json\n" + raw + "\n```"}]}}]})
        spec = s.extract(b"%PDF", {"mimetype": "application/pdf"}, "k", "m", date(2026, 10, 19), http)
        self.assertEqual([w["week"] for w in spec["weeks"]], [1, 2])
        self.assertEqual(spec["weeks"][1]["start"], "2026-10-26")
        with self.assertRaises(ValueError):
            s.clean({"weeks": []})

    def test_startup_matching(self):
        founders = [{"name": "Adrian Lin", "startup_id": "grc"}, {"name": "Matthew Lee", "startup_id": "so"}]
        startups = [{"id": "grc", "name": "GRC Nexus"}, {"id": "so", "name": "SharedOut"}]
        self.assertEqual(s.match_startups({"participant": "Adrian Lin Daoqin"}, "", founders, startups), ["grc"])
        self.assertEqual(s.match_startups({"venture": "SharedOut"}, "", [], startups), ["so"])
        self.assertEqual(s.match_startups({}, "this is Matthew's syllabus", founders, startups), ["so"])
        self.assertEqual(s.match_startups({}, "here you go", founders, startups), [])

    def test_triggers(self):
        pdf = {"mimetype": "application/pdf", "name": "Adrian - MVP Syllabus.pdf"}
        self.assertTrue(s.looks_like_syllabus(pdf, ""))
        self.assertFalse(s.looks_like_syllabus({"mimetype": "application/pdf", "name": "invoice.pdf"}, "here"))
        self.assertTrue(s.looks_like_syllabus({"mimetype": "application/pdf", "name": "x.pdf"}, "his syllabus"))
        self.assertTrue(s.wants_replace("please replace the old syllabus"))
        self.assertFalse(s.wants_replace("here is his syllabus"))


if __name__ == "__main__":
    unittest.main()
