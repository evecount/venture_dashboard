import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import announce  # noqa: E402
import profile_rules  # noqa: E402
import progress_estimator as pe  # noqa: E402
import slack_bot as b  # noqa: E402
from bot_memory import Memory  # noqa: E402


class AnnounceMatchTests(unittest.TestCase):
    pool = [{"name": "Thomas Lee", "slack_user_id": "U00000001", "startups": {"name": "A"}},
            {"name": "Mo Salah", "slack_user_id": "U00000002", "startups": {"name": "B"}},
            {"name": "Monica Ray", "slack_user_id": "U00000003", "startups": {"name": "C"}}]

    def test_first_name_picks_one_person_not_every_substring(self):
        got = announce.resolve_recipients(["Mo"], self.pool, [], "U99999999")
        self.assertEqual([p["name"] for p in got["people"]], ["Mo Salah"])

    def test_ambiguous_partial_name_sends_to_nobody(self):
        got = announce.resolve_recipients(["Mon"], self.pool + [{"name": "Monty P", "slack_user_id": "U00000004"}], [], "U99999999")
        self.assertEqual(got["people"], [])
        self.assertIn("which one", got["unknown"][0])


class ClaimRuleTests(unittest.TestCase):
    def test_typed_email_cannot_claim_an_invite_by_name(self):
        invited = {"name": "Priya Rao", "email": None, "slack_user_id": None}
        self.assertEqual(profile_rules.match_person([invited], [invited], "Priya Rao", "x@y.com", False)[0], "duplicate")
        self.assertEqual(profile_rules.match_person([invited], [invited], "Priya Rao", "x@y.com", True)[0], "claim")


class EstimatorCursorTests(unittest.TestCase):
    def test_window_of_unmonitored_signals_advances_the_cursor(self):
        sb = mock.MagicMock()
        rows = [{"id": 1, "type": "commit", "headline": "h", "detail": "", "meta": {"repo": "other/x"}, "created_at": "2026-10-01T00:00:00+00:00"}]
        sb.table.return_value.select.return_value.eq.return_value.in_.return_value.gt.return_value.order.return_value.limit.return_value.execute.return_value.data = rows
        with mock.patch.object(pe.integrations, "monitored_for_startup", return_value={"mine/y"}):
            work, cursor = pe._monitored_work(sb, "s", "2026-09-01")
        self.assertEqual((work, cursor), ([], "2026-10-01T00:00:00+00:00"))


class TaskPrivacyTests(unittest.TestCase):
    def test_founders_do_not_see_mentor_owned_tasks(self):
        mem = Memory(mock.MagicMock())
        tasks = [{"id": "1", "owner_slack_id": None}, {"id": "2", "owner_slack_id": "UMENTOR"}, {"id": "3", "owner_slack_id": "UFOUNDER"}]
        with mock.patch.object(Memory, "open_tasks", return_value=tasks):
            mem.sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [{"slack_user_id": "UFOUNDER"}]
            self.assertEqual([t["id"] for t in mem.founder_tasks("s")], ["1", "3"])


