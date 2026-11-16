"""Answering a confirmation card by typing "yes" / "confirmed" (what Adrian did), instead of pressing its button.
Before: the assistant replied "✅ Meeting updated" while nothing had been created."""
import os
import sys
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
        for text in ("yes", "Yes!", "confirmed", "Confirm", "go ahead", "ok", "Yes please", "looks good", "send it", "  yep.  ", "yes, thanks"):
            self.assertTrue(b.CONFIRM_RE.match(text), text)
        for text in ("no", "cancel", "never mind", "don't send", "Nope!"):
            self.assertTrue(b.CANCEL_RE.match(text), text)

    def test_answers_with_content_are_not_treated_as_confirmations(self):
        for text in ("yes virtual, google meeting", "yes but make it 11am", "ok add Gwen too", "no, make it Thursday", "confirm the time is 10am?"):
            self.assertFalse(b.CONFIRM_RE.match(text) or b.CANCEL_RE.match(text), text)


class ConfirmByTextTests(unittest.TestCase):
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

    def test_syllabus_cards_still_need_their_button(self):
        handled, _, confirm, _ = self.run_it("yes", self.CARD, [row(kind="syllabus")])
        self.assertFalse(handled)
        confirm.assert_not_called()


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
