"""The 12-week program schedule (src/data/syllabus.json) as plain helpers, shared by the bot's views and the agent."""

import json
import os
from datetime import date, timedelta

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "data", "syllabus.json")


def _load() -> list:
    try:
        with open(_PATH, encoding="utf-8") as f:
            rows = json.load(f)["Mamba_MVP_Official_Syllabus_Sch"]
    except Exception as e:  # noqa: BLE001
        print(f"[Syllabus Warning] could not load schedule: {e}")
        return []
    events = []
    for r in rows:
        try:
            d = date.fromisoformat(str(r["Date"])[:10])
        except (KeyError, ValueError):
            continue
        events.append({
            "date": d, "day": r.get("Day"), "week": r.get("Week"), "phase": r.get("Sprint Phase"),
            "focus": r.get("Module / Tactical Focus"), "activity": r.get("Exercise / Activity"),
            "owner": r.get("Owner / Lead"), "deliverable": r.get("Weekly Deliverable / Milestone"),
        })
    return sorted(events, key=lambda e: e["date"])


EVENTS = _load()
# Every cohort runs this same schedule from its own start Monday (cohorts.start_date). The helpers below take an
# optional `start` (that Monday); without it they use the dates in the file, which are MVP#1's.
BASE_MONDAY = (EVENTS[0]["date"] - timedelta(days=EVENTS[0]["date"].weekday())) if EVENTS else None
_SHIFTED: dict = {}


def events_for(start: date | None = None) -> list:
    """The schedule on a cohort's own calendar (same weeks and days, beginning on `start`)."""
    if not start or not BASE_MONDAY or start == BASE_MONDAY:
        return EVENTS
    if start not in _SHIFTED:
        offset = start - BASE_MONDAY
        _SHIFTED[start] = [{**e, "date": e["date"] + offset} for e in EVENTS]
    return _SHIFTED[start]


def current(today: date, start: date | None = None) -> dict | None:
    """The schedule row for today, or the most recent one before it (weekends). None before the program starts."""
    past = [e for e in events_for(start) if e["date"] <= today]
    return past[-1] if past else None


def week_deliverable(week: str, start: date | None = None) -> dict | None:
    return next((e for e in events_for(start) if e["week"] == week and e["deliverable"]), None)


def upcoming(today: date, days: int = 7, start: date | None = None) -> list:
    end = today + timedelta(days=days)
    return [e for e in events_for(start) if today <= e["date"] <= end]


def fmt_date(d: date) -> str:
    return f"{d.strftime('%a %b')} {d.day}"


def describe(e: dict) -> str:
    if e["deliverable"]:
        return f"{fmt_date(e['date'])}: DELIVERABLE DUE - {e['deliverable']}"
    return f"{fmt_date(e['date'])}: {e['focus']} ({e['owner']})"


def schedule_lines(today: date, start: date | None = None) -> list:
    """Plain-text schedule facts for the agent's context (on a cohort's own calendar when `start` is given)."""
    cur = current(today, start)
    if not cur:
        return ["The program has not started yet."]
    lines = [f"Program week: {cur['week']} of 12 · {cur['phase']}"]
    due = week_deliverable(cur["week"], start)
    if due:
        lines.append(f"This week's deliverable (due {fmt_date(due['date'])}): {due['deliverable']}")
    lines.append("Schedule for the next 7 days:")
    lines += [f"- {describe(e)}" for e in upcoming(today, start=start)]
    return lines


def program_outline(start: date | None = None) -> list:
    """One line per week: 'Week 3 (Sprint 2: ...): deliverable, due Fri Oct 16'. The shape of the whole program for newcomers."""
    lines, seen = [], set()
    for e in events_for(start):
        if e["deliverable"] and e["week"] not in seen:
            seen.add(e["week"])
            lines.append(f"- Week {int(str(e['week']).split()[-1])} ({e['phase']}): {e['deliverable']}, due {fmt_date(e['date'])}")
    return lines


def has_session(d: date, start: date | None = None) -> bool:
    """True if the program schedule has anything on this date (so weekends and off days are skipped)."""
    return any(e["date"] == d for e in events_for(start))


def current_deliverable(today: date, start: date | None = None) -> dict | None:
    """This week's deliverable straight from the schedule (id matches the deliverables table: del-wkNN)."""
    ev = events_for(start)
    cur = current(today, start) or (ev[0] if ev else None)
    due = week_deliverable(cur["week"], start) if cur else None
    if not due:
        return None
    n = int(cur["week"].split()[-1])
    return {"id": f"del-wk{n:02d}", "week": cur["week"], "title": due["deliverable"],
            "due_date": due["date"].isoformat(), "sprint_phase": cur["phase"]}


def long_date(d: date) -> str:
    return f"{d.strftime('%A, %b')} {d.day}"
