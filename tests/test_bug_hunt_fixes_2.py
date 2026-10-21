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


class HomeOpenLinkTests(unittest.TestCase):
    def test_unregistered_user_opening_home_is_linked_by_email_first(self):
        client = mock.MagicMock()
        with mock.patch.object(b, "get_role", return_value=None), \
                mock.patch.object(b, "slack_email", return_value="james@mambapartners.com"), \
                mock.patch.object(b, "has_unlinked_invite", return_value=True), \
                mock.patch.object(b, "onboard_member", return_value=True) as onboard, \
                mock.patch.object(b, "publish_home") as publish:
            b.handle_app_home_opened({"user": "UJAMES", "tab": "home"}, client)
        onboard.assert_called_once_with("UJAMES", client)
        publish.assert_not_called()

    def test_registered_user_just_gets_their_home(self):
        with mock.patch.object(b, "get_role", return_value="mentor"), \
                mock.patch.object(b, "onboard_member") as onboard, mock.patch.object(b, "publish_home") as publish:
            b.handle_app_home_opened({"user": "U1", "tab": "home"}, mock.MagicMock())
        onboard.assert_not_called()
        publish.assert_called_once()


    def test_a_stranger_opening_home_does_not_trigger_onboarding_dms(self):
        with mock.patch.object(b, "get_role", return_value=None), mock.patch.object(b, "slack_email", return_value="x@y.com"),                 mock.patch.object(b, "has_unlinked_invite", return_value=False),                 mock.patch.object(b, "onboard_member") as onboard, mock.patch.object(b, "publish_home") as publish:
            b.handle_app_home_opened({"user": "UX", "tab": "home"}, mock.MagicMock())
        onboard.assert_not_called()
        publish.assert_called_once()


class HuntRoundThreeTests(unittest.TestCase):
    def test_short_voice_note_mentioning_a_call_is_not_a_meeting_recording(self):
        import meeting_capture as mc
        note = {"subtype": "slack_audio", "mimetype": "audio/webm", "duration_ms": 25000, "size": 90000}
        self.assertFalse(mc.is_recording(note, "just had a call with a customer, quick update"))
        self.assertTrue(mc.is_recording(note, "recording of our call"))
        self.assertTrue(mc.is_recording({**note, "duration_ms": 10 * 60000}, "call"))

    def test_double_click_saves_a_checkin_once(self):
        self.assertTrue(b.first_press("C1", "100.1"))
        self.assertFalse(b.first_press("C1", "100.1"))
        b.release_press("C1", "100.1")
        self.assertTrue(b.first_press("C1", "100.1"))
        b.release_press("C1", "100.1")

    def _body(self, user):
        import json as _j
        value = _j.dumps({"startup_id": "s", "deliverable_id": "d", "founder_id": "f1", "status": "On Track", "progress": 5,
                          "blocker": "None", "digest": "x"})
        return {"actions": [{"value": value}], "user": {"id": user, "name": "n"}, "channel": {"id": "C9"}, "message": {"ts": "9.9"}}

    def test_someone_else_cannot_save_a_founders_checkin(self):
        client = mock.MagicMock()
        with mock.patch.object(b, "owns_checkin", return_value=False), mock.patch.object(b, "commit_checkin") as commit:
            b.handle_confirm_checkin(lambda: None, self._body("UOTHER"), client)
        commit.assert_not_called()
        client.chat_postEphemeral.assert_called_once()

    def test_two_clicks_commit_once(self):
        client = mock.MagicMock()
        with mock.patch.object(b, "owns_checkin", return_value=True), mock.patch.object(b, "commit_checkin", return_value=True) as commit, \
                mock.patch.object(b, "estimate_after_checkin"), mock.patch.object(b, "publish_home"):
            b.handle_confirm_checkin(lambda: None, self._body("U1"), client)
            b.handle_confirm_checkin(lambda: None, self._body("U1"), client)
        self.assertEqual(commit.call_count, 1)
        b.release_press("C9", "9.9")

    def test_a_failed_save_can_be_retried(self):
        client = mock.MagicMock()
        with mock.patch.object(b, "owns_checkin", return_value=True), mock.patch.object(b, "commit_checkin", side_effect=[False, True]) as commit, \
                mock.patch.object(b, "estimate_after_checkin"), mock.patch.object(b, "publish_home"):
            b.handle_confirm_checkin(lambda: None, self._body("U1"), client)
            b.handle_confirm_checkin(lambda: None, self._body("U1"), client)
        self.assertEqual(commit.call_count, 2)
        b.release_press("C9", "9.9")


