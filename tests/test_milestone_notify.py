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
            "mentors": [{"name": "Arthur Tan", "slack_user_id": "UMENTOR001"}],
            "founders": [{"name": "Ann Lee", "email": "ann@old.example", "slack_user_id": "UANNLEE001", "startup_id": "s1"},
                         {"name": "Bo Ng", "email": "bo@example.com", "slack_user_id": None, "startup_id": "s1"},
                         {"name": "Cy", "email": "", "slack_user_id": "UCYCYCY001", "startup_id": "s2"}],
        })
        self.client = Client({"UANNLEE001": "ann@slack.example"})

    def run_once(self):
        return mn.run(self.db, self.client, lambda k: k in self.seen, self.seen.add,
                      send_email=lambda to, subj, body: self.mails.append((to, subj, body)), now=NOW)

    def test_one_combined_message_per_founder_on_slack_and_email(self):
        self.run_once()
        ann = [t for c, t in self.client.posts if c == "UANNLEE001"]
        self.assertEqual(len(ann), 1)
        self.assertIn("Arthur Tan set 2 new milestones for Auvira", ann[0])
        self.assertIn("Milestone a", ann[0])
        self.assertIn("Draft script", ann[0])
        for skipped in ("Milestone own", "Milestone fresh", "Milestone old"):
            self.assertNotIn(skipped, ann[0])
        to = sorted(m[0] for m in self.mails)
        # Ann's Slack email wins over the stored one; Bo isn't on Slack but still gets the email; Cy has no email.
        self.assertEqual(to, ["ann@slack.example", "bo@example.com"])
        self.assertEqual([c for c, _ in self.client.posts].count("UCYCYCY001"), 1)

    def test_each_milestone_is_announced_once(self):
        self.run_once()
        posts, mails = len(self.client.posts), len(self.mails)
        self.run_once()
        self.assertEqual((len(self.client.posts), len(self.mails)), (posts, mails))
        self.assertIn("ms-notify:a", self.seen)
        self.assertNotIn("ms-notify:fresh", self.seen)

    def test_without_email_settings_only_slack_is_used(self):
        mn.run(self.db, self.client, lambda k: False, lambda k: None, send_email=None, now=NOW)
        self.assertTrue(self.client.posts)

    def test_long_imports_are_summarised(self):
        items = [milestone(str(i), ago(minutes=5), startup_name="Auvira") for i in range(10)]
        text = mn.slack_text("Ann", items, "Arthur")
        self.assertIn("10 new milestones", text)
        self.assertIn("…and 4 more", text)

    def test_email_reads_as_plain_text(self):
        subject, body = mn.email_parts("Ann", [milestone("a", ago(minutes=5), startup_name="Auvira")], "Arthur", "https://d.example")
        self.assertEqual(subject, "Arthur set a new milestone for Auvira")
        self.assertNotIn("*", body)
        self.assertIn("due Fri Oct 30", body)
        self.assertIn("https://d.example", body)

    def test_smtp_needs_settings(self):
        for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"):
            os.environ.pop(k, None)
        self.assertIsNone(mn.smtp_sender())


if __name__ == "__main__":
    unittest.main()
