"""
Scheduling meetings through the Slack bot (pure helpers, no I/O).

A request ("set up a meet with everyone at 3pm on Thursday, at 111 Somerset") becomes a proposal the requester confirms;
only then does the bot create the Google Calendar event on the shared studio calendar and email the invitations.
Times are Singapore time and are always shown in 12-hour AM/PM format.
"""

import re
import secrets
from datetime import date, datetime, timedelta, timezone

SGT = timezone(timedelta(hours=8))
GROUPS = {"everyone", "everybody", "all", "cohort", "mentors", "founders"}
RECURRENCE = {"weekly": "RRULE:FREQ=WEEKLY", "fortnightly": "RRULE:FREQ=WEEKLY;INTERVAL=2", "monthly": "RRULE:FREQ=MONTHLY"}


def parse_when(day: str, start: str, minutes: int = 60) -> tuple[datetime, datetime] | None:
    """YYYY-MM-DD + HH:MM (24h) -> aware start/end in SGT, or None if it isn't a valid date and time."""
    try:
        d = date.fromisoformat(str(day)[:10])
        h, m = [int(x) for x in str(start).split(":")[:2]]
        begin = datetime(d.year, d.month, d.day, h, m, tzinfo=SGT)
    except (ValueError, TypeError):
        return None
    return begin, begin + timedelta(minutes=max(15, min(int(minutes or 60), 480)))


def time_12h(dt: datetime) -> str:
    """3:00 PM, never 15:00."""
    return dt.strftime("%I:%M %p").lstrip("0")


def format_when(begin: datetime, end: datetime) -> str:
    return f"{begin.strftime('%A, %b')} {begin.day} · {time_12h(begin)}–{time_12h(end)} (SGT)"


def resolve_attendees(specs: list, founders: list, mentors: list, requester_slack_id: str, requester_role: str) -> dict:
    """
    specs: strings from the model: a group ('everyone', 'mentors', 'founders'), a Slack id/mention ('U123ABC', '<@U123ABC>'),
    or a person's name. founders/mentors: rows with name, email, slack_user_id.
    Returns {people: [{name, email}], missing: [names without a known email/match], error: str|None}.
    Founders may invite people, but only mentors may call everyone or whole groups.
    """
    everyone = [{"name": r["name"], "email": r.get("email"), "slack": r.get("slack_user_id"), "role": "mentor"} for r in mentors] + \
               [{"name": r["name"], "email": r.get("email"), "slack": r.get("slack_user_id"), "role": "founder"} for r in founders]
    chosen: dict = {}
    missing: list = []

    def add(p):
        if p.get("email"):
            chosen.setdefault(p["email"].lower(), {"name": p["name"], "email": p["email"]})
        else:
            missing.append(p["name"])

    for raw in specs or []:
        spec = str(raw).strip()
        key = spec.lower().strip("<>@ ")
        if key in GROUPS:
            if requester_role != "mentor":
                return {"people": [], "missing": [], "error": "Only mentors can invite everyone or a whole group. Name the people you want to meet instead."}
            for p in everyone:
                if key in ("everyone", "everybody", "all", "cohort") or p["role"] + "s" == key:
                    add(p)
            continue
        slack_id = re.sub(r"[<@>|].*$", "", spec.lstrip("<@")) if spec.startswith("<@") else spec
        matches = [p for p in everyone if p["slack"] and p["slack"].lower() == slack_id.lower()]
        if not matches:
            matches = [p for p in everyone if p["name"].lower() == key] or \
                      [p for p in everyone if key and (key in p["name"].lower() or p["name"].lower().split()[0] == key)]
        if len(matches) == 1:
            add(matches[0])
        elif len(matches) > 1:
            missing.append(f"{spec} (which one? {', '.join(m['name'] for m in matches)})")
        else:
            missing.append(spec)
    return {"people": list(chosen.values()), "missing": missing, "error": None}


def build_event_body(title: str, begin: datetime, end: datetime, where: str, attendees: list, description: str,
                     repeat: str | None = None) -> dict:
    """Google Calendar event: 'virtual' gets a Meet link, anything else is the location text."""
    body = {
        "summary": title[:200], "description": description[:1000],
        "start": {"dateTime": begin.isoformat(), "timeZone": "Asia/Singapore"},
        "end": {"dateTime": end.isoformat(), "timeZone": "Asia/Singapore"},
        "attendees": [{"email": a["email"]} for a in attendees],
        "reminders": {"useDefault": True},
        "extendedProperties": {"private": {"ventureos": "1"}},  # lets the bot find ITS meetings and nothing else
    }
    if (where or "virtual").strip().lower() in ("virtual", "virtually", "online", "remote", "zoom", "meet", "google meet"):
        body["conferenceData"] = {"createRequest": {"requestId": secrets.token_hex(8),
                                                    "conferenceSolutionKey": {"type": "hangoutsMeet"}}}
    else:
        body["location"] = where[:200]
    if repeat in RECURRENCE:
        body["recurrence"] = [RECURRENCE[repeat]]
    return body


def is_virtual(where: str) -> bool:
    return (where or "virtual").strip().lower() in ("virtual", "virtually", "online", "remote", "zoom", "meet", "google meet")


def describe_event(ev: dict, show_attendees: bool) -> str:
    """One line for an event on the studio calendar: when (12-hour), title, where, and who (mentors only see names)."""
    start = ev.get("start", {})
    stamp = start.get("dateTime")
    if stamp:
        begin = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(SGT)
        end_stamp = (ev.get("end") or {}).get("dateTime")
        end = datetime.fromisoformat(end_stamp.replace("Z", "+00:00")).astimezone(SGT) if end_stamp else None
        when = f"{begin.strftime('%a %b')} {begin.day}, {time_12h(begin)}" + (f"–{time_12h(end)}" if end else "")
    else:
        when = start.get("date", "")
    where = ev.get("location") or ("Google Meet" if ev.get("hangoutLink") else "")
    who = ""
    if show_attendees:
        names = [a.get("displayName") or a.get("email", "") for a in (ev.get("attendees") or []) if not a.get("self")]
        who = f" · with {', '.join(names[:8])}" + (f" and {len(names) - 8} more" if len(names) > 8 else "") if names else ""
    return f"- {when}: {ev.get('summary', '(no title)')}" + (f" ({where})" if where else "") + who


def visible_to(ev: dict, email: str | None, is_mentor: bool) -> bool:
    """Mentors see every studio-calendar meeting; a founder only sees the ones they are invited to."""
    if is_mentor:
        return True
    return bool(email) and any((a.get("email") or "").lower() == email.lower() for a in (ev.get("attendees") or []))
