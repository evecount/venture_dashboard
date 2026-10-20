"""
Copies upcoming studio-calendar meetings into the `studio_events` table so the dashboard can show them.

The Google refresh token stays on the bot's VM (encrypted); the website only ever reads this table through its own
server. Only the bot's own events are copied (the same rule as everywhere else: never read anyone's other calendar
events), and attendee emails are kept so the dashboard can show founders only the meetings they're invited to.
"""

import re
from datetime import datetime, timedelta, timezone

WINDOW_DAYS = 30


def _meet_url(ev: dict) -> str | None:
    loc = ev.get("location") or ""
    link = ev.get("hangoutLink") or (loc if "meet.google.com" in loc else None)
    # The location is free text anyone setting up a meeting can type: only a real https Meet link becomes a link.
    return link if link and re.fullmatch(r"https://meet\.google\.com/[A-Za-z0-9_?=&./-]+", link) else None


def event_rows(events: list, now: datetime | None = None) -> list:
    """Google Calendar events -> `studio_events` rows. Skips cancelled and all-day events (no time to show)."""
    now = now or datetime.now(timezone.utc)
    rows = []
    for ev in events:
        start, end = (ev.get("start") or {}).get("dateTime"), (ev.get("end") or {}).get("dateTime")
        if ev.get("status") == "cancelled" or not start or not ev.get("id"):
            continue
        meet = _meet_url(ev)
        loc = ev.get("location") or ""
        rows.append({
            "id": ev["id"],
            "title": (ev.get("summary") or "Meeting")[:200],
            "starts_at": start,
            "ends_at": end,
            "location": None if meet and loc == meet else (loc[:200] or None),
            "meet_url": meet,
            "attendees": [
                {"name": a.get("displayName") or "", "email": (a.get("email") or "").lower(),
                 "response": a.get("responseStatus") or ""}
                for a in (ev.get("attendees") or []) if not a.get("self") and a.get("email")
            ],
            "synced_at": now.isoformat(),
        })
    return rows


def sync(sb, events: list | None, now: datetime | None = None) -> int:
    """
    Replaces the upcoming window in `studio_events` with what's on the calendar now, so moved or cancelled meetings
    disappear too. `events=None` means the calendar isn't connected: leave the table alone. Returns rows written.
    """
    if events is None or not sb:
        return 0
    now = now or datetime.now(timezone.utc)
    rows = event_rows(events, now)
    try:
        sb.table("studio_events").delete().gte("starts_at", (now - timedelta(hours=12)).isoformat()).execute()
        if rows:
            sb.table("studio_events").upsert(rows).execute()
        # Keep a little history for the dashboard, not forever.
        sb.table("studio_events").delete().lt("starts_at", (now - timedelta(days=60)).isoformat()).execute()
    except Exception as e:  # noqa: BLE001 - the table may not exist yet; the dashboard just shows no meetings
        print(f"[Studio Events Sync Warning] {e}")
        return 0
    return len(rows)


# ---------- keeping the shared studio calendar on one account ----------

def can_reconnect_studio(row: dict | None, slack_id: str, developer: bool) -> bool:
    """Connecting or reconnecting the shared studio calendar is a developer-only action (DEV_EMAILS)."""
    return developer


def studio_account_refusal(row: dict | None, new_email: str | None) -> str | None:
    """
    Why a studio-calendar connection must be refused, or None if it's fine. Reconnecting the same account is allowed
    (e.g. to grant a new permission); switching to a different account is not, because every meeting booked on the
    current account would drop out of the bot and the dashboard, and new invitations would come from someone's
    personal address.
    """
    current = (row or {}).get("account")
    if not current or not new_email:
        return None
    if new_email.strip().lower() == str(current).strip().lower():
        return None
    return (f"The studio calendar is *{current}*, so I kept it. You signed in as {new_email}. To reconnect it, sign in "
            f"with {current}. Moving the studio calendar to another account is a deliberate change: ask the developer.")