class RoundAgentTests(unittest.TestCase):
    def test_percent_reads_what_models_send(self):
        import bot_agent as ba
        self.assertEqual([ba._percent(v) for v in (60, "60", "60%", 60.6, None, "lots", 250, -5)], [60, 60, 60, 61, 50, 50, 100, 0])

    def test_ticking_a_goal_never_reopens_a_done_milestone_but_unticking_does(self):
        def mem(status, goals):
            sb = mock.MagicMock()
            sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
                {"status": status, "goals": [{"done": d} for d in goals]}]
            return Memory(sb)
        self.assertIsNone(mem("done", [True, False]).sync_milestone("m", reopen=False))
        self.assertEqual(mem("done", [True, False]).sync_milestone("m", reopen=True), "open")
        self.assertEqual(mem("open", [True, True]).sync_milestone("m", reopen=False), "done")

    def test_series_changes_say_they_are_one_date(self):
        card = b.build_meeting_card({"kind": "change", "action": "cancel", "title": "Sprint", "old": "Thu", "attendee_count": 3,
                                      "series": True, "id": "x"})
        self.assertIn("other dates stay", card[0]["text"]["text"])
        move = b.build_meeting_card({"kind": "change", "action": "reschedule", "title": "Sprint", "old": "Thu", "new": "Fri",
                                      "attendee_count": 3, "series": True, "id": "x"})
        self.assertIn("other dates stay", move[0]["text"]["text"])


class UnresolvedWarningTests(unittest.TestCase):
    def test_a_failure_the_model_does_not_fix_is_not_hidden_by_a_cheerful_reply(self):
        from test_agent_loop import Script, agent_with, call
        from test_bot_agent import MENTOR
        s = Script(("", [call("add_goal", {"milestone_ref": "zzzz", "title": "x"})]), ("All done, goal added!", []))
        a, mem = agent_with(s)
        out = a.respond(MENTOR, "add a goal")
        self.assertIn("All done", out["text"])
        self.assertIn("couldn't find that milestone", out["text"])


class RoutineTests(unittest.TestCase):
    def test_every_weeks_is_read_leniently(self):
        import routines
        base = {"weekday": "wednesday", "time": "14:00", "instruction": "x"}
        for given, want in ((2, 2), ("2", 2), ("4 weeks", 4), ("weekly", 1), (None, 1)):
            row, problem = routines.validate({**base, "every_weeks": given})
            self.assertIsNone(problem)
            self.assertEqual(row["every_weeks"], want, given)

    def test_people_routines_resolve_names_and_mentions_to_slack_ids(self):
        from test_agent_loop import Script, agent_with, call
        from test_bot_agent import MENTOR
        tables = {"startups": [], "founders": [{"name": "Takshma Patel", "slack_user_id": "U0C79P3470S", "startups": {"name": "Auvira"}}],
                  "mentors": [{"name": "Ben", "slack_user_id": "U0C7BRXM34Z"}]}
        s = Script(("", [call("create_routine", {"instruction": "send the deck", "weekday": "wednesday", "time": "14:00",
                                                    "audience": "people", "people": ["Takshma", "<@U0C7BRXM34Z>"]})]), ("Set.", []))
        a, mem = agent_with(s, tables=tables)
        a.routines = object()  # any truthy store: this path only proposes a card
        out = a.respond(MENTOR, "every wednesday remind takshma and me")
        saved = [p for _, p in getattr(mem, "meetings", [])] if hasattr(mem, "meetings") else []
        card = (out.get("meetings") or [None])[0]
        self.assertIsNotNone(card, out["text"])
        self.assertEqual(sorted(card["routine"]["people"]), ["U0C79P3470S", "U0C7BRXM34Z"])


class QuestionAfterWarningTests(unittest.TestCase):
    def run_turn(self, reply):
        from test_agent_loop import Script, agent_with, call
        from test_bot_agent import MENTOR
        s = Script(("", [call("add_goal", {"milestone_ref": "zzzz", "title": "x"})]), (reply, []))
        a, _ = agent_with(s)
        return a.respond(MENTOR, "add a goal")["text"]

    def test_a_clarifying_question_replaces_the_warning(self):
        text = self.run_turn("I couldn't find that one. Which milestone should I add it to?")
        self.assertNotIn("⚠", text)

    def test_a_question_early_in_the_reply_does_not_hide_a_false_success(self):
        text = self.run_turn("Need anything else? Done! Goal added.")
        self.assertIn("couldn't find that milestone", text)

    def test_plain_success_claim_still_shows_the_warning(self):
        self.assertIn("couldn't find that milestone", self.run_turn("Done! Goal added."))


