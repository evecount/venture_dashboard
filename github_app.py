"""
GitHub App API access (needs the app's private key): list the repos a founder granted on demand, and backfill recent
activity so a newly connected startup doesn't look empty. Read-only: the app only has read permissions anyway.

Config: GITHUB_APP_ID + either GITHUB_APP_PRIVATE_KEY_PATH (a .pem file) or GITHUB_APP_PRIVATE_KEY (the PEM text).
HTTP is injectable so everything here is testable offline.
"""

import os
import time
from datetime import datetime, timedelta, timezone

import jwt  # PyJWT, RS256 via cryptography

API = "https://api.github.com"
BACKFILL_DAYS = 14


def load_private_key() -> str | None:
    inline = os.environ.get("GITHUB_APP_PRIVATE_KEY")
    if inline:
        return inline.replace("\\n", "\n")
    path = os.environ.get("GITHUB_APP_PRIVATE_KEY_PATH")
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return None


def configured() -> bool:
    return bool(os.environ.get("GITHUB_APP_ID") and load_private_key())


def app_jwt(app_id: str, private_key: str, now: float | None = None) -> str:
    """Short-lived JWT proving we are the app (GitHub caps it at 10 minutes)."""
    now = int(now or time.time())
    return jwt.encode({"iat": now - 60, "exp": now + 540, "iss": str(app_id)}, private_key, algorithm="RS256")


def _default_http(method: str, url: str, headers: dict, params: dict | None = None):
    import requests
    r = requests.request(method, url, headers=headers, params=params, timeout=20)
    r.raise_for_status()
    return r.json()


class GitHubApp:
    def __init__(self, app_id: str, private_key: str, http=_default_http):
        self.app_id, self.key, self.http = app_id, private_key, http
        self._tokens: dict = {}  # installation_id -> (token, expires_epoch)

    @classmethod
    def from_env(cls):
        return cls(os.environ["GITHUB_APP_ID"], load_private_key()) if configured() else None

    def _headers(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}

    def installation_token(self, installation_id: str) -> str:
        cached = self._tokens.get(installation_id)
        if cached and cached[1] > time.time() + 60:
            return cached[0]
        data = self.http("POST", f"{API}/app/installations/{installation_id}/access_tokens",
                         self._headers(app_jwt(self.app_id, self.key)))
        expires = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00")).timestamp()
        self._tokens[installation_id] = (data["token"], expires)
        return data["token"]

    def account(self, installation_id: str) -> str | None:
        data = self.http("GET", f"{API}/app/installations/{installation_id}", self._headers(app_jwt(self.app_id, self.key)))
        return (data.get("account") or {}).get("login")

    def installation_for(self, login: str) -> dict | None:
        """The app's installation on an organisation or user account, or None if the app isn't installed there (yet)."""
        for kind in ("orgs", "users"):
            try:
                data = self.http("GET", f"{API}/{kind}/{login}/installation", self._headers(app_jwt(self.app_id, self.key)))
                return {"id": str(data["id"]), "account": (data.get("account") or {}).get("login", login)}
            except Exception:  # noqa: BLE001 - 404 means not installed / not that kind of account
                continue
        return None

    def list_repos(self, installation_id: str) -> list:
        """Every repository the founder granted (follows pagination)."""
        token, repos, page = self.installation_token(installation_id), [], 1
        while True:
            data = self.http("GET", f"{API}/installation/repositories", self._headers(token), {"per_page": 100, "page": page})
            repos += [r["full_name"] for r in data.get("repositories", [])]
            if len(data.get("repositories", [])) < 100:
                return repos
            page += 1

    def commits(self, installation_id: str, repo: str, since: datetime, until: datetime) -> list:
        token = self.installation_token(installation_id)
        return self.http("GET", f"{API}/repos/{repo}/commits", self._headers(token),
                         {"since": since.isoformat(), "until": until.isoformat(), "per_page": 100})

    def merged_prs(self, installation_id: str, repo: str, since: datetime) -> list:
        token = self.installation_token(installation_id)
        prs = self.http("GET", f"{API}/repos/{repo}/pulls", self._headers(token),
                        {"state": "closed", "sort": "updated", "direction": "desc", "per_page": 50})
        return [p for p in prs if p.get("merged_at") and datetime.fromisoformat(p["merged_at"].replace("Z", "+00:00")) >= since]


def backfill_signals(gh: GitHubApp, sb, integration: dict, now: datetime | None = None) -> int:
    """
    Writes one 'commit' signal per day and one 'pull_request' signal per merged PR for the last BACKFILL_DAYS,
    for the repos being monitored, up to the moment of connection (live webhooks cover everything after).
    Re-running replaces earlier backfill rows instead of duplicating them. Returns signals written.
    """
    now = now or datetime.now(timezone.utc)
    connected_at = datetime.fromisoformat(integration["created_at"].replace("Z", "+00:00"))
    since = now - timedelta(days=BACKFILL_DAYS)
    repos = list(integration.get("selected_repos") or integration.get("repos") or [])
    startup_id, installation_id = integration["startup_id"], integration["external_id"]

    old = (sb.table("signals").select("id,meta").eq("startup_id", startup_id).in_("type", ["commit", "pull_request"])
           .gte("created_at", since.isoformat()).limit(1000).execute().data) or []
    stale = [r["id"] for r in old if (r.get("meta") or {}).get("backfill")]
    for sid in stale:
        sb.table("signals").delete().eq("id", sid).execute()

    rows = []
    for repo in repos:
        per_day: dict = {}
        for c in gh.commits(installation_id, repo, since, connected_at):
            stamp = ((c.get("commit") or {}).get("author") or {}).get("date")
            if stamp:
                per_day.setdefault(stamp[:10], []).append(c)
        for day, items in per_day.items():
            n = len(items)
            author = ((items[0].get("author") or {}).get("login")) or "someone"
            rows.append({
                "startup_id": startup_id, "type": "commit", "stream": "Tech", "actor": author,
                "headline": f"{n} commit{'s' if n != 1 else ''} to {repo} on {day}",
                "detail": str(((items[0].get("commit") or {}).get("message") or "")).split(chr(10))[0][:140],
                "created_at": f"{day}T12:00:00+00:00", "meta": {"commits": n, "repo": repo, "backfill": True},
            })
        for pr in gh.merged_prs(installation_id, repo, since):
            rows.append({
                "startup_id": startup_id, "type": "pull_request", "stream": "Tech",
                "actor": (pr.get("user") or {}).get("login") or "someone",
                "headline": f"PR #{pr['number']} merged in {repo}", "detail": str(pr.get("title", ""))[:140],
                "created_at": pr["merged_at"], "meta": {"action": "closed", "merged": True, "repo": repo, "backfill": True},
            })
    if rows:
        sb.table("signals").insert(rows).execute()
    return len(rows)
