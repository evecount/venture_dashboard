"""
Cohorts and their fortnightly sprint sessions. Each cohort (MVP#1, MVP#2, ...) runs the same 12-week syllabus from
its own start Monday (`cohorts.start_date`); the sprint session is the Thursday of each sprint's second week
(weeks 2, 4, 6, ...). If the studio calendar has a sprint meeting that day, its real time and place win, so moving
or cancelling the meeting on the calendar changes what the bot tells people.
"""

from datetime import date, datetime, timedelta, timezone

import syllabus
from timeparse import parse_ts

SGT = timezone(timedelta(hours=8))
WEEKS = 12


def start_monday(start_date) -> date:
    """cohorts.start_date (timestamp or date) as the Monday of week 1, in Singapore time."""
    d = parse_ts(start_date).astimezone(SGT).date() if "T" in str(start_date) else date.fromisoformat(str(start_date)[:10])
    return d - timedelta(days=d.weekday())


def week_of(start: date, today: date, weeks: int = WEEKS) -> int | None:
    """Program week (1..weeks) on `today`; None before the start or after the end."""
    if today < start:
        return None
    w = (today - start).days // 7 + 1
    return w if w <= weeks else None


def sprint_sessions(start: date, weeks: int = WEEKS) -> list:
    """[{date, sprint, week}] for the Thursday of weeks 2, 4, 6, ..."""
    return [{"date": start + timedelta(weeks=w - 1, days=3), "sprint": w // 2, "week": w} for w in range(2, weeks + 1, 2)]


def next_sprint(start: date, today: date, weeks: int = WEEKS) -> dict | None:
    return next((s for s in sprint_sessions(start, weeks) if s["date"] >= today), None)


def _attendee_emails(ev: dict) -> set:
    return {(a.get("email") or "").lower() for a in ev.get("attendees") or [] if a.get("email")}


def calendar_match(session_day: date, events: list, emails: set | None = None) -> dict | None:
    """
    The studio-calendar meeting for a sprint session: a 'sprint' event on that day (Singapore time). With `emails`
    (the cohort's founders), an event that invites people must invite at least one of them: cohorts can share a
    Thursday, and one cohort's session isn't the other's. An event with no invitees counts for everyone.
    """
    for ev in events or []:
        title = (ev.get("summary") or ev.get("title") or "").lower()
        stamp = (ev.get("start") or {}).get("dateTime") if isinstance(ev.get("start"), dict) else ev.get("starts_at")
        if "sprint" not in title or not stamp:
            continue
        invited = _attendee_emails(ev)
        if emails is not None and invited and not (invited & {e.lower() for e in emails}):
            continue
        begin = parse_ts(stamp).astimezone(SGT)
        if begin.date() == session_day:
            return {"begin": begin, "where": ev.get("location") or "", "meet_url": ev.get("hangoutLink") or ev.get("meet_url"),
                    "title": ev.get("summary") or ev.get("title")}
    return None


def describe_session(s: dict, match: dict | None) -> str:
    """'Thu 29 Oct, 11:00 AM at 111 Somerset (Sprint 1 review)' or '... time not on the studio calendar yet'."""
    day = f"{s['date'].strftime('%a')} {s['date'].day} {s['date'].strftime('%b')}"
    label = f"Sprint {s['sprint']} session"
    if not match:
        return f"{label}: {day} (not on the studio calendar yet, so no time or place confirmed)"
    t = match["begin"].strftime("%I:%M %p").lstrip("0")
    where = "online" + (f" ({match['meet_url']})" if match.get("meet_url") else "") if not match["where"] else f"at {match['where']}"
    return f"{label}: {day}, {t} {where}"


def this_weeks_deliverable(start: date, today: date) -> dict | None:
    """This cohort's deliverable for its current week, with the due date shifted to the cohort's own calendar."""
    w = week_of(start, today)
    if not w:
        return None
    if today.weekday() >= 5 and w < WEEKS:  # after Friday's gate the next week's deliverable is the current one (as on the dashboard)
        w += 1
    row = syllabus.week_deliverable(f"WK {w:02d}")
    if not row:
        return None
    base = syllabus.EVENTS[0]["date"] if syllabus.EVENTS else start
    base -= timedelta(days=base.weekday())
    return {"week": w, "title": row["deliverable"], "due": row["date"] + (start - base), "phase": row.get("phase")}


def load(sb) -> list:
    """[{id, name, start, startup_ids}] oldest first; [] when the table is unreadable."""
    try:
        rows = sb.table("cohorts").select("id,name,start_date,total_weeks").order("start_date").execute().data or []
        startups = sb.table("startups").select("id,cohort_id").execute().data or []
        founders = sb.table("founders").select("startup_id,email").execute().data or []
    except Exception as e:  # noqa: BLE001
        print(f"[Cohorts Warning] {e}")
        return []
    out = []
    for r in rows:
        try:
            start = start_monday(r["start_date"])
        except (TypeError, ValueError, KeyError):  # a malformed row is skipped, never fatal
            continue
        ids = [s["id"] for s in startups if s.get("cohort_id") == r["id"]]
        out.append({"id": r["id"], "name": r["name"], "start": start, "weeks": r.get("total_weeks") or WEEKS, "startup_ids": ids,
                    "emails": {f["email"].lower() for f in founders if f.get("startup_id") in ids and f.get("email")}})
    return out


def summary_lines(cohort_list: list, today: date, events: list, only_startup: str | None = None) -> list:
    """Plain-text facts for the agent: each cohort's week, this week's deliverable and the next sprint session."""
    lines = []
    for c in cohort_list:
        if only_startup and only_startup not in c["startup_ids"]:
            continue
        w = week_of(c["start"], today, c["weeks"])
        when = f"week {w} of {c['weeks']}" if w else ("starts " + c["start"].isoformat() if today < c["start"] else "finished")
        lines.append(f"- {c['name']} (started Mon {c['start'].isoformat()}, now {when}; startups: "
                     f"{', '.join(c['startup_ids']) or 'none'})")
        d = this_weeks_deliverable(c["start"], today)
        if d:
            lines.append(f"    · this week's deliverable: {d['title']} (due {d['due'].strftime('%a %d %b')})")
        s = next_sprint(c["start"], today, c["weeks"])
        if s:
            lines.append("    · next " + describe_session(s, calendar_match(s["date"], events, c.get("emails"))))
    return lines


def week_labels(cohort_list: list, today: date) -> str:
    """'MVP#1 week 3 · MVP#2 week 1' for running cohorts (mentor views cover every cohort)."""
    bits = []
    for c in cohort_list:
        w = week_of(c["start"], today, c["weeks"])
        if w:
            bits.append(f"{c['name']} week {w}")
    return " · ".join(bits)


def for_startup(cohort_list: list, startup_id: str | None) -> dict | None:
    return next((c for c in cohort_list if startup_id and startup_id in c["startup_ids"]), None)
