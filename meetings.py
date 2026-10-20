"""
Scheduling meetings through the Slack bot (pure helpers, no I/O).

A request ("set up a meet with everyone at 3pm on Thursday, at 111 Somerset") becomes a proposal the requester confirms;
only then does the bot create the Google Calendar event on the shared studio calendar and email the invitations.
Times are Singapore time and are always shown in 12-hour AM/PM format.
"""

import re
import secrets
from datetime import date, datetime, timedelta, timezone
from timeparse import parse_ts

SGT = timezone(timedelta(hours=8))
GROUPS = {"everyone", "everybody", "all", "cohort", "mentors", "founders"}
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
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


def emails_in(text: str) -> list:
    """Email addresses written in a message, including Slack's <mailto:a@b.com|a@b.com> form, without repeats."""
    seen: dict = {}
    for e in EMAIL_RE.findall(text or ""):
        seen.setdefault(e.lower(), e)
    return list(seen.values())


def resolve_attendees(specs: list, founders: list, mentors: list, requester_slack_id: str, requester_role: str,
                      known_emails: list | None = None) -> dict:
    """
    specs: strings from the model: a group ('everyone', 'mentors', 'founders'), a Slack id/mention ('U123ABC', '<@U123ABC>'),
    or a person's name. founders/mentors: rows with name, email, slack_user_id.
    Returns {people: [{name, email}], missing: [names without a known email/match], error: str|None}.
    Founders may invite people, but only mentors may call everyone or whole groups.
    Mentors may also invite someone outside the cohort by email: either the spec is the address, or the person's name
    matches the start of an address the mentor wrote in the conversation (`known_emails`, e.g. "James" + james@x.com).
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
        typed = emails_in(spec)
        if typed:
            if requester_role == "mentor":
                address = typed[0]
                chosen.setdefault(address.lower(), {"name": spec.split("<")[0].strip() or address.split("@")[0].title(), "email": address})
            else:
                missing.append(f"{typed[0]} (only mentors can invite people outside the cohort)")
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
            first = key.split()[0] if key.split() else ""
            outside = [e for e in (known_emails or []) if first and e.split("@")[0].lower().startswith(first)]
            if requester_role == "mentor" and len(outside) == 1:
                chosen.setdefault(outside[0].lower(), {"name": spec.title(), "email": outside[0]})
            else:
                missing.append(spec)
    return {"people": list(chosen.values()), "missing": missing, "error": None}


def build_event_body(title: str, begin: datetime, end: datetime, where: str, attendees: list, description: str,
                     repeat: str | None = None, requester_slack: str | None = None,
                     meet_link: str | None = None, studio_wide: bool = False) -> dict:
    """Google Calendar event: 'virtual' gets a Meet link, anything else is the location text."""
    body = {
        "summary": title[:200], "description": description[:1000],
        "start": {"dateTime": begin.isoformat(), "timeZone": "Asia/Singapore"},
        "end": {"dateTime": end.isoformat(), "timeZone": "Asia/Singapore"},
        "attendees": [{"email": a["email"]} for a in attendees],
        "reminders": {"useDefault": True},
        "extendedProperties": {"private": {"ventureos": "1", **({"requester": requester_slack} if requester_slack else {})}},  # lets the bot find ITS meetings and nothing else
    }
    if studio_wide:  # a calendar note with no invitees: everyone in the cohort can see it
        body["extendedProperties"]["private"]["studiowide"] = "1"
    if meet_link:  # an OPEN Meet room made through the Meet API: attach its link as the location
        body["location"] = meet_link
        body["description"] = (body["description"] + " Join: " + meet_link)[:1000]
    elif (where or "virtual").strip().lower() in ("virtual", "virtually", "online", "remote", "zoom", "meet", "google meet"):
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
        begin = parse_ts(stamp).astimezone(SGT)
        end_stamp = (ev.get("end") or {}).get("dateTime")
        end = parse_ts(end_stamp).astimezone(SGT) if end_stamp else None
        when = f"{begin.strftime('%a %b')} {begin.day}, {time_12h(begin)}" + (f"–{time_12h(end)}" if end else "")
    else:
        when = start.get("date", "")
    where = "Google Meet" if "meet.google.com" in (ev.get("location") or "") else (ev.get("location") or ("Google Meet" if ev.get("hangoutLink") else ""))
    who = ""
    if show_attendees:
        names = [a.get("displayName") or a.get("email", "") for a in (ev.get("attendees") or []) if not a.get("self")]
        who = f" · with {', '.join(names[:8])}" + (f" and {len(names) - 8} more" if len(names) > 8 else "") if names else ""
        rsvp = rsvp_summary(ev)
        who += f" · {rsvp}" if rsvp else ""
    return f"- {when}: {ev.get('summary', '(no title)')}" + (f" ({where})" if where else "") + who


def visible_to(ev: dict, email: str | None, is_mentor: bool) -> bool:
    """Mentors see every studio-calendar meeting; a founder only sees the ones they are invited to."""
    if is_mentor or ((ev.get("extendedProperties") or {}).get("private") or {}).get("studiowide") == "1":
        return True
    return bool(email) and any((a.get("email") or "").lower() == email.lower() for a in (ev.get("attendees") or []))


def day_label(d: date, today: date) -> str:
    if d == today:
        return "Today"
    if d == today + timedelta(days=1):
        return "Tomorrow"
    return f"{d.strftime('%a %b')} {d.day}"


def upcoming_item(ev: dict, today: date) -> tuple | None:
    """A real studio-calendar meeting as ((date, minute_of_day), line) for the 'Coming up' list, or None if it has no time."""
    stamp = (ev.get("start") or {}).get("dateTime")
    if not stamp:
        return None
    begin = parse_ts(stamp).astimezone(SGT)
    end_stamp = (ev.get("end") or {}).get("dateTime")
    end = parse_ts(end_stamp).astimezone(SGT) if end_stamp else None
    where = "Google Meet" if "meet.google.com" in (ev.get("location") or "") else (ev.get("location") or ("Google Meet" if ev.get("hangoutLink") else ""))
    span = time_12h(begin) + (f"–{time_12h(end)}" if end else "")
    line = f"👥 {day_label(begin.date(), today)}, {span}: *{ev.get('summary', 'Meeting')}*" + (f" · {where}" if where else "")
    return (begin.date(), begin.hour * 60 + begin.minute), line


# ---------- working with existing studio-calendar events ----------

def event_times(ev: dict) -> tuple | None:
    s_, e_ = (ev.get("start") or {}).get("dateTime"), (ev.get("end") or {}).get("dateTime")
    if not s_:
        return None
    begin = parse_ts(s_).astimezone(SGT)
    end = parse_ts(e_).astimezone(SGT) if e_ else begin + timedelta(hours=1)
    return begin, end


def rsvp_summary(ev: dict) -> str:
    """'✅ 3 yes · ❌ 1 no · ⏳ 2 waiting' for everyone invited except the organiser."""
    states = [(a.get("responseStatus") or "needsAction") for a in (ev.get("attendees") or []) if not a.get("self") and not a.get("organizer")]
    if not states:
        return ""
    yes, no = states.count("accepted"), states.count("declined")
    maybe = states.count("tentative")
    wait = len(states) - yes - no - maybe
    parts = [f"✅ {yes} yes", f"❌ {no} no"] + ([f"🤔 {maybe} maybe"] if maybe else []) + [f"⏳ {wait} waiting"]
    return " · ".join(parts)


def find_events(events: list, query: str) -> list:
    """Events whose title contains the query (case-insensitive). An empty query matches everything."""
    q = (query or "").strip().lower()
    return [e for e in events if q in (e.get("summary") or "").lower()]


def overlaps(begin: datetime, end: datetime, ev: dict) -> bool:
    t = event_times(ev)
    return bool(t) and begin < t[1] and t[0] < end


def can_change(ev: dict, slack_id: str, is_mentor: bool) -> bool:
    """Mentors can change any meeting the bot created; others only the ones they asked for."""
    if is_mentor:
        return True
    return ((ev.get("extendedProperties") or {}).get("private") or {}).get("requester") == slack_id


def reminder_due(ev: dict, now: datetime, from_minutes: int = 50, to_minutes: int = 65) -> bool:
    t = event_times(ev)
    if not t:
        return False
    delta = (t[0] - now).total_seconds() / 60
    return from_minutes <= delta <= to_minutes