class FirstNameTests(unittest.TestCase):
    def test_one_rule_for_greetings_everywhere(self):
        from profile_rules import first_name
        import daily_checkin, founder_nudges
        for name, want in (("Takshma Patel", "Takshma"), ("Leung Wai-Leng", "Wai Leng"), ("James Sun", "James"), ("arthur andre", "Arthur"), ("wai-leng", "Wai-Leng"),
                           ("Madonna", "Madonna"), ("", "there"), (None, "there"), ("   ", "there")):
            self.assertEqual(first_name(name), want)
            self.assertEqual(daily_checkin._first_name(name), want)
            self.assertEqual(founder_nudges.first_name(name), want)


class PercentParityTests(unittest.TestCase):
    def test_halves_round_up_like_the_dashboard(self):
        import progress_estimator as pe
        self.assertEqual(pe.milestone_value([{"done": False, "progress": 50}, {"done": False, "progress": 51}])[0], 51)  # 50.5
        self.assertEqual(pe.milestone_value([{"done": False, "progress": 0}, {"done": False, "progress": 1}])[0], 1)     # 0.5
        self.assertEqual(pe.half_up(2.5), 3)
        self.assertEqual(pe.half_up(3.5), 4)


class ImportRobustnessTests(unittest.TestCase):
    def test_week_numbers_written_as_text_are_read(self):
        import syllabus_import as si
        spec = si.clean({"weeks": [{"week": "Week 3", "sprint": "2", "title": "Pricing", "end": "2026-11-06", "milestones": ["a"]},
                                   {"week": None, "title": "Next", "end": "2026-11-13"}]})
        self.assertEqual([w["week"] for w in spec["weeks"]], [3, 2])

    def test_a_zip_bomb_is_refused(self):
        import io, zipfile, attachments
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("word/document.xml", "<w:t>x</w:t>" * 10)
        self.assertIn("x", attachments.office_text(buf.getvalue(), "docx"))
        with mock.patch.object(attachments, "MAX_UNZIPPED", 5):
            with self.assertRaises(ValueError):
                attachments.office_text(buf.getvalue(), "docx")


class WeekFlipTests(unittest.TestCase):
    def test_the_week_flips_after_fridays_gate_like_the_dashboard(self):
        import syllabus
        from datetime import date as d
        week = lambda day: syllabus.current(day)["week"]  # noqa: E731
        self.assertEqual([week(d(2026, 10, n)) for n in (15, 16)], ["WK 02", "WK 02"])   # Thursday, gate day
        self.assertEqual([week(d(2026, 10, n)) for n in (17, 18, 19)], ["WK 03", "WK 03", "WK 03"])  # Sat, Sun, Monday
        self.assertEqual(syllabus.current_deliverable(d(2026, 10, 17))["id"], "del-wk03")
        self.assertIsNone(syllabus.current(d(2026, 1, 1)))

    def test_a_cohorts_weekend_deliverable_is_next_weeks(self):
        import cohorts
        from datetime import date as d
        start = d(2026, 10, 19)
        fri, sat = cohorts.this_weeks_deliverable(start, d(2026, 10, 23)), cohorts.this_weeks_deliverable(start, d(2026, 10, 24))
        self.assertEqual((fri["week"], sat["week"]), (1, 2))


class HomeLimitTests(unittest.TestCase):
    def test_a_home_view_never_exceeds_slacks_limits(self):
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": f"row {i}"}} for i in range(130)]
        fitted = b.fit_blocks(blocks)
        self.assertEqual(len(fitted), 100)
        self.assertIn("more than fits", fitted[-1]["elements"][0]["text"])
        long = b.fit_blocks([{"type": "section", "text": {"type": "mrkdwn", "text": "x" * 5000}}])
        self.assertLessEqual(len(long[0]["text"]["text"]), 3000)
        with mock.patch.object(b, "brand_block", return_value={"type": "context", "block_id": "brand", "elements": []}):
            self.assertLessEqual(len(b.branded(blocks)), 100)
            self.assertEqual(len(b.branded(blocks[:5])), 6)  # the brand line still goes first on a normal view


