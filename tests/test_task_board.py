"""The task board: To do / In progress / Done on the founder's Home tab and in the assistant's task tools."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import slack_bot as b  # noqa: E402
from test_assistant_tools import Mem, agent  # noqa: E402
from test_bot_agent import FOUNDER  # noqa: E402


def task(i, title, status="open", owner=None):
    return {"id": f"t{i}aaaaaa", "startup_id": "startup-auvira", "owner_slack_id": owner, "title": title, "due_date": None, "status": status,
            "startups": {"name": "Auvira"}}


def text_of(blocks):
    return "\n".join(bl["text"]["text"] for bl in blocks if bl.get("type") == "section")


class HomeBoardTests(unittest.TestCase):
    def test_three_columns_with_counts(self):
        blocks = b.build_task_blocks([task(1, "Write pricing page"), task(2, "Call Sam", "doing"), task(3, "Draft deck")],
                                     [{"title": "Ship login", "status": "done", "due_date": None}])
        text = text_of(blocks)
        self.assertIn("📋 To do* (2)", text)
        self.assertIn("🔧 In progress* (1)", text)
        self.assertIn("✅ Done this week* (1)", text)
        self.assertLess(text.index("Write pricing page"), text.index("Call Sam"))
        self.assertLess(text.index("Call Sam"), text.index("Ship login"))

    def test_an_empty_board_shows_nothing(self):
        self.assertEqual(b.build_task_blocks([], []), [])

    def test_only_finished_work_still_shows_the_board(self):
        text = text_of(b.build_task_blocks([], [{"title": "Ship login", "status": "done"}]))
        self.assertIn("Nothing waiting.", text)
        self.assertIn("Ship login", text)

    def test_a_long_column_is_cut_and_stays_within_slacks_limit(self):
        blocks = b.build_task_blocks([task(i, "x" * 300) for i in range(30)], [])
        for bl in blocks:
            if bl.get("type") == "section":
                self.assertLess(len(bl["text"]["text"]), 3000)
        self.assertIn("and 24 more", text_of(blocks))

    def test_the_home_view_includes_the_board(self):
        ctx = {"founder_id": "f1", "startup_id": "s1", "startup_name": "Auvira", "name": "Sam", "stream": "GTM", "lead": "X",
               "deliverable": {"id": "d", "week": "WK 01", "title": "T", "due_date": "2026-11-20"}}
        view = b.build_home_view(ctx, None, [task(1, "Write pricing page", "doing")], [], [], [], done_tasks=[{"title": "Ship login"}])
        text = "\n".join(bl.get("text", {}).get("text", "") for bl in view["blocks"] if bl.get("type") in ("section", "header"))
        self.assertIn("Task board", text)
        self.assertIn("Write pricing page", text)
        self.assertIn("Ship login", text)


class MovingTasksTests(unittest.TestCase):
    def setUp(self):
        self.a, self.mem = agent()
        self.mem.task_rows = [task(1, "Write pricing page")]

    def move(self, status):
        return self.a._update_task(FOUNDER, {"task_ref": "t1aaaa", "status": status})

    def test_start_moves_it_to_in_progress(self):
        out = self.move("doing")
        self.assertEqual(self.mem.updated[-1], ("t1aaaaaa", {"status": "doing", "completed_at": None}))
        self.assertIn("moved to In progress", out)

    def test_done_stamps_the_completion_time(self):
        out = self.move("done")
        patch = self.mem.updated[-1][1]
        self.assertEqual(patch["status"], "done")
        self.assertTrue(patch["completed_at"])
        self.assertIn("moved to Done", out)

    def test_back_to_to_do_clears_the_time(self):
        self.move("todo")
        self.assertEqual(self.mem.updated[-1][1], {"status": "open", "completed_at": None})

    def test_a_database_without_the_new_status_gives_an_honest_failure(self):
        self.mem.update_task = lambda task_id, patch: False
        self.assertIn("task-status update", self.move("doing"))

    def test_the_list_marks_what_is_in_progress(self):
        self.mem.task_rows = [task(1, "Write pricing page", "doing"), task(2, "Call Sam")]
        listing = self.a._list_tasks(FOUNDER, {})
        self.assertIn("in progress", listing.split("Call Sam")[0])
        self.assertNotIn("in progress", listing.split("Call Sam")[1])

    def test_the_tool_offers_the_three_stages(self):
        from bot_agent import build_tools
        spec = next(t for t in build_tools("founder") if t["function"]["name"] == "update_task")
        self.assertEqual(spec["function"]["parameters"]["properties"]["status"]["enum"], ["todo", "doing", "done"])


class MemoryTests(unittest.TestCase):
    def test_done_tasks_hide_a_mentors_private_follow_ups(self):
        import bot_memory
        rows = [{"id": "1", "owner_slack_id": None, "title": "Shared", "status": "done"},
                {"id": "2", "owner_slack_id": "UMENTOR", "title": "Private", "status": "done"}]
        mem = bot_memory.Memory.__new__(bot_memory.Memory)
        mem._guard = lambda name, fn, default: rows if name == "done_tasks" else default  # founders table lookup -> no team
        got = mem._founder_visible(rows, "s1")
        self.assertEqual([t["title"] for t in got], ["Shared"])


if __name__ == "__main__":
    unittest.main()
