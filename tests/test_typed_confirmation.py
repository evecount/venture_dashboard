"""Answering a confirmation card by typing "yes" / "confirmed" (what Adrian did), instead of pressing its button.
Before: the assistant replied "✅ Meeting updated" while nothing had been created."""
import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot_agent  # noqa: E402
import slack_bot as b  # noqa: E402

CARD_NOTE = "Here's the meeting I'll create.\n[A confirmation card for 'MVP round off' was shown. It is NOT done until the person presses its button or replies yes.]"


class Say:
    def __init__(self):
        self.said = []

    def __call__(self, text="", **kw):
        self.said.append(text)
        return {"channel": "D1", "ts": "9.9"}


def row(title="MVP round off", kind=None, rid="r1"):
    payload = {"title": title, **({"kind": kind} if kind else {})}
    return {"id": rid, "requested_by": "U1", "payload": payload, "created_at": "2026-11-16T05:30:00+00:00"}


class PatternTests(unittest.TestCase):
    def test_plain_confirmations_and_refusals_are_recognised(self):
        for text in ("yes", "Yes!", "confirmed", "Confirm", "go ahead", "ok", "Yes please", "looks good", "send it", "  yep.  ", "yes, thanks",
                     "Yes that's good thanks", "yes that looks good, send it", "perfect thanks", "ok great"):
            self.assertTrue(b.is_confirmation(text), text)
        for text in ("no", "cancel", "never mind", "don't send", "Nope!", "no thanks", "no don't send it"):
            self.assertTrue(b.is_cancellation(text), text)

    def test_answers_with_content_are_not_treated_as_confirmations(self):
        for text in ("yes virtual, google meeting", "yes but make it 11am", "ok add Gwen too", "no, make it Thursday", "confirm the time is 10am?",
                     "yes and invite Sam", "sure, move it to Friday", "yes what time is it?"):
            self.assertFalse(b.is_confirmation(text) or b.is_cancellation(text), text)


class FalseReceiptTests(unittest.TestCase):
    def test_a_reply_that_opens_like_a_receipt_with_nothing_done_is_caught(self):
        for text in ("✅ Sent to everyone.", "Done — I've sent it.", "I've scheduled the meeting for 10am.", "📣 Sent!", "Sent to everyone."):
            self.assertTrue(bot_agent.CLAIMS_DONE.search(text), text)
        for text in ("Here are your tasks.", "Should I send it?", "Your meeting is at 10am.", "I can send it once you confirm."):
            self.assertFalse(bot_agent.CLAIMS_DONE.search(text), text)

    def test_the_agent_replaces_an_unbacked_claim_with_an_honest_line(self):
        from test_agent_loop import Script, agent_with
        from test_bot_agent import FOUNDER
        a, _ = agent_with(Script(("✅ Sent to everyone.", [])))
        out = a.respond(FOUNDER, "Yes that's good thanks")
        self.assertIn("haven't done that", out["text"])
        self.assertNotIn("Sent to everyone", out["text"])


class ConfirmByTextTests(unittest.TestCase):
    def setUp(self):
        b._waiting_checkins.clear()
        b._waiting_renames.clear()

    def run_it(self, text, history, rows):
        say = Say()
        with mock.patch.object(b.memory, "history", return_value=history), mock.patch.object(b.memory, "pending_for", return_value=rows), \
                mock.patch.object(b, "handle_confirm_meeting") as confirm, mock.patch.object(b.memory, "delete_meeting") as delete, \
                mock.patch.object(b, "app", mock.MagicMock()):
            handled = b.confirm_by_text("U1", text, say)
        return handled, say, confirm, delete

    CARD = [{"role": "user", "content": "set a meeting"}, {"role": "assistant", "content": CARD_NOTE}]

    def test_a_typed_yes_confirms_the_waiting_card_through_the_normal_confirm_path(self):
        handled, say, confirm, _ = self.run_it("confirmed", self.CARD, [row()])
        self.assertTrue(handled)
        confirm.assert_called_once()
        body = confirm.call_args.args[1]
        self.assertEqual((body["actions"][0]["value"], body["user"]["id"], body["message"]["ts"]), ("r1", "U1", "9.9"))

    def test_a_typed_no_cancels_it_and_nothing_is_sent(self):
        handled, say, confirm, delete = self.run_it("no", self.CARD, [row()])
        self.assertTrue(handled)
        delete.assert_called_once_with("r1")
        confirm.assert_not_called()
        self.assertIn("cancelled", say.said[0])

    def test_a_yes_that_is_not_about_a_card_goes_to_the_assistant(self):
        no_card = [{"role": "assistant", "content": "Should I invite Gwen too?"}]
        handled, _, confirm, _ = self.run_it("yes", no_card, [row()])  # an old proposal must not be confirmed by an unrelated yes
        self.assertFalse(handled)
        confirm.assert_not_called()

    def test_nothing_waiting_means_the_assistant_handles_it(self):
        handled, _, confirm, _ = self.run_it("yes", self.CARD, [])
        self.assertFalse(handled)
        confirm.assert_not_called()

    def test_several_waiting_proposals_are_listed_not_guessed(self):
        handled, say, confirm, _ = self.run_it("yes", self.CARD, [row("One", rid="a"), row("Two", rid="b")])
        self.assertTrue(handled)
        confirm.assert_not_called()
        self.assertIn("2 proposals", say.said[0])

    def test_a_typed_yes_confirms_a_syllabus_card_once_a_startup_is_chosen(self):
        r = row(kind="syllabus")
        r["payload"]["startup_id"] = "s1"
        handled, _, confirm, _ = self.run_it("yes", self.CARD, [r])
        self.assertTrue(handled)
        confirm.assert_called_once()

    def test_a_syllabus_card_without_a_startup_asks_for_the_dropdown(self):
        r = row(kind="syllabus")
        r["payload"]["startup_id"] = None
        handled, say, confirm, _ = self.run_it("yes", self.CARD, [r])
        self.assertTrue(handled)
        confirm.assert_not_called()
        self.assertIn("dropdown", say.said[0])

    def test_a_typed_no_cancels_a_syllabus_import(self):
        handled, say, _, delete = self.run_it("no", self.CARD, [row(kind="syllabus")])
        self.assertTrue(handled)
        delete.assert_called_once_with("r1")
        self.assertIn("Nothing was changed", say.said[0])


