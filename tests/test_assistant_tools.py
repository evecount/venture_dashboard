"""New assistant tools: tasks, notes, catch-ups, reminders and check-in fixes. Run: python -m unittest discover tests"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot_agent  # noqa: E402
import slack_bot as b  # noqa: E402
from bot_agent import Agent, build_tools  # noqa: E402
from test_bot_agent import FOUNDER, MENTOR, STARTUPS, FakeMemory, FakeSB, fake_ai  # noqa: E402

SGT = timezone(timedelta(hours=8))


class Mem(FakeMemory):
    """FakeMemory with the tasks/notes/reminders the new tools read and write."""

    def __init__(self):
        super().__init__()
        self.task_rows, self.note_rows, self.reminders, self.updated, self.deleted = [], [], [], [], []
        self.reminder_ok = True

    def open_tasks(self, *_a, **_k):
        return list(self.task_rows)

    def founder_tasks(self, *_a, **_k):
        return [t for t in self.task_rows if not t.get("owner_slack_id") or t["owner_slack_id"] == "U1"]

    def update_task(self, task_id, patch):
        self.updated.append((task_id, patch))
        return True

    def notes_with_refs(self, startup_id=None, limit=15):
        return list(self.note_rows)

    def update_note(self, note_id, body):
        self.updated.append((note_id, body))
        return True

    def delete_note(self, note_id):
        self.deleted.append(note_id)
        return True

    def my_reminders(self, slack_id, limit=20):
        return [r for r in self.reminders if r["slack_user_id"] == slack_id]

    def add_reminder(self, slack_id, text, iso):
        if self.reminder_ok:
            self.reminders.append({"id": f"{chr(97 + len(self.reminders))}rrrrrr", "slack_user_id": slack_id, "text": text, "remind_at": iso})
        return self.reminder_ok

    def cancel_reminder(self, slack_id, rid):
        self.deleted.append(rid)
        return True


def agent(tables=None, mem=None):
    mem = mem or Mem()
    return Agent(fake_ai([]), "m", FakeSB({"startups": STARTUPS, **(tables or {})}), mem), mem


class GatingTests(unittest.TestCase):
    def names(self, role):
        return {t["function"]["name"] for t in build_tools(role)}

    def test_everyone_gets_the_shared_tools_and_each_role_only_its_own(self):
        shared = {"list_tasks", "update_task", "whats_new", "remind_me", "list_reminders", "cancel_reminder"}
        self.assertTrue(shared <= self.names("founder") and shared <= self.names("mentor"))
        self.assertTrue({"list_notes", "edit_note", "delete_note"} <= self.names("mentor"))
        self.assertTrue({"list_notes", "edit_note", "delete_note"}.isdisjoint(self.names("founder")))
        self.assertIn("fix_checkin", self.names("founder"))
        self.assertNotIn("fix_checkin", self.names("mentor"))

    def test_a_founder_cannot_run_mentor_note_tools_even_if_the_model_tries(self):
        a, mem = agent()
        mem.note_rows = [{"id": "nnnnnnaa", "author_slack_id": "U1", "author_name": "Sam", "body": "x", "created_at": "2026-11-01", "startups": {"name": "S"}}]
        self.assertEqual(a._run_tool(FOUNDER, "delete_note", {"note_ref": "nnnnnn"}, {}), "")
        self.assertEqual(mem.deleted, [])


class TaskToolTests(unittest.TestCase):
    def setUp(self):
        self.a, self.mem = agent()
        self.mem.task_rows = [
            {"id": "t1aaaaaa", "startup_id": "startup-auvira", "title": "Send deck", "due_date": "2026-11-20", "owner_slack_id": None, "startups": {"name": "Auvira"}},
            {"id": "t2bbbbbb", "startup_id": "startup-auvira", "title": "Mentor private", "due_date": None, "owner_slack_id": "UM", "startups": {"name": "Auvira"}},
            {"id": "t3cccccc", "startup_id": "startup-auvira", "title": "Other mentor's", "due_date": None, "owner_slack_id": "UOTHER", "startups": {"name": "Auvira"}},
        ]

    def test_founders_list_only_what_they_may_see_and_mentors_see_all_with_owners(self):
        founder = self.a._list_tasks(FOUNDER, {})
        self.assertIn("Send deck", founder)
        self.assertNotIn("Mentor private", founder)
        mentor = self.a._list_tasks(MENTOR, {})
        self.assertIn("Mentor private", mentor)
        self.assertIn("for you", mentor)
        self.assertIn("someone else", mentor)

    def test_private_follow_ups_never_appear_in_a_channel(self):
        text = self.a._list_tasks({**MENTOR, "in_channel": True}, {})
        self.assertIn("Send deck", text)
        self.assertNotIn("Mentor private", text)

    def test_update_changes_title_due_date_and_owner(self):
        out = self.a._update_task(FOUNDER, {"task_ref": "t1aaaa", "title": "Send the deck", "due_date": "2026-11-25", "assignee": "me"})
        self.assertIn("Task updated", out)
        self.assertEqual(self.mem.updated[-1], ("t1aaaaaa", {"title": "Send the deck", "due_date": "2026-11-25", "owner_slack_id": "U1"}))
        self.a._update_task(FOUNDER, {"task_ref": "t1aaaa", "clear_due_date": True})
        self.assertEqual(self.mem.updated[-1][1], {"due_date": None})

    def test_bad_input_is_refused_without_touching_anything(self):
        self.assertIn("couldn't find", self.a._update_task(FOUNDER, {"task_ref": "t2bbbb", "title": "x"}))  # a mentor's private task
        self.assertIn("couldn't read that date", self.a._update_task(FOUNDER, {"task_ref": "t1aaaa", "due_date": "soon"}))
        self.assertIn("What should I change", self.a._update_task(FOUNDER, {"task_ref": "t1aaaa"}))
        self.assertEqual(self.mem.updated, [])

    def test_a_mentor_cannot_change_another_mentors_private_follow_up(self):
        self.assertIn("belongs to someone else", self.a._update_task(MENTOR, {"task_ref": "t3cccc", "title": "x"}))
        self.assertEqual(self.mem.updated, [])


class NoteToolTests(unittest.TestCase):
    def setUp(self):
        self.a, self.mem = agent()
        self.mem.note_rows = [
            {"id": "n1aaaaaa", "author_slack_id": "UM", "author_name": "Mo", "body": "Needs a technical review", "created_at": "2026-11-01T00:00:00", "startups": {"name": "Auvira"}},
            {"id": "n2bbbbbb", "author_slack_id": "UOTHER", "author_name": "Gwen", "body": "Pricing unclear", "created_at": "2026-11-02T00:00:00", "startups": {"name": "Auvira"}},
        ]

    def test_list_shows_refs_and_marks_your_own(self):
        text = self.a._notes_tool(MENTOR, "list_notes", {})
        self.assertIn("[n1aaaa]", text)
        self.assertIn("(you)", text)

    def test_only_the_author_can_edit_or_delete(self):
        self.assertIn("only they can change it", self.a._notes_tool(MENTOR, "edit_note", {"note_ref": "n2bbbb", "note": "x"}))
        self.assertIn("only they can change it", self.a._notes_tool(MENTOR, "delete_note", {"note_ref": "n2bbbb"}))
        self.assertEqual((self.mem.updated, self.mem.deleted), ([], []))
        self.assertIn("Note updated", self.a._notes_tool(MENTOR, "edit_note", {"note_ref": "n1aaaa", "note": "Reviewed"}))
        self.assertIn("Deleted your note", self.a._notes_tool(MENTOR, "delete_note", {"note_ref": "n1aaaa"}))
        self.assertEqual(self.mem.deleted, ["n1aaaaaa"])

    def test_notes_are_never_listed_or_changed_in_a_channel(self):
        for name, args in (("list_notes", {}), ("edit_note", {"note_ref": "n1aaaa", "note": "x"}), ("delete_note", {"note_ref": "n1aaaa"})):
            self.assertIn("private", self.a._notes_tool({**MENTOR, "in_channel": True}, name, args))
        self.assertEqual((self.mem.updated, self.mem.deleted), ([], []))


class ReminderToolTests(unittest.TestCase):
    def setUp(self):
        self.a, self.mem = agent()

    def future(self, hours=26):
        t = datetime.now(SGT) + timedelta(hours=hours)
        return t.strftime("%Y-%m-%d"), t.strftime("%H:%M")

    def test_a_future_reminder_is_stored_in_utc_and_confirmed_in_singapore_time(self):
        d, t = self.future()
        out = self.a._remind_me(FOUNDER, {"text": "send the deck", "date": d, "time": t})
        self.assertIn("I'll remind you", out)
        self.assertIn("(SGT)", out)
        stored = datetime.fromisoformat(self.mem.reminders[0]["remind_at"])
        self.assertEqual(stored.utcoffset(), timedelta(0))
        self.assertAlmostEqual((stored - datetime.now(timezone.utc)).total_seconds() / 3600, 26, delta=0.1)

    def test_past_far_future_and_garbled_times_are_refused(self):
        self.assertIn("already passed", self.a._remind_me(FOUNDER, {"text": "x", "date": "2020-01-01", "time": "09:00"}))
        far = (datetime.now(SGT) + timedelta(days=400)).strftime("%Y-%m-%d")
        self.assertIn("more than a year", self.a._remind_me(FOUNDER, {"text": "x", "date": far, "time": "09:00"}))
        self.assertIn("valid date and time", self.a._remind_me(FOUNDER, {"text": "x", "date": "friday", "time": "3pm"}))
        self.assertIn("remind you about", self.a._remind_me(FOUNDER, {"text": " ", "date": far, "time": "09:00"}))
        self.assertEqual(self.mem.reminders, [])

    def test_a_missing_table_is_explained_and_the_limit_is_enforced(self):
        d, t = self.future()
        self.mem.reminder_ok = False
        self.assertIn("table needs creating", self.a._remind_me(FOUNDER, {"text": "x", "date": d, "time": t}))
        self.mem.reminder_ok = True
        self.mem.reminders = [{"id": f"r{i}", "slack_user_id": "U1", "text": "x", "remind_at": "2030-01-01T00:00:00+00:00"} for i in range(20)]
        self.assertIn("20 reminders", self.a._remind_me(FOUNDER, {"text": "x", "date": d, "time": t}))

    def test_people_only_see_and_cancel_their_own_reminders(self):
        d, t = self.future()
        self.a._remind_me(FOUNDER, {"text": "send the deck", "date": d, "time": t})
        self.a._remind_me(MENTOR, {"text": "mentor thing", "date": d, "time": t})
        listing = self.a._list_reminders(FOUNDER)
        self.assertIn("send the deck", listing)
        self.assertNotIn("mentor thing", listing)
        ref = self.mem.reminders[0]["id"][:6]
        self.assertIn("cancelled", self.a._cancel_reminder(FOUNDER, {"reminder_ref": ref}))
        self.assertIn("couldn't find", self.a._cancel_reminder(FOUNDER, {"reminder_ref": self.mem.reminders[1]["id"][:6]}))


class FixCheckinTests(unittest.TestCase):
    LAST = {"id": "s1", "status": "In progress", "progress": 40, "blocker": "None", "digest": "Built the form", "created_at": "2026-11-10T03:00:00+00:00"}

    def setUp(self):
        self.a, self.mem = agent({"submissions": [self.LAST]})

    def test_an_edit_becomes_a_confirm_card_with_before_and_after(self):
        out = {"meetings": [], "meeting": None}
        self.assertEqual(self.a._fix_checkin(FOUNDER, {"action": "edit", "status": "Blocked", "blocker": "API key", "progress": "30%"}, out), "")
        card = out["meetings"][0]
        self.assertEqual((card["kind"], card["action"], card["submission_id"]), ("checkin_fix", "edit", "s1"))
        self.assertEqual(card["new"], {"status": "Blocked", "blocker": "API key", "progress": 30})
        blocks = b.build_meeting_card(card)
        text = blocks[0]["text"]["text"]
        self.assertIn("Before", text)
        self.assertIn("After", text)
        self.assertEqual([e["action_id"] for e in blocks[1]["elements"]], ["confirm_meeting", "cancel_meeting"])

    def test_delete_asks_first_and_says_it_cannot_be_undone(self):
        out = {"meetings": [], "meeting": None}
        self.a._fix_checkin(FOUNDER, {"action": "delete"}, out)
        self.assertIn("can't be undone", b.build_meeting_card(out["meetings"][0])[0]["text"]["text"])

    def test_nothing_to_change_or_no_check_in_is_explained(self):
        self.assertIn("say instead", self.a._fix_checkin(FOUNDER, {"action": "edit"}, {"meetings": [], "meeting": None}))
        empty, _ = agent({"submissions": []})
        self.assertIn("don't have a saved check-in", empty._fix_checkin(FOUNDER, {"action": "delete"}, {"meetings": [], "meeting": None}))

    def card(self, action="edit"):
        return {"kind": "checkin_fix", "action": action, "submission_id": "s1", "startup_id": "startup-auvira", "founder_id": "f1",
                "old": {k: self.LAST[k] for k in ("status", "progress", "blocker", "digest")}, "new": {"status": "Blocked"},
                "when": "2026-11-10", "requester": "Sam", "requester_slack": "U1", "id": "m1"}

    def test_applying_changes_only_the_owners_own_check_in(self):
        sb = mock.MagicMock()
        sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [{"id": "s1", "founder_id": "f1"}]
        with mock.patch.object(b, "supabase", sb):
            self.assertIn("is updated", b.apply_checkin_fix(self.card("edit"), "U1"))
            self.assertIn("Deleted", b.apply_checkin_fix(self.card("delete"), "U1"))
        sb2 = mock.MagicMock()
        sb2.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [{"id": "s1", "founder_id": "someone-else"}]
        with mock.patch.object(b, "supabase", sb2):
            self.assertIn("nothing was changed", b.apply_checkin_fix(self.card("delete"), "U1"))
        sb2.table.return_value.delete.assert_not_called()

    def test_someone_else_pressing_confirm_changes_nothing(self):
        client = mock.MagicMock()
        row = {"id": "m1", "requested_by": "U1", "payload": self.card()}
        body = {"actions": [{"value": "m1"}], "user": {"id": "U1"}, "channel": {"id": "C"}, "message": {"ts": "1"}}
        with mock.patch.object(b.memory, "get_meeting", return_value=row), mock.patch.object(b, "owns_checkin", return_value=False), \
                mock.patch.object(b, "apply_checkin_fix") as apply:
            b.handle_confirm_meeting(lambda: None, body, client)
        apply.assert_not_called()
        client.chat_postEphemeral.assert_called_once()

    def test_the_owner_confirming_applies_it_once(self):
        client = mock.MagicMock()
        row = {"id": "m1", "requested_by": "U1", "payload": self.card()}
        body = {"actions": [{"value": "m1"}], "user": {"id": "U1"}, "channel": {"id": "C"}, "message": {"ts": "1"}}
        with mock.patch.object(b.memory, "get_meeting", return_value=row), mock.patch.object(b, "owns_checkin", return_value=True), \
                mock.patch.object(b.memory, "claim_meeting", side_effect=[True, False]), mock.patch.object(b, "publish_home"), \
                mock.patch.object(b, "apply_checkin_fix", return_value="done") as apply:
            b.handle_confirm_meeting(lambda: None, body, client)
            b.handle_confirm_meeting(lambda: None, body, client)  # a double click
        self.assertEqual(apply.call_count, 1)


class WhatsNewTests(unittest.TestCase):
    TABLES = {
        "submissions": [{"startup_id": "startup-auvira", "status": "Blocked", "progress": 30, "blocker": "API key", "digest": "Built the signup form",
                         "created_at": "2026-11-10T03:00:00+00:00"}],
        "goals": [{"title": "Create wireframe", "done_at": "2026-11-09T00:00:00+00:00", "milestones": {"startup_id": "startup-auvira"}},
                  {"title": "Someone else's goal", "done_at": "2026-11-09T00:00:00+00:00", "milestones": {"startup_id": "startup-other"}}],
        "tasks": [{"startup_id": "startup-auvira", "title": "Public task", "owner_slack_id": None, "completed_at": "2026-11-09"},
                  {"startup_id": "startup-auvira", "title": "Mentor private task", "owner_slack_id": "UM", "completed_at": "2026-11-09"}],
        "milestones": [{"startup_id": "startup-auvira", "title": "Landing page", "created_by_role": "mentor", "created_at": "2026-11-08"}],
        "founders": [{"slack_user_id": "U1"}],
    }

    def setUp(self):
        self.a, _ = agent(self.TABLES)

    def test_a_founder_catch_up_has_their_own_work_and_hides_mentors_private_tasks(self):
        text = self.a._whats_new(FOUNDER, {"days": 7})
        for want in ("Built the signup form", "API key", "Create wireframe", "Public task", "Landing page", "from a mentor"):
            self.assertIn(want, text)
        self.assertNotIn("Mentor private task", text)

    def test_private_follow_ups_stay_out_of_channel_replies(self):
        text = self.a._whats_new({**MENTOR, "in_channel": True}, {"startup": "Auvira"})
        self.assertIn("Public task", text)
        self.assertNotIn("Mentor private task", text)

    def test_a_bad_date_is_asked_about_and_an_empty_period_says_so(self):
        self.assertIn("couldn't read that date", self.a._whats_new(FOUNDER, {"since": "last monday"}))
        quiet, _ = agent({})
        self.assertIn("Nothing new", quiet._whats_new(FOUNDER, {}))


class ReminderSenderTests(unittest.TestCase):
    def run_sender(self, claim):
        client = mock.MagicMock()
        with mock.patch.object(b, "supabase", mock.MagicMock()), mock.patch.object(b, "SLACK_BOT_TOKEN", "x"), \
                mock.patch.object(b, "app", mock.MagicMock(client=client)), \
                mock.patch.object(b.memory, "due_reminders", return_value=[{"id": "r1", "slack_user_id": "U1", "text": "send the deck"}]), \
                mock.patch.object(b.memory, "claim_reminder", return_value=claim), mock.patch.object(b.memory, "log"):
            b.send_due_reminders()
        return client

    def test_a_due_reminder_is_sent_once_claimed(self):
        client = self.run_sender(True)
        self.assertIn("send the deck", client.chat_postMessage.call_args.kwargs["text"])

    def test_a_reminder_someone_else_already_claimed_is_not_sent_again(self):
        self.run_sender(False).chat_postMessage.assert_not_called()


class MemoryLayerTests(unittest.TestCase):
    def test_claiming_a_reminder_is_only_true_for_the_first_caller(self):
        from bot_memory import Memory
        sb = mock.MagicMock()
        q = sb.table.return_value.update.return_value.eq.return_value.is_.return_value
        q.execute.return_value.data = [{"id": "r1"}]
        self.assertTrue(Memory(sb).claim_reminder("r1", "2026-11-12T00:00:00+00:00"))
        q.execute.return_value.data = []
        self.assertFalse(Memory(sb).claim_reminder("r1", "2026-11-12T00:00:00+00:00"))


if __name__ == "__main__":
    unittest.main()