class TokenCacheTests(unittest.TestCase):
    def test_access_tokens_are_reused_until_they_lapse(self):
        import google_calendar as gc
        calls = []

        def http(method, url, **kw):
            calls.append(url)
            return {"access_token": f"tok{len(calls)}", "expires_in": 3600}
        cal = gc.GoogleCalendar("id", "secret", "https://x/cb", "state-secret", http=http)
        blob = gc.encrypt_token("refresh", "state-secret")
        self.assertEqual([cal.access_token(blob), cal.access_token(blob)], ["tok1", "tok1"])
        self.assertEqual(len(calls), 1)
        cal._tokens[blob] = ("old", 0)  # expired
        self.assertEqual(cal.access_token(blob), "tok2")
        self.assertIsNone(cal.access_token("not-a-valid-blob"))


class BigCohortHomeTests(unittest.TestCase):
    def test_many_startups_split_across_sections_instead_of_overflowing(self):
        from datetime import date
        import mentor_home
        latest = {"created_at": "2026-10-19T03:00:00+00:00", "status": "On Track", "progress": 50, "blocker": "None", "digest": "d" * 150}
        summaries = [{"id": f"s{i}", "name": f"Startup {i}", "stream": "GTM", "lead": "x", "founders": ["Ann"], "latest": latest,
                      "recent": [latest], "health": "on_track", "detail": "", "last_seen": "1 day ago", "blocked_days": 0,
                      "idle_days": 1, "work": "5 commits, 1 PRs opened, 0 PRs merged, 0 issues closed (last 7 days)"} for i in range(40)]
        blocks = mentor_home.build_mentor_blocks(summaries, today=date(2026, 10, 20))
        sections = [bl for bl in blocks if bl["type"] == "section"]
        self.assertGreater(len(sections), 2)
        self.assertTrue(all(len(bl["text"]["text"]) <= 3000 for bl in sections))
        shown = " ".join(bl["text"]["text"] for bl in sections)
        self.assertTrue(all(f"Startup {i}" in shown for i in range(40)))  # nobody is dropped


class SlackLimitTests(unittest.TestCase):
    def test_long_headers_and_field_lists_are_capped(self):
        long_header = {"type": "header", "text": {"type": "plain_text", "text": "H" * 400}}
        many_fields = {"type": "section", "fields": [{"type": "mrkdwn", "text": "f" * 2500} for _ in range(14)]}
        out = b.fit_blocks([long_header, many_fields])
        self.assertEqual(len(out[0]["text"]["text"]), 150)
        self.assertEqual(len(out[1]["fields"]), 10)
        self.assertTrue(all(len(f["text"]) <= 2000 for f in out[1]["fields"]))

    def test_the_static_home_blocks_stay_inside_slacks_limits(self):
        for role in ("founder", "mentor"):
            for bl in b.home_features_blocks(role) + b.how_to_blocks(role) + b.how_to_blocks(role, compact=True):
                if bl.get("type") == "section" and "fields" in bl:
                    self.assertLessEqual(len(bl["fields"]), 10, role)
                    self.assertTrue(all(len(f["text"]) <= 2000 for f in bl["fields"]), role)
                if bl.get("type") == "header":
                    self.assertLessEqual(len(bl["text"]["text"]), 150)
                if bl.get("type") == "section" and isinstance(bl.get("text"), dict):
                    self.assertLessEqual(len(bl["text"]["text"]), 3000)


class DigestOverdueTests(unittest.TestCase):
    def test_overdue_follow_ups_are_labelled_as_such(self):
        import digest as d
        from datetime import date
        blocks = d.build_digest_blocks([], date(2026, 10, 20), [], [
            {"title": "Old one", "due_date": "2026-10-16", "startups": {"name": "Auvira"}},
            {"title": "Soon", "due_date": "2026-10-22", "startups": {"name": "Auvira"}}])
        text = " ".join(bl.get("text", {}).get("text", "") for bl in blocks if bl["type"] == "section")
        self.assertIn("or overdue", text)
        self.assertEqual(text.count("overdue"), 2)  # heading + the one late item


class MeetLinkSafetyTests(unittest.TestCase):
    def test_only_real_meet_links_become_links(self):
        import studio_events as se
        self.assertEqual(se._meet_url({"hangoutLink": "https://meet.google.com/abc-defg-hij"}), "https://meet.google.com/abc-defg-hij")
        self.assertEqual(se._meet_url({"location": "https://meet.google.com/abc-defg-hij?authuser=0"}), "https://meet.google.com/abc-defg-hij?authuser=0")
        self.assertIsNone(se._meet_url({"location": "javascript:alert(1)//meet.google.com/x"}))
        self.assertIsNone(se._meet_url({"location": "111 Somerset"}))
        self.assertIsNone(se._meet_url({"hangoutLink": "http://meet.google.com/abc"}))
