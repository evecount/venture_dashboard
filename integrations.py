"""
Real work signals: connecting a founder's GitHub (and, later, Google Calendar) and summarising what comes back.

Connection flow (GitHub App): the bot sends a link to GitHub's own install screen, where the founder picks
"all repositories" or "only select repositories". GitHub then redirects to our site, which verifies the signed `state`
below and links the installation to the startup. Webhooks then arrive as `signals` rows.
`state` is HMAC-signed (shared STATE_SECRET) so nobody can attach an installation to someone else's startup.
"""

import base64
import secrets
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

STATE_TTL_SECONDS = 60 * 60  # a connect link is valid for an hour
SIGNAL_TYPES = ("commit", "pull_request", "issue", "meeting")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def sign_state(payload: dict, secret: str, now: float | None = None, ttl: int = STATE_TTL_SECONDS) -> str:
    body = {**payload, "exp": int((now or time.time()) + ttl)}
    encoded = _b64(json.dumps(body, separators=(",", ":"), sort_keys=True).encode())
    sig = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{sig}"


DASHBOARD_LINK_TTL = 90 * 24 * 60 * 60  # a Slack dashboard link works for 90 days, on any device


def dashboard_url(base: str | None, secret: str | None, founder_id: str | None) -> str | None:
    """
    Link for Slack's "Open dashboard" button. It carries a signed personal pass (`k`) that skips the access code.
    Anyone who just pastes the bare dashboard address (no pass) still has to enter the code.
    """
    if not base:
        return None
    url = base
    if founder_id:
        url += ("&" if "?" in url else "?") + "as=" + quote(founder_id)
    if secret:
        token = sign_state({"f": founder_id or "mentor", "s": "dash", "p": "dash", "j": secrets.token_urlsafe(12)},
                           secret, ttl=DASHBOARD_LINK_TTL)
        url += ("&" if "?" in url else "?") + "k=" + token
    return url


def github_connect_url(app_slug: str | None, secret: str | None, founder_id: str, startup_id: str) -> str | None:
    """Link to GitHub's install screen, or None when the GitHub App isn't configured."""
    if not (app_slug and secret):
        return None
    state = sign_state({"f": founder_id, "s": startup_id, "p": "github"}, secret)
    return f"https://github.com/apps/{app_slug}/installations/new?state={state}"


def connections(sb, startup_id: str) -> dict:
    """{'github': {'account', 'repos'}} for the providers connected to this startup."""
    try:
        rows = sb.table("integrations").select("id,provider,account,repos,selected_repos").eq("startup_id", startup_id).execute().data or []
    except Exception as e:  # noqa: BLE001
        print(f"[Integrations Warning] {e}")
        return {}
    return {r["provider"]: r for r in rows}


def github_connections(sb, startup_id: str) -> list:
    """Every GitHub connection of a startup (co-founders may each have connected their own), with who connected it."""
    try:
        return (sb.table("integrations").select("id,account,repos,selected_repos,founder_id,founders(name)")
                .eq("startup_id", startup_id).eq("provider", "github").order("created_at").execute().data) or []
    except Exception as e:  # noqa: BLE001
        print(f"[Integrations Warning] {e}")
        return []


CLAIM_TTL_DAYS = 14


def open_claims(sb, now: datetime | None = None) -> list:
    """Organisation claims still waiting for an owner to approve the install."""
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(days=CLAIM_TTL_DAYS)).isoformat()
    try:
        return (sb.table("github_claims").select("*").is_("resolved_at", "null")
                .gte("created_at", since).execute().data) or []
    except Exception as e:  # noqa: BLE001
        print(f"[Claims Warning] {e}")
        return []


def valid_org_login(value: str) -> bool:
    """GitHub logins: letters, digits and single hyphens, up to 39 characters."""
    import re
    return bool(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}", (value or "").strip()))


def activity_summary(sb, startup_id: str, days: int = 7, now: datetime | None = None) -> dict:
    """Counts of real work signals for a startup over the last `days` days."""
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(days=days)).isoformat()
    try:
        rows = (sb.table("signals").select("type,meta,created_at").eq("startup_id", startup_id)
                .in_("type", list(SIGNAL_TYPES)).gte("created_at", since)
                .order("created_at", desc=True).limit(500).execute().data) or []
    except Exception as e:  # noqa: BLE001
        print(f"[Activity Warning] {e}")
        rows = []
    out = {"commits": 0, "prs_opened": 0, "prs_merged": 0, "issues_closed": 0, "last_activity": None, "signals": len(rows)}
    for r in rows:
        meta = r.get("meta") or {}
        if r["type"] == "commit":
            out["commits"] += int(meta.get("commits", 1))
        elif r["type"] == "pull_request":
            out["prs_merged" if meta.get("merged") else "prs_opened"] += 1
        elif r["type"] == "issue" and meta.get("action") == "closed":
            out["issues_closed"] += 1
    out["last_activity"] = rows[0]["created_at"] if rows else None
    return out


def activity_line(a: dict, connected: bool) -> str:
    if not connected:
        return "GitHub not connected"
    if not a["signals"]:
        return "GitHub connected, no activity in the last 7 days"
    return (f"{a['commits']} commits, {a['prs_opened']} PRs opened, {a['prs_merged']} PRs merged, "
            f"{a['issues_closed']} issues closed (last 7 days)")


def monitored_repos(row: dict) -> list:
    """What the bot watches: only what the founder chose. A single granted repo needs no choosing."""
    chosen = list(row.get("selected_repos") or [])
    granted = list(row.get("repos") or [])
    return chosen or (granted if len(granted) == 1 else [])


def build_repo_selector(row: dict, headline: str, compact: bool = False) -> list:
    """
    One section: the headline text with a multi-select of the granted repos beside it (the chosen ones preselected).
    Slack allows multi-selects as a section accessory in messages AND the Home tab, but not inside an actions block.
    """
    repos = list(row.get("repos") or [])
    block = {"type": "section", "text": {"type": "mrkdwn", "text": headline}}
    if len(repos) < 2:
        return [block]  # nothing to choose between
    options = [{"text": {"type": "plain_text", "text": r[:75]}, "value": r[:75]} for r in repos[:100]]
    chosen = set(row.get("selected_repos") or [])  # nothing is preselected: the founder picks deliberately
    initial = [o for o in options if o["value"] in chosen]
    element = {"type": "multi_static_select", "action_id": "select_repos", "options": options,
               "placeholder": {"type": "plain_text", "text": "Pick repository"}}
    if initial:
        element["initial_options"] = initial
    block["block_id"] = f"repos_{row['id']}"
    block["accessory"] = element
    return [block]


def connected_headline(row: dict, startup_name: str) -> str:
    repos = list(row.get("repos") or [])
    who = f" as *{row['account']}*" if row.get("account") else ""
    if not repos:
        return (f"✅ *GitHub connected*{who}, but I can't see any repositories. When you installed the app on GitHub, "
                "did you give it access to at least one? You can press Connect GitHub again to change that.")
    if len(repos) == 1:
        return f"✅ *GitHub connected*{who}. I'm monitoring *{repos[0]}* for {startup_name}. I only read commits, pull requests and issues."
    return (f"✅ *GitHub connected*{who}. I can see {len(repos)} repositories you granted. "
            f"*Which one is {startup_name}'s?* Pick it below (you can pick more than one). "
            "I won't track anything until you choose.")