class CheckinTypedConfirmTests(unittest.TestCase):
    CTX = {"founder_id": "f1", "name": "Ann Lee", "startup_id": "s1", "startup_name": "Auvira", "stream": "GTM", "lead": "Unassigned",
           "deliverable": {"id": "del-wk03", "week": "WK 03", "title": "Interview insight repo", "due_date": "2026-10-16"}}
    PARSED = {"status": "On Track", "progress": 50, "blocker": "None", "digest": "Built the login page", "stream": "Product"}
    CARD = [{"role": "assistant", "content": "Here's what I captured.\n[A confirmation card for a check-in was shown. It is NOT saved until the founder presses Save or replies yes.]"}]

    def setUp(self):
        b._waiting_checkins.clear()
        b._saved_cards.clear()
        self.blocks = b.build_confirmation_card(self.CTX, self.PARSED, "I built the login page")
        b.remember_checkin("U1", self.blocks, {"channel": "D1", "ts": "5.5"})

    def tearDown(self):
        b._waiting_checkins.clear()

    def run_it(self, text, history=None, rows=()):
        say = Say()
        app = mock.MagicMock()
        with mock.patch.object(b.memory, "history", return_value=history or self.CARD), mock.patch.object(b.memory, "pending_for", return_value=list(rows)),                 mock.patch.object(b, "commit_checkin", return_value=True) as commit, mock.patch.object(b, "owns_checkin", return_value=True),                 mock.patch.object(b, "estimate_after_checkin"), mock.patch.object(b, "publish_home"), mock.patch.object(b, "app", app):
            handled = b.confirm_by_text("U1", text, say)
        return handled, say, commit, app

    def test_the_card_contents_are_remembered_from_the_button_value(self):
        self.assertEqual(b._waiting_checkins["U1"]["value"]["digest"], "Built the login page")
        self.assertEqual(b._waiting_checkins["U1"]["ts"], "5.5")

    def test_a_typed_yes_saves_the_check_in_and_marks_the_card_saved(self):
        handled, _, commit, app = self.run_it("Yes that's good thanks")
        self.assertTrue(handled)
        commit.assert_called_once()
        self.assertEqual(commit.call_args.args[0]["digest"], "Built the login page")
        self.assertEqual(app.client.chat_update.call_args.kwargs["ts"], "5.5")
        self.assertNotIn("U1", b._waiting_checkins)

    def test_a_typed_yes_twice_saves_once(self):
        self.run_it("yes")
        handled, _, commit, _ = self.run_it("yes")
        self.assertFalse(handled)  # nothing waiting any more: the assistant answers
        commit.assert_not_called()

    def test_a_typed_no_saves_nothing(self):
        handled, say, commit, _ = self.run_it("no")
        self.assertTrue(handled)
        commit.assert_not_called()
        self.assertIn("won't save", say.said[0])
        self.assertNotIn("U1", b._waiting_checkins)

    def test_an_old_card_is_not_saved_by_a_late_yes(self):
        b._waiting_checkins["U1"]["at"] -= 3600
        handled, _, commit, _ = self.run_it("yes")
        self.assertFalse(handled)
        commit.assert_not_called()

    def test_a_check_in_and_a_meeting_waiting_together_are_listed_not_guessed(self):
        handled, say, commit, _ = self.run_it("yes", rows=[row()])
        self.assertTrue(handled)
        commit.assert_not_called()
        self.assertIn("2 proposals", say.said[0])

    def test_the_history_note_for_a_check_in_names_the_card(self):
        self.assertIn("confirmation card", bot_agent._card_note({"meetings": [], "checkin": None, "rename": {"x": 1}}))
        note = bot_agent._card_note({"meetings": [], "checkin": {"x": 1}, "rename": None})
        self.assertIn("confirmation card", note)
        self.assertIn("NOT saved", note)


