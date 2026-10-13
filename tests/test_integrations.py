import os
import sys
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import integrations as i  # noqa: E402


class Q:
    def __init__(self, data):
        self.data = data

    def __getattr__(self, _):
        return lambda *a, **k: self

    def execute(self):
        return NS(data=self.data)


class SB:
    def __init__(self, rows):
        self.rows = rows

    def table(self, _):
        return Q(self.rows)


class IntegrationTests(unittest.TestCase):
    def test_state_matches_the_vector_the_website_test_verifies(self):
        state = i.sign_state({"f": "founder-x", "s": "startup-y", "p": "github"}, "test-secret", now=2000000000)
        self.assertTrue(state.startswith("eyJleHAiOjIwMDAwMDM2MDAs"))
        self.assertTrue(state.endswith("0d7a1baedeb1b767a158a8299f57abf2e42e1e015139128d1502e6c484ebb93c"))

    def test_no_link_until_the_github_app_is_configured(self):
        self.assertIsNone(i.github_connect_url(None, "s", "f", "st"))
        self.assertIsNone(i.github_connect_url("my-app", None, "f", "st"))
        self.assertIn("github.com/apps/my-app/installations/new?state=", i.github_connect_url("my-app", "s", "f", "st"))

    def test_activity_summary_counts_real_work(self):
        rows = [
            {"type": "commit", "meta": {"commits": 3, "repo": "a/web"}, "created_at": "2026-10-13T10:00:00+00:00"},
            {"type": "commit", "meta": {"commits": 2, "repo": "a/web"}, "created_at": "2026-10-12T10:00:00+00:00"},
            {"type": "pull_request", "meta": {"merged": True, "repo": "a/web"}, "created_at": "2026-10-12T09:00:00+00:00"},
            {"type": "pull_request", "meta": {"merged": False, "repo": "a/web"}, "created_at": "2026-10-11T09:00:00+00:00"},
            {"type": "issue", "meta": {"action": "closed", "repo": "a/web"}, "created_at": "2026-10-11T08:00:00+00:00"},
        ]
        a = i.activity_summary(SB(rows), "s", now=datetime(2026, 10, 13, 12, tzinfo=timezone.utc), monitored=["a/web"])
        self.assertEqual((a["commits"], a["prs_opened"], a["prs_merged"], a["issues_closed"]), (5, 1, 1, 1))
        self.assertIn("5 commits", i.activity_line(a, True))
        self.assertEqual(i.activity_line(a, False), "GitHub not connected")

    def test_activity_only_counts_the_repos_monitored_now(self):
        rows = [
            {"type": "commit", "meta": {"commits": 3, "repo": "a/web"}, "created_at": "2026-10-13T10:00:00+00:00"},
            {"type": "commit", "meta": {"commits": 9, "repo": "a/old"}, "created_at": "2026-10-13T09:00:00+00:00"},
            {"type": "meeting", "meta": {"meetings": 2, "external": 1}, "created_at": "2026-10-13T08:00:00+00:00"},
        ]
        now = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
        a = i.activity_summary(SB(rows), "s", now=now, monitored=["a/web"])
        self.assertEqual((a["commits"], a["meetings"]), (3, 2))
        # Switching the selection to the other repo flips what counts, without touching stored rows.
        self.assertEqual(i.activity_summary(SB(rows), "s", now=now, monitored=["a/old"])["commits"], 9)



class RepoSelectorTests(unittest.TestCase):
    ROW = {"id": "i1", "account": "acme", "repos": ["acme/web", "acme/api", "acme/docs"], "selected_repos": ["acme/web"]}

    def test_nothing_is_preselected_before_the_founder_chooses(self):
        row = {"id": "i1", "repos": ["a/x", "a/y"], "selected_repos": None}
        select = i.build_repo_selector(row, "hi")[0]["accessory"]
        self.assertNotIn("initial_options", select)
        self.assertEqual(i.monitored_repos(row), [])

    def test_selector_preselects_the_monitored_repos(self):
        blocks = i.build_repo_selector(self.ROW, "hi")
        select = blocks[0]["accessory"]
        self.assertEqual(blocks[0]["block_id"], "repos_i1")
        self.assertEqual([o["value"] for o in select["initial_options"]], ["acme/web"])
        self.assertEqual(len(select["options"]), 3)

    def test_a_single_granted_repo_is_monitored_automatically(self):
        self.assertEqual(i.monitored_repos({"repos": ["a/x"], "selected_repos": None}), ["a/x"])

    def test_single_repo_needs_no_selector(self):
        self.assertEqual(len(i.build_repo_selector({"id": "i", "repos": ["a/x"]}, "hi")), 1)

    def test_headlines(self):
        self.assertIn("monitoring *a/x*", i.connected_headline({"repos": ["a/x"], "account": "a"}, "S"))
        self.assertIn("can't see any repositories", i.connected_headline({"repos": []}, "S"))
        self.assertIn("Which one is", i.connected_headline(self.ROW, "S"))



class OrgAndCofounderTests(unittest.TestCase):
    def test_org_login_validation(self):
        for ok in ("acme", "Acme-Labs", "a1", "x" * 39):
            self.assertTrue(i.valid_org_login(ok), ok)
        for bad in ("", "-acme", "acme-", "ac--me", "has space", "x" * 40, "a/b", "../etc", "acme.org"):
            self.assertFalse(i.valid_org_login(bad), bad)

    def test_old_claims_expire(self):
        rows = [{"id": "c1", "org_login": "acme", "created_at": "2026-10-10T00:00:00+00:00"}]
        self.assertEqual(len(i.open_claims(SB(rows), now=datetime(2026, 10, 13, tzinfo=timezone.utc))), 1)



class DashboardLinkTests(unittest.TestCase):
    def test_link_carries_a_personal_single_use_pass(self):
        url = i.dashboard_url("https://dash.example/", "secret", "founder-x")
        self.assertTrue(url.startswith("https://dash.example/?k="))
        self.assertNotIn("as=", url)  # the view comes from the signed-in role, not the URL
        self.assertNotEqual(url, i.dashboard_url("https://dash.example/", "secret", "founder-x"))  # fresh pass each time
        self.assertIn("?k=", i.dashboard_url("https://dash.example/", "secret", None, slack_user_id="U123"))

    def test_without_a_person_or_secret_it_is_the_plain_link(self):
        self.assertEqual(i.dashboard_url("https://dash.example/", None, "founder-x"), "https://dash.example/")
        self.assertEqual(i.dashboard_url("https://dash.example/", "secret", None), "https://dash.example/")
        self.assertIsNone(i.dashboard_url(None, "secret", None))


if __name__ == "__main__":
    unittest.main()
