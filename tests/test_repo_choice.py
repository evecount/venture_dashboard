import os
import sys
import unittest
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import integrations as i  # noqa: E402
from bot_agent import Agent  # noqa: E402

GRANTED = ["acme/Bazi-Engine", "acme/website", "acme/web-app"]


class Chain:
    def __init__(self, db, name): self.db, self.name, self.patch = db, name, None
    def select(self, *a): return self
    def eq(self, *a): return self
    def order(self, *a): return self
    def update(self, p): self.patch = p; return self
    def execute(self):
        if self.patch is not None:
            self.db.updates.append(self.patch)
            return NS(data=[])
        return NS(data=self.db.rows)


class Db:
    def __init__(self, rows): self.rows, self.updates = rows, []
    def table(self, n): return Chain(self, n)


class MatchTests(unittest.TestCase):
    def test_resolves_loose_names(self):
        self.assertEqual(i.match_repos(["bazi"], GRANTED)["chosen"], ["acme/Bazi-Engine"])
        self.assertEqual(i.match_repos(["acme/website"], GRANTED)["chosen"], ["acme/website"])
        self.assertEqual(i.match_repos(["web"], GRANTED)["ambiguous"][0][1], ["acme/website", "acme/web-app"])
        self.assertEqual(i.match_repos(["nothing"], GRANTED)["missing"], ["nothing"])


class KeepTests(unittest.TestCase):
    def test_sharing_more_repos_keeps_the_one_already_tracked(self):
        row = {"repos": ["a/x", "a/y"], "selected_repos": None}
        self.assertEqual(i.keep_implicit_choice((("a/x",), ()), row), ["a/x"])
        self.assertIsNone(i.keep_implicit_choice((("a/x",), ("a/x",)), row))        # they had chosen: leave it
        self.assertIsNone(i.keep_implicit_choice(((), ()), row))                     # nothing was tracked before
        self.assertIsNone(i.keep_implicit_choice((("a/z",), ()), row))               # the old one is gone
        self.assertIsNone(i.keep_implicit_choice((("a/x",), ()), {"repos": ["a/x"], "selected_repos": None}))  # still one repo


class ChooseTests(unittest.TestCase):
    def setUp(self):
        row = {"id": "i1", "founder_id": "f1", "repos": GRANTED, "selected_repos": None, "account": "acme", "founders": {"name": "A"}}
        self.db, self.changed = Db([row]), []
        self.agent = Agent(None, "m", self.db, memory=NS(), connect_url=lambda f, s: "https://gh/x",
                           repos_changed=lambda r, u: self.changed.append((r["selected_repos"], u)))
        self.ident = {"role": "founder", "slack_id": "U1", "name": "A", "context": {"founder_id": "f1", "startup_id": "s1"}}

    def test_switches_to_a_shared_repo_and_refreshes(self):
        out = self.agent._choose_repos(self.ident, {"repos": ["bazi"]})
        self.assertIn("Now tracking acme/Bazi-Engine", out)
        self.assertEqual(self.db.updates, [{"selected_repos": ["acme/Bazi-Engine"]}])
        self.assertEqual(self.changed, [(["acme/Bazi-Engine"], "U1")])

    def test_all_repos(self):
        self.agent._choose_repos(self.ident, {"all": True})
        self.assertEqual(set(self.db.updates[0]["selected_repos"]), set(GRANTED))

    def test_unshared_repo_gets_the_share_link_and_changes_nothing(self):
        out = self.agent._choose_repos(self.ident, {"repos": ["secret-repo"]})
        self.assertIn("can't see secret-repo", out)
        self.assertIn("https://gh/x", out)
        self.assertEqual(self.db.updates, [])

    def test_not_connected(self):
        self.db.rows = []
        self.assertIn("isn't connected yet", self.agent._choose_repos(self.ident, {"repos": ["x"]}))


if __name__ == "__main__":
    unittest.main()
