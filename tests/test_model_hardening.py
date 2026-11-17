"""A model that talks instead of acting, an alert when the model has to be retried or replaced, and the intent check behind both."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot_agent  # noqa: E402
import llm_client  # noqa: E402
from test_agent_loop import Script, agent_with, call  # noqa: E402
from test_bot_agent import MENTOR  # noqa: E402


class IntentTests(unittest.TestCase):
    def test_requests_to_do_something_are_recognised(self):
        for text in ("Set a meeting tomorrow with Matt, James and Arthur at 4.30pm virtual", "can u set a meeting with adrian and gwen at 10am tmr",
                     "remind me on Friday to send the deck", "Add a task for Auvira: chase pricing", "schedule a call with Sam", "save a note on Auvira",
                     "please cancel the sync on Thursday", "announce that I'm away Monday"):
            self.assertTrue(bot_agent.wants_action(text), text)

    def test_questions_and_chat_are_not(self):
        for text in ("what meeting do I have tomorrow?", "did you set the meeting?", "thanks!", "how are the founders doing", "Which tasks are open?",
                     "have you added the note", "who is on the call"):
            self.assertFalse(bot_agent.wants_action(text), text)


class TalkedButDidNothingTests(unittest.TestCase):
    ASK = "Set a meeting tomorrow with Sam at 4.30pm virtual"

    def test_a_reply_with_no_action_is_asked_again_and_the_second_answer_is_used(self):
        alerts, skipped = [], []
        card = call("add_note", {"startup_id": "startup-auvira", "note": "x"})
        s = Script(("Sure, I'll set that up.", []), ("", [card]))
        a, mem = agent_with(s)
        a.alert = lambda key, text: alerts.append((key, text))
        a.ai.skip_primary = lambda: skipped.append(1)
        out = a.respond(MENTOR, self.ASK)
        self.assertEqual(len(s.requests), 2)
        self.assertEqual(skipped, [1])
        self.assertEqual(len(mem.notes), 1)  # the second model acted
        self.assertEqual(alerts[0][0], "model-retry")
        self.assertIn("no action", alerts[0][1])
        self.assertNotIn("Nothing has been created", out["text"])

    def test_if_it_still_only_talks_the_reply_says_nothing_was_done(self):
        s = Script(("Sure, I'll set that up.", []), ("Okay, I'll arrange that.", []))
        a, _ = agent_with(s)
        out = a.respond(MENTOR, self.ASK)
        self.assertIn("Nothing has been created or changed yet", out["text"])

    def test_a_clarifying_question_is_left_alone(self):
        s = Script(("Which day do you mean?", []))
        a, _ = agent_with(s)
        out = a.respond(MENTOR, self.ASK)
        self.assertEqual(len(s.requests), 1)  # a question is a legitimate answer: no retry
        self.assertEqual(out["text"], "Which day do you mean?")

    def test_ordinary_chat_is_not_retried_or_annotated(self):
        s = Script(("You're welcome!", []))
        a, _ = agent_with(s)
        out = a.respond(MENTOR, "thanks!")
        self.assertEqual((len(s.requests), out["text"]), (1, "You're welcome!"))

    def test_an_empty_answer_also_alerts(self):
        alerts = []
        s = Script(("", []), ("Which day?", []))
        a, _ = agent_with(s)
        a.alert = lambda key, text: alerts.append(text)
        a.respond(MENTOR, self.ASK)
        self.assertIn("empty answer", alerts[0])


class AlertTests(unittest.TestCase):
    def test_the_developer_dm_is_sent_once_an_hour_per_kind(self):
        import slack_bot as b
        from unittest import mock
        b._alert_last.clear()
        with mock.patch.object(b, "notify_developers") as notify, mock.patch.object(b.time, "time", side_effect=[10000.0, 10100.0, 14000.0, 14001.0]):
            b.alert_developers_once("k", "one")
            b.alert_developers_once("k", "two")      # within the hour: dropped
            b.alert_developers_once("k", "three")    # an hour later: sent
            b.alert_developers_once("other", "four")  # a different kind: sent
        self.assertEqual([c.args[0] for c in notify.call_args_list], ["one", "three", "four"])

    def test_a_failing_dm_never_breaks_the_caller(self):
        import slack_bot as b
        from unittest import mock
        b._alert_last.clear()
        with mock.patch.object(b, "notify_developers", side_effect=RuntimeError("no developer on Slack")):
            b.alert_developers_once("k", "x")

    def test_the_fallback_wrapper_reports_why_it_switched_and_survives_a_broken_notifier(self):
        seen = []

        class Down:
            chat = type("C", (), {"completions": type("D", (), {"create": staticmethod(lambda **kw: (_ for _ in ()).throw(ConnectionError("tailscale down")))})})()

        class Up:
            chat = type("C", (), {"completions": type("D", (), {"create": staticmethod(lambda **kw: "ok")})})()

        w = llm_client.WithFallback(Down(), Up(), "m", notify=lambda why: seen.append(why))
        self.assertEqual(w.create(model="x"), "ok")
        self.assertIn("tailscale down", seen[0])

        def boom(why):
            raise RuntimeError("alert failed")
        w2 = llm_client.WithFallback(Down(), Up(), "m", notify=boom)
        self.assertEqual(w2.create(model="x"), "ok")


if __name__ == "__main__":
    unittest.main()
