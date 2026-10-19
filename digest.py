"""
Mentor intelligence: the "talking but not building" signal, the Monday digest, and proactive nudges (pure functions).

Signal rule (kept simple and explainable)
  gap = the startup checked in at least once in the last 7 days, a GitHub repository is being tracked,
        and there were no commits or pull requests in the last 7 days.
  Startups without a tracked repo are never flagged: no data is not the same as no work.
"""

from datetime import date, datetime, timedelta, timezone

import cohorts
import mentor_home
import syllabus

NL = chr(10)
BLOCKED_ALERT_DAYS = 3  # nudge mentors once a startup has been blocked this long
GAP_MIN_CHECKINS = 1


def building_gap(checkins_7d: int, has_tracked_repo: bool, activity: dict) -> bool:
    code = activity.get("commits", 0) + activity.get("prs_opened", 0) + activity.get("prs_merged", 0)
    return checkins_7d >= GAP_MIN_CHECKINS and has_tracked_repo and code == 0


def count_recent(subs: list, startup_id: str, now: datetime, days: int = 7) -> int:
    since = now - timedelta(days=days)
    return sum(1 for s in subs if s["startup_id"] == startup_id and mentor_home._parse(s["created_at"]) >= since)


def alert_candidates(summaries: list, today: date) -> list:
    """
    Things a mentor should hear about without asking. Each has a stable `key` so it is sent once per episode:
    a blocked run, a quiet stretch, or an ISO week of "talking but not building".
    """
    alerts = []
    for s in summaries:
        who = ", ".join(s["founders"]) or "no founder linked yet"
        name = f"*{s['name']}* ({who})"   # every nudge names the startup AND its founders
        latest = s.get("latest")
        if s["health"] == "blocked" and s.get("blocked_days", 0) >= BLOCKED_ALERT_DAYS and latest:
            alerts.append({
                "key": f"blocked:{s['id']}:{s.get('blocked_since') or latest['created_at'][:10]}",
                "startup_id": s["id"],
                "text": f"🔴 {name} has been blocked for {s['blocked_days']} days: {latest.get('blocker') or 'no detail given'}. "
                        "Worth reaching out."})
        elif s["health"] == "quiet" and latest and s.get("idle_days", 0) >= mentor_home.QUIET_DAYS:
            alerts.append({
                "key": f"quiet:{s['id']}:{latest['created_at'][:10]}",
                "startup_id": s["id"],
                "text": f"🟠 {name} hasn't checked in for {s['idle_days']} days (last update {latest['created_at'][:10]})."})
        if s.get("gap"):
            year, week, _ = today.isocalendar()
            alerts.append({
                "key": f"gap:{s['id']}:{year}-W{week}",
                "startup_id": s["id"],
                "text": f"⚠️ {name} is checking in ({s.get('checkins_7d', 0)} this week) but I see no code activity on the "
                        "repository they track. Could be a good question for your next catch-up."})
    return alerts


def _startup_section(s: dict) -> str:
    icon = {"blocked": "🔴", "quiet": "🟠"}.get(s["health"], "🟢")
    lines = [f"{icon} *{s['name']}* ({', '.join(s['founders']) or 'no founder linked yet'})"]
    lat = s.get("latest")
    if s["health"] == "blocked" and lat:
        lines.append(f"• {s['detail']}: {mentor_home._short(lat.get('blocker'))}")
    elif s["health"] == "quiet":
        lines.append(f"• {s['detail']}")
    if lat and s["health"] != "quiet":
        lines.append(f"• {s.get('checkins_7d', 0)} check-in{'s' if s.get('checkins_7d', 0) != 1 else ''} this week · "
                     f"{lat.get('progress', 0)}% · _{mentor_home._short(lat['digest'], 110)}_")
    if s.get("work"):
        lines.append(f"• 💻 {s['work']}")
    if s.get("goals_total"):
        lines.append(f"• 🎯 {s['goals_done']}/{s['goals_total']} milestone goals done")
    if s.get("gap"):
        lines.append("• ⚠️ Checking in but no code activity this week")
    return NL.join(lines)


def build_digest_blocks(summaries: list, today: date, meetings: list | None = None, tasks: list | None = None,
                        footer: list | None = None, cohort_list: list | None = None) -> list:
    cur = syllabus.current(today)
    counts = {k: sum(1 for s in summaries if s["health"] == k) for k in ("blocked", "quiet", "on_track")}
    gaps = sum(1 for s in summaries if s.get("gap"))
    blocks = [{"type": "header", "text": {"type": "plain_text", "text": f"Weekly digest · {syllabus.fmt_date(today)}"}}]
    weeks = cohorts.week_labels(cohort_list or [], today)  # "MVP#1 week 3 · MVP#2 week 1"
    week = f"{weeks} · " if weeks else (f"Week {int(cur['week'].split()[-1])} of 12 · " if cur else "")
    glance = (f"{week}{counts['on_track']} on track · {counts['blocked']} blocked · {counts['quiet']} quiet"
              + (f" · {gaps} checking in without code activity" if gaps else ""))
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": glance}]})
    for s in summaries:  # already ordered blocked, quiet, on track
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": _startup_section(s)}})
    lines = mentor_home.coming_up(today, meetings, cohort_list=cohort_list)
    if lines:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Coming up this week*" + NL + NL.join(lines)}})
    due = [t for t in (tasks or []) if t.get("due_date") and str(t["due_date"]) <= (today + timedelta(days=7)).isoformat()]
    if due:
        rows = [f"• {t['title']} · {(t.get('startups') or {}).get('name', 'startup')} · due {t['due_date']}" for t in due[:8]]
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Follow-ups due this week*" + NL + NL.join(rows)}})
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text":
                   "Ask me about any startup or founder, for example _\"how is Auvira doing?\"_ or _\"who hasn't checked in?\"_"}]})
    return blocks + (footer or [])
