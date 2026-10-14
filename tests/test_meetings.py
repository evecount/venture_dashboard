import json
import os
import sys
import unittest
from datetime import datetime
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import meetings as m  # noqa: E402
from bot_agent import Agent  # noqa: E402

MENTORS = [{"name": "Mo Mentor", "email": "mo@studio.com", "slack_user_id": "UMENTOR01"}]
FOUNDERS = [{"name": "Ann Founder", "email": "ann@a.io", "slack_user_id": "UANN00001"},
            {"name": "Bo Founder", "email": "bo@b.io", "slack_user_id": "UBO000001"},
            {"name": "Cy NoEmail", "email": None, "slack_user_id": "UCY000001"}]


class HelperTests(unittest.TestCase):
    def test_times_show_in_12_hour_format(self):
        begin, end = m.parse_when("2026-10-16", "15:00", 60)
        self.assertEqual(m.format_when(begin, end), "Friday, Oct 16 · 3:00 PM–4:00 PM (SGT)")
        b2, e2 = m.parse_when("2026-10-15", "09:30", 90)
        self.assertEqual(m.format_when(b2, e2), "Thursday, Oct 15 · 9:30 AM–11:00 AM (SGT)")
        self.assertEqual(m.time_12h(m.parse_when("2026-10-15", "00:05")[0]), "12:05 AM")

    def test_bad_input_is_rejected(self):
        self.assertIsNone(m.parse_when("not-a-date", "15:00"))
        self.assertIsNone(m.parse_when("2026-10-16", "25:99"))

    def test_mentor_can_invite_everyone_and_missing_emails_are_reported(self):
        got = m.resolve_attendees(["everyone"], FOUNDERS, MENTORS, "UMENTOR01", "mentor")
        self.assertEqual({p["email"] for p in got["people"]}, {"mo@studio.com", "ann@a.io", "bo@b.io"})
        self.assertEqual(got["missing"], ["Cy NoEmail"])

    def test_founders_cannot_call_everyone_but_can_name_people(self):
        self.assertIn("Only mentors", m.resolve_attendees(["everyone"], FOUNDERS, MENTORS, "UANN00001", "founder")["error"])
        got = m.resolve_attendees(["<@UMENTOR01>", "Bo"], FOUNDERS, MENTORS, "UANN00001", "founder")
        self.assertEqual({p["email"] for p in got["people"]}, {"mo@studio.com", "bo@b.io"})

    def test_ambiguous_or_unknown_people_are_flagged_not_guessed(self):
        both = FOUNDERS + [{"name": "Ann Other", "email": "ann2@x.io", "slack_user_id": "UANN00002"}]
        got = m.resolve_attendees(["Ann", "Zed"], both, MENTORS, "UMENTOR01", "mentor")
        self.assertEqual(got["people"], [])
        self.assertTrue(any("which one" in x for x in got["missing"]))
        self.assertIn("Zed", got["missing"])

    def test_event_body_virtual_gets_meet_link_and_place_does_not(self):
        begin, end = m.parse_when("2026-10-16", "15:00")
        att = [{"name": "A", "email": "a@x.io"}]
        online = m.build_event_body("Sprint", begin, end, "Virtually", att, "d", "fortnightly")
        self.assertIn("conferenceData", online)
        self.assertEqual(online["recurrence"], ["RRULE:FREQ=WEEKLY;INTERVAL=2"])
        place = m.build_event_body("Sprint", begin, end, "111 Somerset", att, "d")
        self.assertEqual(place["location"], "111 Somerset")
        self.assertNotIn("conferenceData", place)
        self.assertEqual(place["start"]["timeZone"], "Asia/Singapore")


class Q:
    def __init__(self, data):
        self.data = data

    def __getattr__(self, _):
        return lambda *a, **k: self

    def execute(self):
        return NS(data=self.data)


class SB:
    def table(self, name):
        return Q({"founders": FOUNDERS, "mentors": MENTORS}.get(name, []))


class Mem:
    def __init__(self):
        self.saved = []

    def history(self, *_):
        return []

    def log(self, *_):
        pass

    def save_meeting(self, who, payload):
        self.saved.append((who, payload))
        return "mtg-1"

    def __getattr__(self, name):
        return lambda *a, **k: []


def ai(call):
    msg = NS(content="", tool_calls=[NS(function=NS(name=call[0], arguments=json.dumps(call[1])))])
    return NS(chat=NS(completions=NS(create=lambda **kw: NS(choices=[NS(message=msg)]))))