class MeetingCardTests(unittest.TestCase):
    def body(self, user):
        return {"actions": [{"value": "m1"}], "user": {"id": user}, "channel": {"id": "C"}, "message": {"ts": "1"}}

    def test_only_the_requester_can_cancel_a_card(self):
        client = mock.MagicMock()
        with mock.patch.object(b.memory, "get_meeting", return_value={"requested_by": "UA"}), \
                mock.patch.object(b.memory, "delete_meeting") as delete:
            b.handle_cancel_meeting(lambda: None, self.body("UB"), client)
            delete.assert_not_called()
            b.handle_cancel_meeting(lambda: None, self.body("UA"), client)
            delete.assert_called_once()

    def test_second_click_on_an_announcement_sends_nothing(self):
        client = mock.MagicMock()
        row = {"id": "m1", "requested_by": "UA", "payload": {"kind": "announce", "requester_slack": "UA", "requester": "A",
                                                              "message": "hi", "recipients": [{"name": "X", "slack": "U1"}]}}
        with mock.patch.object(b.memory, "get_meeting", return_value=row), mock.patch.object(b, "get_role", return_value="mentor"), \
                mock.patch.object(b.memory, "claim_meeting", return_value=False):
            b.handle_confirm_meeting(lambda: None, self.body("UA"), client)
        client.chat_postMessage.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class DirectAnnounceTests(unittest.TestCase):
    def test_few_named_people_are_sent_directly_but_groups_keep_the_card(self):
        two = [{"name": "A"}, {"name": "B"}]
        self.assertTrue(announce.is_direct(["Wai-Leng"], two[:1]))
        self.assertTrue(announce.is_direct(["Ann", "Bo"], two))
        self.assertFalse(announce.is_direct(["everyone"], two))
        self.assertFalse(announce.is_direct(["Founders"], two))
        self.assertFalse(announce.is_direct(["Ann"], [{"name": str(i)} for i in range(6)]))
        self.assertFalse(announce.is_direct(["Ann"], []))

    def test_send_announcement_reports_the_outcome(self):
        client = mock.MagicMock()
        m = {"requester": "Ben", "message": "hi", "recipients": [{"name": "Wai-Leng", "slack": "U1"}], "unreachable": [], "unknown": []}
        self.assertEqual(b.send_announcement(client, m), "✅ Sent to Wai-Leng.")
        client.chat_postMessage.side_effect = RuntimeError("nope")
        self.assertIn("Couldn't reach: Wai-Leng", b.send_announcement(client, m))

    def test_claim_survives_a_database_error(self):
        sb = mock.MagicMock()
        sb.table.return_value.delete.return_value.eq.return_value.execute.side_effect = RuntimeError("disconnected")
        self.assertTrue(Memory(sb).claim_meeting("m1"))


class MilestoneSyncTests(unittest.TestCase):
    def memory(self, status, goals):
        sb = mock.MagicMock()
        sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"status": status, "goals": [{"done": d} for d in goals]}]
        return Memory(sb), sb

    def test_last_goal_ticked_completes_the_milestone(self):
        mem, sb = self.memory("open", [True, True])
        self.assertEqual(mem.sync_milestone("m1"), "done")
        self.assertEqual(sb.table.return_value.update.call_args[0][0]["status"], "done")

    def test_new_or_unticked_goal_reopens_it(self):
        mem, _ = self.memory("done", [True, False])
        self.assertEqual(mem.sync_milestone("m1"), "open")

    def test_nothing_changes_when_status_already_matches_or_dropped_or_no_goals(self):
        for status, goals in (("open", [True, False]), ("done", [True]), ("dropped", [True]), ("open", [])):
            mem, sb = self.memory(status, goals)
            self.assertIsNone(mem.sync_milestone("m1"))
            sb.table.return_value.update.assert_not_called()


class OutsideGuestTests(unittest.TestCase):
    import meetings as _m
    founders = [{"name": "Takshma Patel", "email": "t@x.com", "slack_user_id": "U1"}]
    mentors = [{"name": "Ben Lim", "email": "ben@x.com", "slack_user_id": "U2"}]

    def resolve(self, specs, role="mentor", known=None):
        return self._m.resolve_attendees(specs, self.founders, self.mentors, "U2", role, known)

    def test_name_plus_email_from_the_conversation_invites_the_outside_guest(self):
        known = self._m.emails_in("James email is <mailto:james@mambapartners.com|james@mambapartners.com>")
        got = self.resolve(["takshma", "James"], known=known)
        self.assertEqual(got["missing"], [])
        self.assertIn("james@mambapartners.com", [p["email"] for p in got["people"]])

    def test_an_email_spec_is_invited_directly_for_mentors_only(self):
        self.assertEqual([p["email"] for p in self.resolve(["james@mambapartners.com"])["people"]], ["james@mambapartners.com"])
        got = self.resolve(["james@mambapartners.com"], role="founder")
        self.assertEqual(got["people"], [])
        self.assertTrue(got["missing"])

    def test_unknown_name_without_a_matching_email_stays_missing(self):
        self.assertEqual(self.resolve(["Zed"], known=["james@x.com"])["missing"], ["Zed"])
