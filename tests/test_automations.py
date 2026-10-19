import unittest
from datetime import date, datetime, timedelta, timezone

import cohorts
import founder_nudges
import routines

SGT = timezone(timedelta(hours=8))
MVP1 = {"id": "sg-01", "name": "MVP#1", "start": date(2026, 10, 5), "weeks": 12, "startup_ids": ["a"], "emails": {"a@x.co"}}
MVP2 = {"id": "sg-02", "name": "MVP#2", "start": date(2026, 10, 19), "weeks": 12, "startup_ids": ["b"], "emails": {"b@x.co"}}
SPRINT_EVENT = {"title": "Fortnightly sprint", "starts_at": "2026-10-29T03:00:00+00:00", "location": "111 Somerset",
                "attendees": [{"email": "a@x.co"}, {"email": "mentor@x.co"}]}


class CohortTest(unittest.TestCase):
    def test_start_monday_from_timestamp_in_sgt(self):
        self.assertEqual(cohorts.start_monday("2026-10-18T16:00:00+00:00"), date(2026, 10, 19))  # midnight SGT
        self.assertEqual(cohorts.start_monday("2026-10-21"), date(2026, 10, 19))

    def test_weeks_and_sprint_thursdays(self):
        self.assertEqual(cohorts.week_of(MVP1["start"], date(2026, 10, 19)), 3)
        self.assertEqual(cohorts.week_of(MVP2["start"], date(2026, 10, 19)), 1)
        self.assertIsNone(cohorts.week_of(MVP2["start"], date(2026, 10, 18)))
        self.assertEqual([s["date"] for s in cohorts.sprint_sessions(MVP1["start"])][:3],
                         [date(2026, 10, 15), date(2026, 10, 29), date(2026, 11, 12)])
        self.assertEqual(cohorts.next_sprint(MVP2["start"], date(2026, 10, 19))["date"], date(2026, 10, 29))
        self.assertEqual(cohorts.next_sprint(MVP2["start"], date(2026, 10, 19))["sprint"], 1)

    def test_calendar_match_respects_who_is_invited(self):
        day = date(2026, 10, 29)
        hit = cohorts.calendar_match(day, [SPRINT_EVENT], MVP1["emails"])
        self.assertEqual(hit["where"], "111 Somerset")
        self.assertEqual(hit["begin"].hour, 11)
        self.assertIsNone(cohorts.calendar_match(day, [SPRINT_EVENT], MVP2["emails"]))  # MVP#2 isn't invited
        open_event = {**SPRINT_EVENT, "attendees": []}
        self.assertIsNotNone(cohorts.calendar_match(day, [open_event], MVP2["emails"]))  # studio-wide note counts

    def test_describe_session(self):
        s = cohorts.next_sprint(MVP1["start"], date(2026, 10, 19))
        self.assertEqual(cohorts.describe_session(s, cohorts.calendar_match(s["date"], [SPRINT_EVENT], MVP1["emails"])),
                         "Sprint 2 session: Thu 29 Oct, 11:00 AM at 111 Somerset")
        self.assertIn("not on the studio calendar", cohorts.describe_session(s, None))

    def test_deliverable_shifts_with_cohort(self):
        d1 = cohorts.this_weeks_deliverable(MVP1["start"], date(2026, 10, 21))
        d2 = cohorts.this_weeks_deliverable(MVP2["start"], date(2026, 10, 21))
        self.assertEqual((d1["week"], d2["week"]), (3, 1))
        self.assertEqual(d2["due"], date(2026, 10, 23))  # MVP#2's week-1 deliverable is due its own Friday


class NudgeTest(unittest.TestCase):
    founders = [{"id": "f1", "name": "Adrian Lin", "startup_id": "b", "slack_user_id": "U0AAAAAAAA1"},
                {"id": "f2", "name": "Takshma Patel", "startup_id": "a", "slack_user_id": "U0AAAAAAAA2"}]

    def test_plan_on_the_wednesday_before_a_sprint(self):
        got = founder_nudges.plan(self.founders, {"f2": {"github": True, "google": True}}, {"a": date(2026, 10, 27)},
                                  [MVP1, MVP2], [SPRINT_EVENT], date(2026, 10, 28))
        adrian, takshma = got["founders"]
        self.assertEqual(adrian["missing"], ["google", "github"])
        self.assertIn("Google Calendar and GitHub", adrian["text"])
        self.assertIn("haven't had a check-in", adrian["text"])
        self.assertIn("not on the studio calendar", adrian["text"])     # MVP#2's sprint isn't scheduled
        self.assertEqual(takshma["missing"], [])
        self.assertIn("How's the week going?", takshma["text"])
        self.assertIn("11:00 AM at 111 Somerset", takshma["text"])
        self.assertIn("MVP#2 Sprint 1 session", got["mentors_note"])  # mentors are told what's unscheduled

    def test_first_name(self):
        self.assertEqual(founder_nudges.first_name("Takshma Patel"), "Takshma")
        self.assertEqual(founder_nudges.first_name("Leung Wai-Leng"), "Leung Wai-Leng")

    def test_no_sprint_line_on_off_weeks(self):
        got = founder_nudges.plan(self.founders[:1], {}, {}, [MVP1, MVP2], [], date(2026, 10, 21))
        self.assertNotIn("Tomorrow", got["founders"][0]["text"])
        self.assertIsNone(got["mentors_note"])


