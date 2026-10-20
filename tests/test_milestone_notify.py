import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import milestone_notify as mn  # noqa: E402

NOW = datetime(2026, 10, 20, 2, 0, tzinfo=timezone.utc)


def ago(**kw):
    return (NOW - timedelta(**kw)).isoformat()


class Q:
    def __init__(self, data):
        self.data = data

    def __getattr__(self, _):
        return lambda *a, **k: self

    def execute(self):
        return NS(data=self.data)


class DB:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return Q(self.tables[name])


class Client:
    def __init__(self, emails=None):
        self.posts, self.emails = [], emails or {}

    def chat_postMessage(self, channel, text):
        self.posts.append((channel, text))

    def users_info(self, user):
        return {"user": {"profile": {"email": self.emails.get(user, "")}}}


def milestone(mid, created, role="mentor", startup="s1", **kw):
    return {"id": mid, "startup_id": startup, "title": f"Milestone {mid}", "due_date": "2026-10-30", "status": "open",
            "created_by": "UMENTOR001", "created_by_role": role, "created_at": created, "startups": {"name": "Auvira"},
            "goals": [{"title": "Draft script"}], **kw}


def task(tid, created, owner=None, by="UMENTOR001", startup="s1"):
    return {"id": tid, "startup_id": startup, "owner_slack_id": owner, "title": f"Task {tid}", "due_date": "2026-10-23",
            "status": "open", "created_by": by, "created_at": created, "startups": {"name": "Auvira"}}


