"""
Copies upcoming studio-calendar meetings into the `studio_events` table so the dashboard can show them.

The Google refresh token stays on the bot's VM (encrypted); the website only ever reads this table through its own
server. Only the bot's own events are copied (the same rule as everywhere else: never read anyone's other calendar
events), and attendee emails are kept so the dashboard can show founders only the meetings they're invited to.
"""

from datetime import datetime, timedelta, timezone

WINDOW_DAYS = 30


def _meet_url(ev: dict) -> str | None:
    loc = ev.get("location") or ""
    return ev.get("hangoutLink") or (loc if "meet.google.com" in loc else None)


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
