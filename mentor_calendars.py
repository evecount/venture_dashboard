"""
Mentors' own Google Calendars (read-only), so the bot knows when mentors are busy and the dashboard can show it.

- Each mentor connects their calendar themselves (Home tab button). This is separate from the shared studio
  calendar and never changes it.
- Events are copied into `mentor_events` every 10 minutes for the next two weeks. Titles are kept and shown to
  other mentors (never to founders); events the mentor marked private in Google are kept as plain "Busy".
- The refresh token is Fernet-encrypted with STATE_SECRET, like every other Google connection.
"""

from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import urlencode

import google_calendar
import integrations

SGT = timezone(timedelta(hours=8))
SYNC_DAYS = 14
DAY_START, DAY_END = time(9, 0), time(18, 0)  # the window used to suggest free times


# ---------- connecting ----------

def connect_url(client_id: str | None, redirect_uri: str | None, secret: str | None, slack_id: str) -> str | None:
    """Google's consent screen for read-only calendar access, with a signed state naming the mentor."""
    if not (client_id and redirect_uri and secret and slack_id):
        return None
    state = integrations.sign_state({"f": slack_id, "s": "mentor", "p": "google-mentor"}, secret)
    return google_calendar.AUTH_URL + "?" + urlencode({
        "client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": google_calendar.SCOPES,
        "access_type": "offline", "prompt": "consent", "state": state, "include_granted_scopes": "true",
    })


def save_connection(sb, slack_id: str, got: dict, secret: str) -> None:
    """Stores (or replaces) this mentor's own calendar connection. Raises if Google gave no refresh token."""
    if not got.get("refresh_token"):
        raise RuntimeError("Google returned no refresh token")
    sb.table("mentor_calendars").upsert({
        "slack_user_id": slack_id, "account": got.get("email") or "",
        "refresh_token": google_calendar.encrypt_token(got["refresh_token"], secret),
        "connected_at": datetime.now(timezone.utc).isoformat(),
    }).execute()


def disconnect(sb, slack_id: str) -> None:
    sb.table("mentor_events").delete().eq("slack_user_id", slack_id).execute()
    sb.table("mentor_calendars").delete().eq("slack_user_id", slack_id).execute()


def connection(sb, slack_id: str) -> dict | None:
    try:
        rows = sb.table("mentor_calendars").select("slack_user_id,account,connected_at").eq("slack_user_id", slack_id).execute().data
        return rows[0] if rows else None
    except Exception as e:  # noqa: BLE001 - table may not exist yet
        print(f"[Mentor Calendar Warning] {e}")
        return None


# ---------- syncing ----------

def _private(ev: dict) -> bool:
    return (ev.get("visibility") or "").lower() in ("private", "confidential")


def event_rows(slack_id: str, events: list, now: datetime | None = None) -> list:
    """Google events -> `mentor_events` rows. Skips cancelled events and ones the mentor declined or is free for."""
    now = now or datetime.now(timezone.utc)
    rows = []
    for ev in events:
        if ev.get("status") == "cancelled" or not ev.get("id"):
            continue
        if (ev.get("transparency") or "") == "transparent":
            continue  # marked "Free" in Google: doesn't block time
        me = next((a for a in (ev.get("attendees") or []) if a.get("self")), None)
        if me and me.get("responseStatus") == "declined":
            continue
        start, end = ev.get("start") or {}, ev.get("end") or {}
        all_day = "dateTime" not in start
        if all_day and not start.get("date"):
            continue
        rows.append({
            "id": f"{slack_id}:{ev['id']}",
            "event_id": ev["id"],
            "slack_user_id": slack_id,
            "title": "Busy" if _private(ev) else (ev.get("summary") or "Busy")[:200],
            "busy_only": _private(ev),
            "all_day": all_day,
            "starts_at": start.get("dateTime") or f"{start['date']}T00:00:00+08:00",
            "ends_at": end.get("dateTime") or (f"{end['date']}T00:00:00+08:00" if end.get("date") else None),
            "synced_at": now.isoformat(),
        })
    return rows