class AgentMeetingTests(unittest.TestCase):
    ARGS = {"title": "Fortnightly sprint", "date": "2099-10-16", "start_time": "15:00", "where": "111 Somerset",
            "attendees": ["everyone"], "repeat": "fortnightly"}

    def run_agent(self, ident, args, connected=True):
        mem = Mem()
        agent = Agent(ai(("schedule_meeting", args)), "m", SB(), mem, studio_link=lambda s: "https://x", studio_connected=lambda: connected)
        return agent.respond(ident, "set up a meeting"), mem

    def test_mentor_request_becomes_a_proposal_never_an_event(self):
        out, mem = self.run_agent({"role": "mentor", "slack_id": "UMENTOR01", "name": "Mo Mentor"}, self.ARGS)
        self.assertEqual(out["meeting"]["id"], "mtg-1")
        self.assertEqual(len(out["meeting"]["attendees"]), 3)
        self.assertEqual(mem.saved[0][0], "UMENTOR01")

    def test_nothing_is_proposed_until_the_studio_calendar_is_connected(self):
        out, mem = self.run_agent({"role": "mentor", "slack_id": "UMENTOR01", "name": "Mo Mentor"}, self.ARGS, connected=False)
        self.assertIsNone(out["meeting"])
        self.assertIn("studio calendar", out["text"])

    def test_past_dates_and_founder_everyone_requests_are_refused(self):
        past = {**self.ARGS, "date": "2020-01-01"}
        out, _ = self.run_agent({"role": "mentor", "slack_id": "UMENTOR01", "name": "Mo"}, past)
        self.assertIsNone(out["meeting"])
        founder = {"role": "founder", "slack_id": "UANN00001", "name": "Ann Founder",
                   "context": {"founder_id": "f", "startup_id": "s", "startup_name": "S", "name": "Ann", "stream": "GTM", "lead": "x",
                               "deliverable": {}}}
        out, _ = self.run_agent(founder, self.ARGS)
        self.assertIsNone(out["meeting"])
        self.assertIn("Only mentors", out["text"])


class StudioEventTests(unittest.TestCase):
    EV = {"summary": "Fortnightly sprint", "start": {"dateTime": "2026-10-15T15:00:00+08:00"}, "end": {"dateTime": "2026-10-15T16:00:00+08:00"},
          "location": "111 Somerset", "attendees": [{"email": "ann@a.io", "displayName": "Ann Founder"}, {"email": "mo@studio.com", "self": True}]}

    def test_description_uses_12_hour_time_and_place(self):
        line = m.describe_event(self.EV, show_attendees=True)
        self.assertIn("Thu Oct 15, 3:00 PM–4:00 PM", line)
        self.assertIn("(111 Somerset)", line)
        self.assertIn("with Ann Founder", line)
        self.assertNotIn("with", m.describe_event(self.EV, show_attendees=False))

    def test_founders_only_see_meetings_they_are_invited_to(self):
        self.assertTrue(m.visible_to(self.EV, "ann@a.io", False))
        self.assertFalse(m.visible_to(self.EV, "bo@b.io", False))
        self.assertFalse(m.visible_to(self.EV, None, False))
        self.assertTrue(m.visible_to(self.EV, None, True))


class ComingUpTests(unittest.TestCase):
    def test_real_meetings_merge_with_the_schedule_in_order_with_12_hour_times(self):
        import mentor_home
        from datetime import date
        today = date(2026, 10, 14)
        ev = {"summary": "Fortnightly sprint", "location": "111 Somerset",
              "start": {"dateTime": "2026-10-15T15:00:00+08:00"}, "end": {"dateTime": "2026-10-15T16:00:00+08:00"}}
        lines = mentor_home.coming_up(today, [m.upcoming_item(ev, today)])
        text = chr(10).join(lines)
        self.assertIn("Tomorrow, 3:00 PM–4:00 PM: *Fortnightly sprint* · 111 Somerset", text)
        self.assertTrue(lines[0].startswith("🗓 Today"))          # today's office hours first
        self.assertLess(text.index("Tomorrow"), text.index("Fri Oct 16"))   # sprint before Friday's deliverable
        self.assertNotIn("(Mamba Program Lead)", text)             # no repeated role in double brackets

    def test_day_labels(self):
        from datetime import date
        self.assertEqual(m.day_label(date(2026, 10, 14), date(2026, 10, 14)), "Today")
        self.assertEqual(m.day_label(date(2026, 10, 15), date(2026, 10, 14)), "Tomorrow")
        self.assertEqual(m.day_label(date(2026, 10, 20), date(2026, 10, 14)), "Tue Oct 20")


if __name__ == "__main__":
    unittest.main()
