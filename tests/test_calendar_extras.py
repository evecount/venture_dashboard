import json
import os
import sys
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import google_calendar as g  # noqa: E402
import meetings as m  # noqa: E402
from bot_agent import Agent  # noqa: E402


def ev(eid="evt1", title="Fortnightly sprint", start="2026-10-15T15:00:00+08:00", end="2026-10-15T16:00:00+08:00",
       requester="UREQ00001", attendees=None):
    return {"id": eid, "summary": title, "start": {"dateTime": start}, "end": {"dateTime": end},
            "extendedProperties": {"private": {"ventureos": "1", "requester": requester}},
            "attendees": attendees if attendees is not None else [
                {"email": "studio@x.io", "self": True, "organizer": True, "responseStatus": "accepted"},
                {"email": "a@x.io", "responseStatus": "accepted"}, {"email": "b@x.io", "responseStatus": "declined"},
                {"email": "c@x.io", "responseStatus": "needsAction"}]}


class HelperTests(unittest.TestCase):
    def test_rsvp_summary_counts_everyone_but_the_organiser(self):
        self.assertEqual(m.rsvp_summary(ev()), "✅ 1 yes · ❌ 1 no · ⏳ 1 waiting")

    def test_find_events_by_partial_title(self):
        events = [ev(title="Fortnightly sprint"), ev("e2", "Office hours")]
        self.assertEqual([e["id"] for e in m.find_events(events, "SPRINT")], ["evt1"])
        self.assertEqual(len(m.find_events(events, "")), 2)

    def test_only_mentors_or_the_requester_can_change_a_meeting(self):
        e = ev(requester="UREQ00001")
        self.assertTrue(m.can_change(e, "UREQ00001", False))
        self.assertFalse(m.can_change(e, "UOTHER001", False))
        self.assertTrue(m.can_change(e, "UOTHER001", True))

    def test_overlap_and_reminder_window(self):
        e = ev()
        b, en = m.parse_when("2026-10-15", "15:30", 60)
        self.assertTrue(m.overlaps(b, en, e))
        b2, e2 = m.parse_when("2026-10-15", "16:00", 60)
        self.assertFalse(m.overlaps(b2, e2, e))                         # back-to-back is not an overlap
        at_1400 = datetime(2026, 10, 15, 6, 0, tzinfo=timezone.utc)     # 2:00 PM SGT = 60 min before
        self.assertTrue(m.reminder_due(e, at_1400))
        self.assertFalse(m.reminder_due(e, datetime(2026, 10, 15, 3, 0, tzinfo=timezone.utc)))  # 3 hours before
        self.assertFalse(m.reminder_due(e, datetime(2026, 10, 15, 8, 0, tzinfo=timezone.utc)))  # already started

    def test_events_carry_the_requester_for_later_permission_checks(self):
        b, e = m.parse_when("2026-10-16", "15:00")
        body = m.build_event_body("T", b, e, "virtual", [], "d", None, "UREQ00001")
        self.assertEqual(body["extendedProperties"]["private"], {"ventureos": "1", "requester": "UREQ00001"})


class GoogleTests(unittest.TestCase):
    def test_meet_code_is_extracted(self):
        self.assertEqual(g.meet_code("https://meet.google.com/abc-defg-hij?authuser=0"), "abc-defg-hij")
        self.assertIsNone(g.meet_code("https://example.com"))
        self.assertIsNone(g.meet_code(None))

    def test_open_meet_patches_access_type_to_open(self):
        calls = []

        def http(method, url, headers=None, data=None, params=None, json=None):
            if url == g.TOKEN_URL:
                return {"access_token": "at"}
            calls.append((method, url, params, json))
            return {}

        gc = g.GoogleCalendar("c", "s", "https://x/cb", "k", http=http)
        self.assertTrue(gc.open_meet(g.encrypt_token("r", "k"), "abc-defg-hij"))
        method, url, params, body = calls[0]
        self.assertEqual((method, url.endswith("spaces/abc-defg-hij"), params, body),
                         ("PATCH", True, {"updateMask": "config.accessType"}, {"config": {"accessType": "OPEN"}}))

    def test_open_meet_reports_failure_when_permission_is_missing(self):
        def http(method, url, headers=None, data=None, params=None, json=None):
            if url == g.TOKEN_URL:
                return {"access_token": "at"}
            raise RuntimeError("403 insufficient scope")

        gc = g.GoogleCalendar("c", "s", "https://x/cb", "k", http=http)
        self.assertFalse(gc.open_meet(g.encrypt_token("r", "k"), "abc-defg-hij"))

    def test_open_meet_rooms_are_created_with_open_access_and_attached_as_the_location(self):
        seen = {}

        def http(method, url, headers=None, data=None, params=None, json=None):
            if url == g.TOKEN_URL:
                return {"access_token": "at"}
            seen.update(method=method, url=url, body=json)
            return {"meetingUri": "https://meet.google.com/abc-defg-hij"}

        gc = g.GoogleCalendar("c", "s", "https://x/cb", "k", http=http)
        link = gc.create_open_meet(g.encrypt_token("r", "k"))
        self.assertEqual((link, seen["method"], seen["body"]), ("https://meet.google.com/abc-defg-hij", "POST", {"config": {"accessType": "OPEN"}}))
        b, e = m.parse_when("2026-10-16", "15:00")
        body = m.build_event_body("T", b, e, "virtual", [], "d", meet_link=link)
        self.assertEqual(body["location"], link)
        self.assertNotIn("conferenceData", body)            # we attach our own room instead of letting Calendar make one
        self.assertIn(link, body["description"])
        self.assertIn("conferenceData", m.build_event_body("T", b, e, "virtual", [], "d"))   # fallback unchanged

    def test_creating_an_open_room_fails_softly_without_the_permission(self):
        def http(method, url, headers=None, data=None, params=None, json=None):
            if url == g.TOKEN_URL:
                return {"access_token": "at"}
            raise RuntimeError("403 insufficient scope")

        self.assertIsNone(g.GoogleCalendar("c", "s", "https://x/cb", "k", http=http).create_open_meet(g.encrypt_token("r", "k")))

    def test_meet_links_in_the_location_are_shown_as_google_meet(self):
        e = ev()
        e["location"] = "https://meet.google.com/abc-defg-hij"
        self.assertIn("(Google Meet)", m.describe_event(e, False))

    def test_studio_connection_asks_for_the_meet_settings_scope(self):
        url = g.connect_url("c", "https://x/cb", "k", "U1", "s", studio=True)
        self.assertIn("meetings.space.settings", url)
        self.assertIn("meetings.space.created", url)
        self.assertNotIn("meetings.space.settings", g.connect_url("c", "https://x/cb", "k", "f", "s"))

    def test_update_and_delete_notify_attendees(self):
        seen = []

        def http(method, url, headers=None, data=None, params=None, json=None):
            if url == g.TOKEN_URL:
                return {"access_token": "at"}
            seen.append((method, params))
            return {}

        gc = g.GoogleCalendar("c", "s", "https://x/cb", "k", http=http)
        enc = g.encrypt_token("r", "k")
        gc.update_event(enc, "evt1", {"start": {}})
        gc.delete_event(enc, "evt1")
        self.assertEqual(seen, [("PATCH", {"sendUpdates": "all"}), ("DELETE", {"sendUpdates": "all"})])


