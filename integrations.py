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
# GitHub install links live longer: founders often come back to the same Slack button later, and an expired link
# left the app installed on GitHub but never linked to the startup. The state is still signed and names the founder.
GITHUB_LINK_TTL = 7 * 24 * 60 * 60
SIGNAL_TYPES = ("commit", "pull_request", "issue", "meeting")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def sign_state(payload: dict, secret: str, now: float | None = None, ttl: int = STATE_TTL_SECONDS) -> str:
    body = {**payload, "exp": int((now or time.time()) + ttl)}
    encoded = _b64(json.dumps(body, separators=(",", ":"), sort_keys=True).encode())
    sig = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{sig}"


DASHBOARD_LINK_TTL = 60 * 60  # single-use and short-lived; the Home tab makes a fresh one every time it opens


def dashboard_url(base: str | None, secret: str | None, founder_id: str | None,
                  slack_user_id: str | None = None) -> str | None:
    """
    Link for Slack's "Open dashboard" button: a signed, single-use pass (`k`) naming the person, valid for an hour.
    The website checks the person against the mentors/founders tables and signs them in; their role decides the view.
    Without a person (or a secret) it's the bare address, where they use Sign in with Slack instead.
    """
    if not base:
        return None
    who = slack_user_id or founder_id
    if not secret or not who:
        return base
    payload = {"f": who, "s": "dash", "p": "dash", "j": secrets.token_urlsafe(12)}
    if slack_user_id:
        payload["u"] = slack_user_id
    token = sign_state(payload, secret, ttl=DASHBOARD_LINK_TTL)
    return base + ("&" if "?" in base else "?") + "k=" + token

def github_connect_url(app_slug: str | None, secret: str | None, founder_id: str, startup_id: str) -> str | None:
    """Link to GitHub's install screen, or None when the GitHub App isn't configured."""
    if not (app_slug and secret):
        return None
    state = sign_state({"f": founder_id, "s": startup_id, "p": "github"}, secret, ttl=GITHUB_LINK_TTL)
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


GITHUB_TYPES = ("commit", "pull_request", "issue")


def monitored_for_startup(sb, startup_id: str) -> set:
    """Repos currently monitored across the startup's GitHub connections (follows the founder's latest choice)."""
    try:
        rows = (sb.table("integrations").select("repos,selected_repos").eq("startup_id", startup_id)
                .eq("provider", "github").execute().data) or []
    except Exception as e:  # noqa: BLE001
        print(f"[Activity Warning] {e}")
        rows = []
    return {repo for row in rows for repo in monitored_repos(row)}


def activity_summary(sb, startup_id: str, days: int = 7, now: datetime | None = None,
                     monitored: set | list | None = None) -> dict:
    """
    Counts of real work signals for a startup over the last `days` days. GitHub work only counts for the repos
    monitored right now: older signals from a repo the founder has since deselected are ignored, not deleted.
    """
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(days=days)).isoformat()
    try:
        rows = (sb.table("signals").select("type,meta,created_at").eq("startup_id", startup_id)
                .in_("type", list(SIGNAL_TYPES)).gte("created_at", since)
                .order("created_at", desc=True).limit(500).execute().data) or []
    except Exception as e:  # noqa: BLE001
        print(f"[Activity Warning] {e}")
        rows = []
    watched = set(monitored_for_startup(sb, startup_id) if monitored is None else monitored)
    return summarize_activity(rows, watched)


def recent_signals(sb, days: int = 7, now: datetime | None = None) -> list:
    """Every startup's work signals of the last `days` days in one query (newest first), for activity_from_rows."""
    now = now or datetime.now(timezone.utc)
    try:
        return (sb.table("signals").select("startup_id,type,meta,created_at").in_("type", list(SIGNAL_TYPES))
                .gte("created_at", (now - timedelta(days=days)).isoformat())
                .order("created_at", desc=True).limit(5000).execute().data) or []
    except Exception as e:  # noqa: BLE001
        print(f"[Activity Warning] {e}")
        return []


