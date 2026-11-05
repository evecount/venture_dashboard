import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import meetings as m  # noqa: E402
import slack_bot as b  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_calendar_extras as tce  # noqa: E402

ev = tce.ev

MEET = "https://meet.google.com/abc-defg-hij"


class LocationHelperTests(unittest.TestCase):
    def test_where_an_event_is(self):
        self.assertEqual(m.event_where({"location": MEET}), "Google Meet")
        self.assertEqual(m.event_where({"hangoutLink": MEET}), "Google Meet")
        self.assertEqual(m.event_where({"location": "111 Somerset"}), "111 Somerset")
        self.assertEqual(m.event_where({}), "")

    def test_in_person_drops_the_stale_meet_link(self):
        e = {"location": MEET, "description": f"Requested by Ben through VentureOS. Join: {MEET}", "conferenceData": {"x": 1}}
        self.assertEqual(m.location_patch(e, "111 Somerset", None),
                         {"location": "111 Somerset", "description": "Requested by Ben through VentureOS.", "conferenceData": None})

    def test_online_adds_the_new_link(self):
        e = {"location": "Cafe", "description": "Requested by Ben through VentureOS."}
        self.assertEqual(m.location_patch(e, "virtual", MEET),
                         {"location": MEET, "description": f"Requested by Ben through VentureOS. Join: {MEET}"})


class AgentLocationTests(tce.AgentChangeTests):
    def test_change_location_is_a_proposal_with_old_and_new_place(self):
        out, _ = self.run_agent(self.MENTOR, {"title": "sprint", "action": "change_location", "new_where": "111 Somerset"}, [ev()])
        p = out["meeting"]
        self.assertEqual((p["action"], p["new_where"]), ("change_location", "111 Somerset"))
        self.assertNotIn("new", p)

    def test_change_location_needs_a_place(self):
        out, _ = self.run_agent(self.MENTOR, {"title": "sprint", "action": "change_location"}, [ev()])
        self.assertIsNone(out["meeting"])
        self.assertIn("Where should it move", out["text"])

    def test_reschedule_can_change_the_place_too(self):
        out, _ = self.run_agent(self.MENTOR, {"title": "sprint", "action": "reschedule", "new_date": "2099-10-16",
                                              "new_start_time": "16:00", "new_where": "virtual"}, [ev()])
        p = out["meeting"]
        self.assertIn("4:00 PM", p["new"])
        self.assertEqual(p["new_where"], "virtual")

    test_mentor_reschedule_becomes_a_proposal_with_old_and_new_times = None
    test_cancel_is_a_proposal_too = None
    test_founder_cannot_change_someone_elses_meeting = None
    test_ambiguous_titles_ask_which_one = None


class CardAndConfirmTests(unittest.TestCase):
    PAYLOAD = {"kind": "change", "action": "change_location", "event_id": "evt1", "title": "Sprint", "old": "Thu 3 PM",
               "old_where": "Google Meet", "new_where": "111 Somerset", "requester_slack": "UMENTOR01", "attendee_count": 3}

    def test_card_shows_the_place_change(self):
        text = b.build_meeting_card({**self.PAYLOAD, "id": "mtg-1"})[0]["text"]["text"]
        self.assertIn("change the place of", text)
        self.assertIn("*111 Somerset*", text)

    def test_confirm_patches_the_place_and_notifies(self):
        gcal = mock.Mock()
        gcal.get_event.return_value = {"location": MEET, "description": f"Requested. Join: {MEET}"}
        mem = mock.Mock()
        mem.get_meeting.return_value = {"id": "mtg-1", "payload": self.PAYLOAD, "requested_by": "UMENTOR01"}
        mem.claim_meeting.return_value = True
        client = mock.Mock()
        with mock.patch.object(b, "gcal", gcal), mock.patch.object(b, "memory", mem), \
                mock.patch.object(b, "studio_row", return_value={"refresh_token": "s"}), \
                mock.patch.object(b, "get_role", return_value="mentor"):
            b.handle_confirm_meeting(lambda: None, {"user": {"id": "UMENTOR01"}, "actions": [{"value": "mtg-1"}],
                                                    "channel": {"id": "D1"}, "message": {"ts": "1"}}, client)
        gcal.update_event.assert_called_once_with("s", "evt1", {"location": "111 Somerset", "description": "Requested."})
