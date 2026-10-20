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


class SlotTests(unittest.TestCase):
    def rows(self, row, extra=0):
        return [b for b in i.build_repo_slots(row, "head", extra) if b["type"] == "actions"]

    def test_one_empty_row_to_start_then_plus_opens_the_next(self):
        row = {"id": "r1", "repos": GRANTED, "selected_repos": None}
        first = self.rows(row)
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["elements"][0]["placeholder"]["text"], "Select repo 1")
        self.assertEqual(first[0]["elements"][1]["action_id"], "add_repo_slot")
        chosen = {**row, "selected_repos": ["acme/Bazi-Engine"]}
        two = self.rows(chosen, i.empty_slots(chosen, 0) + 1)
        self.assertEqual([r["block_id"] for r in two], ["slot_r1_0", "slot_r1_1"])
        self.assertEqual(two[0]["elements"][0]["initial_option"]["value"], "acme/Bazi-Engine")
        self.assertEqual(len(two[0]["elements"]), 1)      # only the last row has the plus
        self.assertEqual(two[1]["elements"][0]["placeholder"]["text"], "Select repo 2")
        values = [o["value"] for o in two[1]["elements"][0]["options"]]
        self.assertNotIn("acme/Bazi-Engine", values)       # already tracked in row 1

    def test_no_plus_when_every_repo_is_used_and_single_repo_has_no_stop_option(self):
        full = {"id": "r1", "repos": GRANTED, "selected_repos": list(GRANTED)}
        self.assertTrue(all(len(r["elements"]) == 1 for r in self.rows(full)))
        solo = self.rows({"id": "r2", "repos": ["a/x"], "selected_repos": None})
        self.assertEqual([o["value"] for o in solo[0]["elements"][0]["options"]], ["a/x"])


class MentorChooseTests(unittest.TestCase):
    def test_mentor_sets_repos_for_a_startup_and_the_founder_is_refreshed(self):
        row = {"id": "i1", "founder_id": "f1", "repos": GRANTED, "selected_repos": None}
        db = Db([row])
        db.rows = [row]
        changed = []
        agent = Agent(None, "m", db, memory=NS(), repos_changed=lambda r, u: changed.append(u))
        ident = {"role": "mentor", "slack_id": "UMENTOR", "name": "M"}
        out = agent._choose_repos(ident, {"repos": ["website"]}, startup_id="s1")
        self.assertIn("Now tracking acme/website", out)
        self.assertEqual(db.updates, [{"selected_repos": ["acme/website"]}])
        miss = agent._choose_repos(ident, {"repos": ["nope"]}, startup_id="s1")
        self.assertIn("founder needs to share it first", miss)


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