class MilestoneNotifyTests(unittest.TestCase):
    def setUp(self):
        mn.STARTED = NOW - timedelta(hours=1)
        self.seen = set()
        self.mails = []
        self.db = DB({
            "milestones": [milestone("a", ago(minutes=5)), milestone("b", ago(minutes=4)),
                           milestone("own", ago(minutes=5), role="founder"),         # founder's own: no notice
                           milestone("fresh", ago(seconds=10)),                      # goals may still be landing
                           milestone("old", ago(hours=3)),                           # from before the notifier ran
                           milestone("c", ago(minutes=5), startup="s2")],
            "tasks": [task("t1", ago(minutes=5)),
                      task("mine", ago(minutes=5), owner="UMENTOR001"),              # a mentor's own follow-up
                      task("selfset", ago(minutes=5), by="UANNLEE001")],             # the founder's own reminder
            "mentors": [{"name": "Arthur Tan", "email": "arthur@studio.example", "slack_user_id": "UMENTOR001"},
                        {"name": "Mo Lim", "email": "", "slack_user_id": "UMENTOR002"}],
            "founders": [{"name": "Ann Lee", "email": "ann@old.example", "slack_user_id": "UANNLEE001", "startup_id": "s1"},
                         {"name": "Bo Ng", "email": "bo@example.com", "slack_user_id": None, "startup_id": "s1"},
                         {"name": "Cy", "email": "", "slack_user_id": "UCYCYCY001", "startup_id": "s2"}],
        })
        self.client = Client({"UANNLEE001": "ann@slack.example"})

    def run_once(self):
        return mn.run(self.db, self.client, lambda k: k in self.seen, self.seen.add,
                      send_email=lambda *a: self.mails.append(a), now=NOW)

    def test_one_combined_message_per_founder_on_slack_and_email(self):
        self.run_once()
        ann = [t for c, t in self.client.posts if c == "UANNLEE001"]
        self.assertEqual(len(ann), 1)
        self.assertIn("Arthur Tan set 2 new milestones and a task for Auvira", ann[0])
        for shown in ("Milestone a", "Draft script", "Task t1"):
            self.assertIn(shown, ann[0])
        for skipped in ("Milestone own", "Milestone fresh", "Milestone old", "Task mine", "Task selfset"):
            self.assertNotIn(skipped, ann[0])
        to = sorted(m[0] for m in self.mails)
        # Ann's Slack email wins over the stored one; Bo isn't on Slack but still gets the email; Cy has no email.
        self.assertEqual(to, ["ann@slack.example", "bo@example.com"])
        self.assertEqual([c for c, _ in self.client.posts].count("UCYCYCY001"), 1)

    def test_email_says_who_sent_it_and_replies_go_to_them(self):
        self.run_once()
        to, subject, body, from_name, reply_to, page = next(m for m in self.mails if m[0] == "bo@example.com")
        self.assertEqual(subject, "Arthur Tan set 2 new milestones and a task for Auvira")
        self.assertEqual(from_name, "Arthur Tan via Venture Studio")
        self.assertEqual(reply_to, ["arthur@studio.example"])
        self.assertIn("Arthur Tan (your mentor) set", body)
        self.assertIn("Sent by: Arthur Tan (arthur@studio.example), via Venture Buddy.", body)
        self.assertIn("Reply to this email to answer Arthur Tan directly.", body)
        self.assertIn("MILESTONES", body)
        self.assertIn("TASKS", body)
        self.assertNotIn("*", body)
        for bit in ("<!doctype html>", "Arthur Tan set 2 new milestones and a task for Auvira", "Milestone a", "Draft script",
                    "Task t1", "Due Fri Oct 30", "mailto:arthur@studio.example", "Your mentor", ">AT<"):
            self.assertIn(bit, page)

    def test_each_item_is_announced_once(self):
        self.run_once()
        posts, mails = len(self.client.posts), len(self.mails)
        self.run_once()
        self.assertEqual((len(self.client.posts), len(self.mails)), (posts, mails))
        self.assertTrue({"ms-notify:a", "task-notify:t1"} <= self.seen)
        self.assertNotIn("ms-notify:fresh", self.seen)

    def test_without_the_studio_account_only_slack_is_used(self):
        mn.run(self.db, self.client, lambda k: False, lambda k: None, send_email=None, now=NOW)
        self.assertTrue(self.client.posts)

    def test_several_mentors_are_each_credited(self):
        items = [dict(milestone("a", ago(minutes=5)), kind="milestone", mentor="Arthur Tan"),
                 dict(task("t", ago(minutes=5)), kind="task", mentor="Mo Lim")]
        text = mn.slack_text("Ann", items, "Auvira")
        self.assertIn("Arthur Tan and Mo Lim set a new milestone and a task", text)
        self.assertIn("from Arthur Tan", text)
        self.assertIn("from Mo Lim", text)
        subject, body, from_name, reply_to, page = mn.email_parts("Ann", items, "Auvira", {"Arthur Tan": "a@x.example", "Mo Lim": ""})
        self.assertIn("from Mo Lim", page)
        self.assertIn("Your mentors", page)
        self.assertEqual(from_name, "Your mentors via Venture Studio")
        self.assertEqual(reply_to, ["a@x.example"])
        self.assertIn("Sent by: Arthur Tan (a@x.example), Mo Lim", body)

    def test_long_imports_are_summarised(self):
        items = [dict(milestone(str(i), ago(minutes=5)), kind="milestone", mentor="Arthur") for i in range(10)]
        text = mn.slack_text("Ann", items, "Auvira")
        self.assertIn("10 new milestones", text)
        self.assertIn("…and 4 more milestones", text)

    def test_html_escapes_what_people_typed(self):
        items = [dict(milestone("a", ago(minutes=5)), kind="milestone", mentor="Arthur <b>", title="Ship <script>x</script>")]
        page = mn.email_html("Ann", items, "A&B Co", {})
        self.assertNotIn("<script>", page)
        self.assertIn("Ship &lt;script&gt;", page)
        self.assertIn("A&amp;B Co", page)
        self.assertNotIn("Open the dashboard", page)  # no link without a dashboard url
        self.assertNotIn("<img", page)                 # nor a logo: it is served by the dashboard site

    def test_logo_comes_from_the_dashboard_site(self):
        items = [dict(milestone("a", ago(minutes=5)), kind="milestone", mentor="Arthur")]
        page = mn.email_html("Ann", items, "Auvira", {}, "https://dash.example/")
        self.assertIn('<img src="https://dash.example/email-logo.png"', page)
        self.assertTrue(os.path.exists(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public", "email-logo.png")))


if __name__ == "__main__":
    unittest.main()