def activity_from_rows(signals: list, github_rows: list) -> dict:
    """{startup_id: activity_summary} from recent_signals and every GitHub integration row, with no further queries."""
    watched, by = {}, {}
    for g in github_rows:
        watched.setdefault(g.get("startup_id"), set()).update(monitored_repos(g))
    for r in signals:
        by.setdefault(r.get("startup_id"), []).append(r)
    return {sid: summarize_activity(rows, watched.get(sid, set())) for sid, rows in by.items()}


def summarize_activity(rows: list, watched: set) -> dict:
    """Counts from signal rows (newest first); GitHub rows only count for watched repos."""
    rows = [r for r in rows if r["type"] not in GITHUB_TYPES or (r.get("meta") or {}).get("repo") in watched]
    out = {"commits": 0, "prs_opened": 0, "prs_merged": 0, "issues_closed": 0, "meetings": 0, "external_meetings": 0,
           "last_activity": None, "signals": len(rows)}
    for r in rows:
        meta = r.get("meta") or {}
        if r["type"] == "commit":
            out["commits"] += int(meta.get("commits", 1))
        elif r["type"] == "pull_request":
            out["prs_merged" if meta.get("merged") else "prs_opened"] += 1
        elif r["type"] == "issue" and meta.get("action") == "closed":
            out["issues_closed"] += 1
        elif r["type"] == "meeting":
            out["meetings"] += int(meta.get("meetings", 0))
            out["external_meetings"] += int(meta.get("external", 0))
    out["last_activity"] = rows[0]["created_at"] if rows else None
    return out


def describe_work(r: dict, max_files: int = 10) -> str:
    """One GitHub signal as evidence: the headline, every commit message, what a PR says it does, and which files
    changed. Older signals (before the webhook stored messages and files) fall back to headline and detail."""
    meta = r.get("meta") or {}
    parts = [r.get("headline") or r.get("type") or "work"]
    if r.get("type") == "commit":
        msgs = meta.get("messages") or ([r["detail"]] if r.get("detail") else [])
        if msgs:
            parts.append("commits: " + "; ".join(str(m) for m in msgs[:15]))
    elif r.get("detail"):
        parts.append(str(r["detail"]))
    if meta.get("body"):
        parts.append(f"description: {meta['body']}")
    if isinstance(meta.get("changed_files"), int):
        parts.append(f"size: +{meta.get('additions', 0)}/-{meta.get('deletions', 0)} in {meta['changed_files']} files")
    files = [f for f in meta.get("files") or [] if isinstance(f, str)]
    if files:
        parts.append("files: " + ", ".join(files[:max_files]) + (f" (+{len(files) - max_files} more)" if len(files) > max_files else ""))
    return " · ".join(parts)


def activity_line(a: dict, connected: bool) -> str:
    """One line of real work signals: GitHub activity (if connected) plus calendar meetings (if shared)."""
    parts = []
    code = a["commits"] or a["prs_opened"] or a["prs_merged"] or a["issues_closed"]
    if not connected:
        parts.append("GitHub not connected")
    elif not code:
        parts.append("GitHub connected, no activity in the last 7 days")
    else:
        parts.append(f"{a['commits']} commits, {a['prs_opened']} PRs opened, {a['prs_merged']} PRs merged, "
                     f"{a['issues_closed']} issues closed (last 7 days)")
    if a.get("meetings"):
        parts.append(f"{a['meetings']} meetings, {a['external_meetings']} with people outside the team (last 7 days)")
    return "; ".join(parts)


def google_connections(sb, startup_id: str) -> list:
    try:
        return (sb.table("integrations").select("id,account,founder_id,founders(name)")
                .eq("startup_id", startup_id).eq("provider", "google").order("created_at").execute().data) or []
    except Exception as e:  # noqa: BLE001
        print(f"[Integrations Warning] {e}")
        return []