class RenameTypedConfirmTests(unittest.TestCase):
    PROPOSAL = {"startup_id": "s1", "old_name": "Auvira", "new_name": "Auvira Labs"}
    CARD = [{"role": "assistant", "content": "Please confirm the rename below.\n[A confirmation card for a rename was shown. Nothing is renamed until they press Rename or reply yes.]"}]

    def setUp(self):
        b._waiting_checkins.clear()
        b._waiting_renames.clear()
        b._waiting_renames["U1"] = {"value": dict(self.PROPOSAL), "channel": "D1", "ts": "7.7", "at": time.time()}

    def tearDown(self):
        b._waiting_renames.clear()

    def run_it(self, text, role="mentor", rows=()):
        say, app, sb = Say(), mock.MagicMock(), mock.MagicMock()
        with mock.patch.object(b.memory, "history", return_value=self.CARD), mock.patch.object(b.memory, "pending_for", return_value=list(rows)),                 mock.patch.object(b, "get_role", return_value=role), mock.patch.object(b, "supabase", sb), mock.patch.object(b, "publish_home"),                 mock.patch.object(b, "app", app):
            handled = b.confirm_by_text("U1", text, say)
        return handled, say, app, sb

    def test_a_typed_yes_renames_and_updates_the_card(self):
        handled, _, app, sb = self.run_it("yes please")
        self.assertTrue(handled)
        sb.table.return_value.update.assert_called_once_with({"name": "Auvira Labs"})
        self.assertIn("Renamed", app.client.chat_update.call_args.kwargs["text"])
        self.assertEqual(app.client.chat_update.call_args.kwargs["ts"], "7.7")
        self.assertNotIn("U1", b._waiting_renames)

    def test_a_typed_no_renames_nothing(self):
        handled, say, _, sb = self.run_it("no")
        self.assertTrue(handled)
        sb.table.return_value.update.assert_not_called()
        self.assertIn("won't rename", say.said[0])

    def test_a_founder_still_cannot_rename_someone_elses_startup_by_typing_yes(self):
        _, _, app, sb = self.run_it("yes", role="founder")
        sb.table.return_value.update.assert_not_called()
        self.assertIn("can't rename", app.client.chat_update.call_args.kwargs["text"])

    def test_a_rename_and_a_meeting_waiting_together_are_listed(self):
        handled, say, _, sb = self.run_it("yes", rows=[row()])
        self.assertTrue(handled)
        sb.table.return_value.update.assert_not_called()
        self.assertIn("2 proposals", say.said[0])


class EmptyAnswerTests(unittest.TestCase):
    def test_a_model_that_says_nothing_is_asked_again(self):
        from test_agent_loop import Script, agent_with
        from test_bot_agent import FOUNDER
        s = Script(("", []), ("Which day do you mean?", []))
        a, _ = agent_with(s)
        out = a.respond(FOUNDER, "set a meeting tomorrow at 4.30pm")
        self.assertEqual(len(s.requests), 2)
        self.assertEqual(out["text"], "Which day do you mean?")

    def test_still_nothing_is_not_reported_as_got_it(self):
        from test_agent_loop import Script, agent_with
        from test_bot_agent import FOUNDER
        a, _ = agent_with(Script(("", []), ("", [])))
        out = a.respond(FOUNDER, "set a meeting tomorrow")
        self.assertNotEqual(out["text"], "Got it.")
        self.assertIn("couldn't act on that", out["text"])


class HistoryNoteTests(unittest.TestCase):
    def test_the_history_says_a_card_is_waiting_so_the_model_cannot_claim_it_was_done(self):
        note = bot_agent._card_note({"meetings": [{"title": "MVP round off"}], "checkin": None, "rename": None})
        self.assertIn("confirmation card for 'MVP round off'", note)
        self.assertIn("NOT done", note)
        self.assertEqual(bot_agent._card_note({"meetings": [], "checkin": None, "rename": None}), "")
        self.assertIn("NOT saved", bot_agent._card_note({"meetings": [], "checkin": {"x": 1}, "rename": None}))

    def test_a_card_with_no_words_gets_an_honest_default_reply(self):
        from test_agent_loop import Script, agent_with, call
        from test_bot_agent import FOUNDER
        s = Script(("", [call("schedule_meeting", {"title": "Sync", "date": "2099-01-01", "start_time": "10:00", "where": "virtual", "attendees": ["Sam"]})]))
        a, mem = agent_with(s)
        a.studio_connected = lambda: True
        out = a.respond(FOUNDER, "set up a sync")
        if out["meetings"]:
            self.assertIn("press its button", out["text"])
        logged = [c for r, c in mem.log_rows if r == "assistant"][-1]
        self.assertEqual("confirmation card" in logged, bool(out["meetings"]))


if __name__ == "__main__":
    unittest.main()
