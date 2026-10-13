import os
import sys
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace as NS

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import github_app as g  # noqa: E402

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PEM = KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
PUB = KEY.public_key()


class FakeHTTP:
    def __init__(self):
        self.calls = []

    def __call__(self, method, url, headers, params=None):
        self.calls.append((method, url, params))
        if url.endswith("/access_tokens"):
            return {"token": "tok", "expires_at": "2099-01-01T00:00:00Z"}
        if url.endswith("/installation/repositories"):
            n = 100 if params["page"] == 1 else 2
            return {"repositories": [{"full_name": f"a/r{params['page']}-{i}"} for i in range(n)]}
        if url.endswith("/commits"):
            return [{"commit": {"author": {"date": "2026-10-12T08:00:00Z"}, "message": "Fix pricing\n\nmore"}, "author": {"login": "ann"}},
                    {"commit": {"author": {"date": "2026-10-12T09:00:00Z"}, "message": "x"}, "author": {"login": "ann"}},
                    {"commit": {"author": {"date": "2026-10-10T09:00:00Z"}, "message": "y"}, "author": {"login": "ann"}}]
        if url.endswith("/pulls"):
            return [{"number": 4, "title": "Add auth", "merged_at": "2026-10-11T01:00:00Z", "user": {"login": "ann"}},
                    {"number": 3, "title": "Old", "merged_at": "2026-08-01T01:00:00Z", "user": {"login": "ann"}},
                    {"number": 2, "title": "Closed unmerged", "merged_at": None, "user": {"login": "ann"}}]
        if "/app/installations/" in url:
            return {"account": {"login": "acme"}}
        raise AssertionError(url)


class Q:
    def __init__(self, store, name):
        self.store, self.name, self.op, self.payload = store, name, "select", None

    def select(self, *_):
        return self

    def insert(self, rows):
        self.op, self.payload = "insert", rows
        return self

    def delete(self):
        self.op = "delete"
        return self

    def __getattr__(self, _):
        return lambda *a, **k: self

    def execute(self):
        if self.op == "insert":
            self.store.setdefault("inserted", []).extend(self.payload)
        if self.op == "delete":
            self.store["deleted"] = self.store.get("deleted", 0) + 1
        return NS(data=self.store.get("existing", []) if self.op == "select" else None)


class SB:
    def __init__(self, existing=None):
        self.store = {"existing": existing or []}

    def table(self, name):
        return Q(self.store, name)


class GitHubAppTests(unittest.TestCase):
    def test_app_jwt_is_rs256_with_short_expiry(self):
        token = g.app_jwt("123", PEM, now=1_800_000_000)
        claims = jwt.decode(token, PUB, algorithms=["RS256"], options={"verify_exp": False, "verify_iat": False})
        self.assertEqual((claims["iss"], claims["exp"] - claims["iat"]), ("123", 600))

    def test_list_repos_follows_pagination_and_caches_the_token(self):
        http = FakeHTTP()
        app = g.GitHubApp("1", PEM, http=http)
        self.assertEqual(len(app.list_repos("9")), 102)
        app.list_repos("9")
        self.assertEqual(sum(1 for c in http.calls if c[1].endswith("/access_tokens")), 1)

    def test_backfill_groups_commits_by_day_and_skips_unmerged_or_old_prs(self):
        sb = SB(existing=[{"id": "old1", "meta": {"backfill": True}}, {"id": "live1", "meta": {"commits": 1}}])
        integ = {"startup_id": "s", "external_id": "9", "repos": ["a/web"], "selected_repos": None,
                 "created_at": "2026-10-13T11:00:00+00:00"}
        n = g.backfill_signals(g.GitHubApp("1", PEM, http=FakeHTTP()), sb, integ, now=datetime(2026, 10, 13, 12, tzinfo=timezone.utc))
        rows = sb.store["inserted"]
        self.assertEqual(n, 3)  # 2 commit-days + 1 merged PR
        self.assertEqual(sorted(r["meta"].get("commits", 0) for r in rows if r["type"] == "commit"), [1, 2])
        self.assertEqual([r["headline"] for r in rows if r["type"] == "pull_request"], ["PR #4 merged in a/web"])
        self.assertEqual(sb.store["deleted"], 1)  # only the earlier backfill row is replaced, never live signals

    def test_private_key_loaded_from_env(self):
        os.environ["GITHUB_APP_PRIVATE_KEY"] = PEM.replace("\n", "\n")
        os.environ["GITHUB_APP_ID"] = "1"
        try:
            self.assertTrue(g.configured())
            self.assertIn("BEGIN PRIVATE KEY", g.load_private_key())
        finally:
            del os.environ["GITHUB_APP_PRIVATE_KEY"], os.environ["GITHUB_APP_ID"]


if __name__ == "__main__":
    unittest.main()
