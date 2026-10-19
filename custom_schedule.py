"""
A participant's own program schedule, read from the syllabus milestones an upload created (titles "Week N (Sprint M): ...").
Participants without one follow the standard 12-week program (syllabus.py). Pure helpers plus one read-only fetch.
"""

import re
from datetime import date, timedelta

WEEK_RE = re.compile(r"^Week (\d+) \(Sprint (\d+)\): (.*)$")
MIN_WEEKS = 3  # a stray milestone called "Week 3 (Sprint 1): x" is not a schedule


def weeks_from_milestones(milestones: list) -> list:
    """Schedule weeks, in order: [{n, sprint, title, start, end, goals, pause}]. [] when there is no custom schedule."""
    weeks = {}
    for m in milestones or []:
        hit = WEEK_RE.match(m.get("title") or "")
        try:
            end = date.fromisoformat(str(m.get("due_date") or "")[:10])
        except ValueError:
            continue
        if not hit or m.get("status") == "dropped":
            continue
        title = hit.group(3)
        weeks[int(hit.group(1))] = {
            "n": int(hit.group(1)), "sprint": int(hit.group(2)), "title": title, "start": end - timedelta(days=6), "end": end,
            "goals": [g["title"] for g in (m.get("goals") or [])], "pause": "pause" in title.lower()}
    out = [weeks[k] for k in sorted(weeks)]
    return out if len(out) >= MIN_WEEKS else []


def fetch(sb, startup_id: str | None = None):
    """{startup_id: weeks} for every startup with a custom schedule, or just the weeks for one startup. Never raises."""
    try:
        q = sb.table("milestones").select("startup_id,title,due_date,status,goals(title)").like("title", "Week %")
        if startup_id:
            q = q.eq("startup_id", startup_id)
        rows = q.execute().data or []
    except Exception as e:  # noqa: BLE001
        print(f"[Custom Schedule Warning] {e}")
        return [] if startup_id else {}
    by = {}
    for r in rows:
        if r.get("startup_id"):
            by.setdefault(r["startup_id"], []).append(r)
    done = {k: weeks_from_milestones(v) for k, v in by.items()}
    if startup_id:
        return done.get(startup_id, [])
    return {k: v for k, v in done.items() if v}


def current(weeks: list, today: date) -> dict | None:
    """The week containing today, or None before the schedule starts or after it ends."""
    return next((w for w in weeks if w["start"] <= today <= w["end"]), None)


def is_session_day(weeks: list, d: date) -> bool:
    """A weekday inside the schedule that is not a pause week."""
    w = current(weeks, d)
    return bool(w) and d.weekday() < 5 and not w["pause"]


def fmt(d: date) -> str:
    return f"{d.strftime('%a %b')} {d.day}"


def deliverable(weeks: list, today: date, base: dict | None) -> dict | None:
    """The standard deliverable record with this week's custom title, dates and phase.
    The id is the standard deliverable with the same week number (capped at 12): check-ins point at the deliverables table."""
    w = current(weeks, today)
    if not w:
        return None
    title = w["title"] + (": " + "; ".join(w["goals"]) if w["goals"] else "")
    return {**(base or {}), "id": f"del-wk{min(w['n'], 12):02d}", "week": f"Week {w['n']}", "title": title, "due_date": w["end"].isoformat(), "sprint_phase": f"Sprint {w['sprint']}"}


def progress(weeks: list, today: date) -> dict | None:
    """{week, total, phase, paused} for the Home tab, or None."""
    w = current(weeks, today)
    return {"week": w["n"], "total": weeks[-1]["n"], "phase": f"Sprint {w['sprint']}", "paused": w["pause"]} if w else None


def agent_lines(weeks: list, today: date) -> list:
    w = current(weeks, today)
    if not w:
        return [f"This participant's custom {weeks[-1]['n']}-week schedule is not running today (it runs {fmt(weeks[0]['start'])} to {fmt(weeks[-1]['end'])})."]
    lines = [f"Program week: {w['n']} of {weeks[-1]['n']} · Sprint {w['sprint']} (this participant has a CUSTOM schedule)"]
    lines.append(f"This week: {w['title']} (ends {fmt(w['end'])})" + (" · a pause week, nothing is expected" if w["pause"] else ""))
    if w["goals"]:
        lines.append("This week's deliverables: " + "; ".join(w["goals"]))
    nxt = next((x for x in weeks if x["n"] == w["n"] + 1), None)
    if nxt:
        lines.append(f"Next week: Week {nxt['n']}: {nxt['title']}")
    return lines


def outline(weeks: list) -> list:
    return [f"- Week {w['n']} (Sprint {w['sprint']}): {'; '.join(w['goals']) or w['title']}, due {fmt(w['end'])}"
            + (" (pause week)" if w["pause"] else "") for w in weeks]