class Q:
    def __init__(self, data):
        self.data = data

    def __getattr__(self, _):
        return lambda *a, **k: self

    def execute(self):
        return NS(data=self.data)


class SB:
    def table(self, name):
        return Q({"founders": [{"name": "Ann", "email": "a@x.io", "slack_user_id": "UANN00001"}],
                  "mentors": [{"name": "Mo", "email": "mo@x.io", "slack_user_id": "UMENTOR01"}]}.get(name, []))


class Mem:
    def __init__(self):
        self.saved = []

    def history(self, *_):
        return []

    def log(self, *_):
        pass

    def save_meeting(self, who, payload):
        self.saved.append(payload)
        return "mtg-1"

    def __getattr__(self, _):
        return lambda *a, **k: []


def ai(call):
    msg = NS(content="", tool_calls=[NS(function=NS(name=call[0], arguments=json.dumps(call[1])))])
    return NS(chat=NS(completions=NS(create=lambda **kw: NS(choices=[NS(message=msg)]))))


class AgentChangeTests(unittest.TestCase):
    def run_agent(self, ident, args, events):
        mem = Mem()
        agent = Agent(ai(("change_meeting", args)), "m", SB(), mem, studio_events=lambda days: events,
                      studio_connected=lambda: True)
        return agent.respond(ident, "move it"), mem

    MENTOR = {"role": "mentor", "slack_id": "UMENTOR01", "name": "Mo"}
    FOUNDER = {"role": "founder", "slack_id": "UANN00001", "name": "Ann",
               "context": {"founder_id": "f", "startup_id": "s", "startup_name": "S", "name": "Ann", "stream": "GTM", "lead": "x", "deliverable": {}}}

    def test_mentor_reschedule_becomes_a_proposal_with_old_and_new_times(self):
        out, mem = self.run_agent(self.MENTOR, {"title": "sprint", "action": "reschedule", "new_date": "2099-10-16", "new_start_time": "16:00"}, [ev()])
        p = out["meeting"]
        self.assertEqual((p["kind"], p["action"], p["event_id"]), ("change", "reschedule", "evt1"))
        self.assertIn("3:00 PM", p["old"])
        self.assertIn("4:00 PM", p["new"])

    def test_cancel_is_a_proposal_too(self):
        out, _ = self.run_agent(self.MENTOR, {"title": "sprint", "action": "cancel"}, [ev()])
        self.assertEqual(out["meeting"]["action"], "cancel")
        self.assertEqual(out["meeting"]["attendee_count"], 3)

    def test_founder_cannot_change_someone_elses_meeting(self):
        out, _ = self.run_agent(self.FOUNDER, {"title": "sprint", "action": "cancel"}, [ev(requester="UOTHER001")])
        self.assertIsNone(out["meeting"])
        self.assertIn("only a mentor", out["text"])

    def test_ambiguous_titles_ask_which_one(self):
        out, _ = self.run_agent(self.MENTOR, {"title": "sprint", "action": "cancel"}, [ev(), ev("e2", "Sprint review")])
        self.assertIsNone(out["meeting"])
        self.assertIn("Which one", out["text"])


if __name__ == "__main__":
    unittest.main()
