import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import github_app as g  # noqa: E402
import progress_estimator as pe  # noqa: E402


class FakeHTTP:
    def __init__(self):
        self.urls = []

    def __call__(self, method, url, headers, params=None):
        self.urls.append(url)
        if url.endswith("/access_tokens"):
            return {"token": "tok", "expires_at": "2099-01-01T00:00:00Z"}
        f = {"filename": "src/pay.ts", "status": "added", "additions": 3, "deletions": 0, "patch": "+charge()"}
        return [f] if "/pulls/" in url else {"files": [f]}


def app():
    a = g.GitHubApp("1", "key", http=FakeHTTP())
    a._tokens["9"] = ("tok", 4102444800)
    return a


class CodeChangesTests(unittest.TestCase):
    def test_each_kind_of_signal_reads_the_right_diff(self):
        a = app()
        a.code_changes("9", "a/web", {"type": "pull_request", "meta": {"number": 7}})
        a.code_changes("9", "a/web", {"type": "commit", "meta": {"before": "abc", "after": "def"}})
        a.code_changes("9", "a/web", {"type": "commit", "meta": {"before": "0" * 40, "after": "def"}})  # new branch
        a.code_changes("9", "a/web", {"type": "commit", "meta": {"shas": ["s1", "s2"]}})  # backfilled day
        self.assertEqual([u.split("/repos/a/web/")[1] for u in a.http.urls],
                         ["pulls/7/files", "compare/abc...def", "commits/def", "commits/s1", "commits/s2"])
        self.assertEqual(a.code_changes("9", "a/web", {"type": "commit", "meta": {}}), [])
        self.assertEqual(a.code_changes("9", "a/web", {"type": "pull_request", "meta": {"number": 7}})[0]["patch"], "+charge()")


class DiffExcerptTests(unittest.TestCase):
    def test_noise_is_left_out_and_size_is_capped(self):
        files = [{"file": "package-lock.json", "status": "modified", "additions": 900, "deletions": 900, "patch": "x"},
                 {"file": "logo.png", "status": "added", "additions": 0, "deletions": 0, "patch": ""},
                 {"file": "src/pay.ts", "status": "added", "additions": 40, "deletions": 0, "patch": "+" * 5000},
                 {"file": "src/a.ts", "status": "modified", "additions": 1, "deletions": 1, "patch": "-a\n+b"}]
        out = pe.diff_excerpt(files)
        self.assertNotIn("package-lock", out.split("(")[0])
        self.assertIn("src/pay.ts (added, +40/-0)", out)
        self.assertIn("… (cut)", out)
        self.assertIn("src/a.ts", out)
        self.assertIn("2 more files not shown", out)
        self.assertIn("1 more file not shown", pe.diff_excerpt(files[2:], budget=1550))

    def test_the_prompt_shows_code_changes_under_the_work(self):
        work = [{"created_at": "2026-10-22T00:00:00Z", "type": "commit", "headline": "ann pushed 1 commit",
                 "meta": {"messages": ["add payments"]}, "diff": "src/pay.ts (added, +1/-0)\n+charge()"}]
        prompt = pe.build_prompt([("g1", {"title": "Payments", "milestone": "MVP"})], work)
        self.assertIn("CODE CHANGES:\n    src/pay.ts (added, +1/-0)\n    +charge()", prompt)
        self.assertIn("strongest evidence", pe.SYSTEM)


class AttachDiffsTests(unittest.TestCase):
    class DB:
        def __init__(self, rows):
            self.rows = rows

        def table(self, _):
            return self

        def select(self, *_):
            return self

        def eq(self, *_):
            return self

        def execute(self):
            from types import SimpleNamespace
            return SimpleNamespace(data=self.rows)

    def test_only_monitored_repos_with_an_install_and_never_issues(self):
        db = self.DB([{"external_id": "9", "repos": ["a/web"], "selected_repos": None}])
        work = [{"type": "commit", "meta": {"repo": "a/web", "before": "abc", "after": "def"}},
                {"type": "commit", "meta": {"repo": "a/other", "after": "x"}},
                {"type": "issue", "meta": {"repo": "a/web", "number": 1}}]
        out = pe.attach_diffs(db, app(), "s1", work)
        self.assertIn("+charge()", out[0]["diff"])
        self.assertNotIn("diff", out[1])
        self.assertNotIn("diff", out[2])

    def test_github_failing_or_no_app_keeps_the_work_as_it_was(self):
        class Broken:
            def code_changes(self, *_):
                raise RuntimeError("401")
        db = self.DB([{"external_id": "9", "repos": ["a/web"]}])
        work = [{"type": "commit", "meta": {"repo": "a/web", "after": "def"}}]
        self.assertNotIn("diff", pe.attach_diffs(db, Broken(), "s1", work)[0])
        self.assertIs(pe.attach_diffs(db, None, "s1", work), work)


if __name__ == "__main__":
    unittest.main()