def sync_one(sb, gcal, row: dict, now: datetime | None = None) -> int:
    """Replaces this mentor's upcoming window with what's on their calendar now."""
    now = now or datetime.now(timezone.utc)
    events = gcal.events(row["refresh_token"], now - timedelta(hours=12), now + timedelta(days=SYNC_DAYS))
    rows = event_rows(row["slack_user_id"], events, now)
    sb.table("mentor_events").delete().eq("slack_user_id", row["slack_user_id"]).execute()
    if rows:
        sb.table("mentor_events").upsert(rows).execute()
    return len(rows)


def sync_all(sb, gcal) -> int:
    if not (sb and gcal):
        return 0
    try:
        rows = sb.table("mentor_calendars").select("*").execute().data or []
    except Exception as e:  # noqa: BLE001 - table may not exist yet
        print(f"[Mentor Calendar Sync Warning] {e}")
        return 0
    total = 0
    for row in rows:
        try:
            total += sync_one(sb, gcal, row)
        except Exception as e:  # noqa: BLE001 - one mentor's revoked token must not stop the others
            print(f"[Mentor Calendar Sync Warning] {row.get('slack_user_id')}: {e}")
    return total


# ---------- availability ----------

def _dt(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(SGT)


def busy_blocks(sb, slack_ids: list, begin: datetime, end: datetime) -> list:
    """[{slack_user_id, title, busy_only, all_day, begin, end}] for these mentors overlapping [begin, end)."""
    if not (sb and slack_ids):
        return []
    try:
        rows = (sb.table("mentor_events").select("slack_user_id,event_id,title,busy_only,all_day,starts_at,ends_at")
                .in_("slack_user_id", list(slack_ids)).lt("starts_at", end.isoformat())
                .gte("ends_at", begin.isoformat()).execute().data) or []
    except Exception as e:  # noqa: BLE001
        print(f"[Mentor Calendar Warning] {e}")
        return []
    out = []
    for r in rows:
        b, e = _dt(r["starts_at"]), _dt(r["ends_at"]) if r.get("ends_at") else _dt(r["starts_at"]) + timedelta(hours=1)
        if b < end and begin < e:
            out.append({**r, "begin": b, "end": e})
    return sorted(out, key=lambda x: x["begin"])


def free_slots(blocks: list, day: date, minutes: int = 60, limit: int = 3) -> list:
    """
    Up to `limit` start times on `day` (9 am-6 pm SGT, on the half hour) when nobody in `blocks` is busy. Suggestions
    are at least one meeting-length apart, so they're real alternatives rather than 9:00, 9:30, 10:00.
    """
    start = datetime.combine(day, DAY_START, SGT)
    stop = datetime.combine(day, DAY_END, SGT)
    length = timedelta(minutes=max(15, minutes))
    out, t = [], start
    while t + length <= stop and len(out) < limit:
        if not any(b["begin"] < t + length and t < b["end"] for b in blocks if not b.get("all_day")):
            out.append(t)
            t += length
        else:
            t += timedelta(minutes=30)
    return out


def clash_lines(blocks: list, names: dict, show_titles: bool) -> list:
    """Human lines like 'Arthur Andre Pandaan: Board call 3:00-4:00 pm'. Titles only for mentors asking."""
    lines = []
    for b in blocks:
        who = names.get(b["slack_user_id"], "A mentor")
        what = b["title"] if show_titles and not b.get("busy_only") else "busy"
        when = "all day" if b.get("all_day") else f"{_clock(b['begin'])}–{_clock(b['end'])}"
        lines.append(f"{who}: {what} ({when})")
    return lines


def _clock(dt: datetime) -> str:
    return dt.strftime("%I:%M %p").lstrip("0").lower()