class RoutineTest(unittest.TestCase):
    def row(self, **kw):
        r, err = routines.validate({"instruction": "Remind founders to connect GitHub until they do", "weekday": "wednesday",
                                    "time": "14:00", **kw})
        self.assertIsNone(err)
        return {**r, "id": "r1", "anchor_date": "2026-10-21"}

    def test_validate_rejects_missing_parts(self):
        self.assertIsNotNone(routines.validate({"instruction": "x", "weekday": "someday", "time": "14:00"})[1])
        self.assertIsNotNone(routines.validate({"instruction": "x", "weekday": "monday", "time": "2pm"})[1])
        self.assertIsNotNone(routines.validate({"instruction": "", "weekday": "monday", "time": "14:00"})[1])

    def test_due_window_and_last_run(self):
        r = self.row()
        at = datetime(2026, 10, 21, 14, 5, tzinfo=SGT)
        self.assertEqual(routines.due(r, at), datetime(2026, 10, 21, 14, 0, tzinfo=SGT))
        self.assertIsNone(routines.due(r, datetime(2026, 10, 21, 13, 59, tzinfo=SGT)))
        self.assertIsNone(routines.due(r, datetime(2026, 10, 21, 14, 31, tzinfo=SGT)))  # window passed
        self.assertIsNone(routines.due({**r, "last_run_at": "2026-10-21T06:00:00+00:00"}, at))  # already sent
        self.assertIsNone(routines.due({**r, "active": False}, at))

    def test_fortnightly_skips_alternate_weeks(self):
        r = self.row(every_weeks=2)
        self.assertIsNotNone(routines.due(r, datetime(2026, 10, 21, 14, 1, tzinfo=SGT)))
        self.assertIsNone(routines.due(r, datetime(2026, 10, 28, 14, 1, tzinfo=SGT)))
        self.assertIsNotNone(routines.due(r, datetime(2026, 11, 4, 14, 1, tzinfo=SGT)))

    def test_first_run(self):
        r = self.row()
        self.assertEqual(routines.first_run(r, datetime(2026, 10, 19, 12, 0, tzinfo=SGT)), date(2026, 10, 21))
        self.assertEqual(routines.first_run(r, datetime(2026, 10, 21, 15, 0, tzinfo=SGT)), date(2026, 10, 28))

    def test_describe(self):
        self.assertTrue(routines.describe(self.row()).startswith("every Wednesday at 2:00 PM → all founders (written for each person)"))


class LookupAnswerTest(unittest.TestCase):
    """A reply that only used look-up tools gets a second pass that reasons over the results."""

    def make(self, first_tool):
        from types import SimpleNamespace as NS
        from bot_agent import Agent

        calls = []

        class Completions:
            def create(self, **kw):
                calls.append(kw)
                if len(calls) == 1:
                    call = NS(id="c1", function=NS(name=first_tool, arguments="{}"))
                    return NS(choices=[NS(message=NS(content="", tool_calls=[call]))])
                return NS(choices=[NS(message=NS(content="MVP#2's first sprint isn't on the calendar yet.", tool_calls=None))])

        class Mem:
            def history(self, _): return []
            def log(self, *a): pass

        agent = Agent(NS(chat=NS(completions=Completions())), "m", None, memory=Mem())
        agent._system = lambda ident: "system"
        agent._run_tool = lambda ident, name, args, out: "RAW CALENDAR DUMP"
        return agent, calls

    def test_lookup_gets_a_reasoned_answer(self):
        agent, calls = self.make("upcoming_meetings")
        out = agent.respond({"role": "mentor", "slack_id": "U1", "name": "Ben"}, "any sprint gaps?")
        self.assertEqual(out["text"], "MVP#2's first sprint isn't on the calendar yet.")
        self.assertEqual(calls[1]["messages"][-1], {"role": "tool", "tool_call_id": "c1", "content": "RAW CALENDAR DUMP"})
        self.assertNotIn("tools", calls[1])

    def test_actions_keep_a_single_pass(self):
        agent, calls = self.make("add_task")
        out = agent.respond({"role": "mentor", "slack_id": "U1", "name": "Ben"}, "add a task")
        self.assertEqual(len(calls), 1)
        self.assertIn("RAW CALENDAR DUMP", out["text"])


if __name__ == "__main__":
    unittest.main()