def monitored_repos(row: dict) -> list:
    """What the bot watches: only what the founder chose. A single granted repo needs no choosing."""
    chosen = list(row.get("selected_repos") or [])
    granted = list(row.get("repos") or [])
    return chosen or (granted if len(granted) == 1 else [])


def match_repos(wanted: list, granted: list) -> dict:
    """
    Resolve what a founder typed ("bazi", "acme/app") against the repos shared with the app.
    Returns {"chosen": [...], "ambiguous": [(text, [candidates])], "missing": [text]}.
    """
    chosen, ambiguous, missing = [], [], []
    for raw in wanted or []:
        text = str(raw).strip().lower().strip("/ ")
        if not text:
            continue
        exact = [g for g in granted if g.lower() == text or g.lower().split("/")[-1] == text]
        hits = exact or [g for g in granted if text in g.lower()]
        if len(hits) == 1:
            if hits[0] not in chosen:
                chosen.append(hits[0])
        elif hits:
            ambiguous.append((raw, hits))
        else:
            missing.append(raw)
    return {"chosen": chosen, "ambiguous": ambiguous, "missing": missing}


NO_REPO = "__none__"


def _option(repo: str) -> dict:
    return {"text": {"type": "plain_text", "text": repo[:75]}, "value": repo[:75]}


def empty_slots(row: dict, extra: int = 0) -> int:
    """How many empty 'Select repo N' rows to show: one to start with, more as the founder presses the plus, never more than there are repos left."""
    repos = list(row.get("repos") or [])
    chosen = [r for r in monitored_repos(row) if r in repos]
    return min(max(extra, 1 if not chosen else 0), len(repos) - len(chosen))


def build_repo_slots(row: dict, headline: str, extra: int = 0, more: dict | None = None) -> list:
    """
    The headline, then one row per tracked repository ("Repo 1 v", "Repo 2 v") and empty "Select repo N v" rows, each a dropdown
    of the repositories shared with the app. The last row has a plus button that opens the next row. When every shared
    repository is already showing, `more` (a button: share more on GitHub, or ask the founder to) takes the plus's place.
    """
    repos = list(row.get("repos") or [])
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": headline}}]
    if not repos:
        return blocks + ([{"type": "actions", "block_id": f"slot_{row['id']}_more", "elements": [more]}] if more else [])
    chosen = [r for r in monitored_repos(row) if r in repos]
    empty = empty_slots(row, extra)
    total = len(chosen) + empty
    for i in range(total):
        current = chosen[i] if i < len(chosen) else None
        options = [_option(r) for r in repos if r == current or r not in chosen][:98]
        if current and len(repos) > 1:
            options.insert(0, {"text": {"type": "plain_text", "text": "✕ Stop tracking this one"}, "value": NO_REPO})
        if current and current[:75] not in {o["value"] for o in options}:
            options.insert(0, _option(current))
        element = {"type": "static_select", "action_id": "repo_slot", "options": options,
                   "placeholder": {"type": "plain_text", "text": f"Select repo {i + 1}"}}
        if current:
            element["initial_option"] = _option(current)
        elements = [element]
        if i == total - 1 and len(repos) - len(chosen) > empty:
            elements.append({"type": "button", "text": {"type": "plain_text", "text": "➕", "emoji": True},
                             "action_id": "add_repo_slot", "value": row["id"]})
        elif i == total - 1 and more:
            elements.append(more)
        blocks.append({"type": "actions", "block_id": f"slot_{row['id']}_{i}", "elements": elements})
    return blocks


def keep_implicit_choice(before: tuple | None, row: dict) -> list | None:
    """
    A founder who shared exactly one repository is tracked without choosing. When they later share more, that one repository
    would silently stop being tracked (several shared and none chosen). Returns [that repository] so tracking carries on.
    """
    if not before:
        return None
    old_repos, old_selected = before
    now = list(row.get("repos") or [])
    if len(old_repos) == 1 and not old_selected and not row.get("selected_repos") and len(now) >= 2 and old_repos[0] in now:
        return [old_repos[0]]
    return None


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
