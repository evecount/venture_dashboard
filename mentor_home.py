"""
Mentor-facing views: per-startup health summaries and the Slack blocks built from them.
Pure functions (no I/O) so they can be unit tested.

Health rules (kept deliberately simple and explainable):
  blocked  = the latest check-in says Blocked
  quiet    = no check-in for QUIET_DAYS or more (or none at all)
  on track = everything else
"""

from datetime import date, datetime, timedelta, timezone

import cohorts
import syllabus
from timeparse import parse_ts

QUIET_DAYS = 7
NL = chr(10)


def _parse(ts: str) -> datetime:
    return parse_ts(ts)


def relative(ts: str, now: datetime) -> str:
    secs = max(0, int((now - _parse(ts)).total_seconds()))
    if secs < 3600:
        return "just now" if secs < 120 else f"{secs // 60} min ago"
    if secs < 86400:
        hours = secs // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = secs // 86400
    return f"{days} day{'s' if days != 1 else ''} ago"


def summarize_startups(startups: list, founders: list, subs: list, now: datetime | None = None) -> list:
    """subs: confirmed check-ins (startup_id, founder_id, status, progress, blocker, digest, created_at), any order."""
    now = now or datetime.now(timezone.utc)
    out = []
    for st in startups:
        mine = sorted((s for s in subs if s["startup_id"] == st["id"]), key=lambda s: s["created_at"], reverse=True)
        names = [f["name"] for f in founders if f["startup_id"] == st["id"]]
        latest = mine[0] if mine else None
        health, detail, blocked_days, idle_days = "on_track", "", 0, None
        if latest is None:
            health, detail = "quiet", "No check-ins yet"
        else:
            idle_days = (now - _parse(latest["created_at"])).days
            if latest["status"] == "Blocked":
                since = latest["created_at"]
                for s in mine:  # walk back through the consecutive blocked run
                    if s["status"] != "Blocked":
                        break
                    since = s["created_at"]
                days = (now - _parse(since)).days
                blocked_days = days
                health = "blocked"
                detail = "Blocked " + ("for " + str(days) + " day" + ("s" if days != 1 else "") if days else "since today")
            elif idle_days >= QUIET_DAYS:
                health, detail = "quiet", f"No check-in for {idle_days} days"
        out.append({
            "id": st["id"], "name": st["name"], "stream": st.get("stream"), "lead": st.get("lead"),
            "founders": names, "latest": latest, "recent": mine[:3], "health": health, "detail": detail,
            "last_seen": relative(latest["created_at"], now) if latest else None,
            "blocked_days": blocked_days, "idle_days": idle_days,
            "blocked_since": since[:10] if latest and latest["status"] == "Blocked" else None,
        })
    order = {"blocked": 0, "quiet": 1, "on_track": 2}
    return sorted(out, key=lambda s: (order[s["health"]], s["name"].lower()))


def _who(s: dict) -> str:
    return ", ".join(s["founders"]) or "no founder linked yet"


def _short(text: str, n: int = 160) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _label(d: date, today: date) -> str:
    return "Today" if d == today else "Tomorrow" if d == today + timedelta(days=1) else syllabus.fmt_date(d)


def coming_up(today: date, meetings: list | None = None, limit: int = 6, cohort_list: list | None = None) -> list:
    """
    Program schedule items (office hours, deliverables) merged with real meetings, in date and time order. With
    `cohort_list`, each running cohort's own calendar is used and deliverables are labelled with the cohort.
    """
    running = [c for c in cohort_list or [] if cohorts.week_of(c["start"], today, c["weeks"])]
    calendars = [(c["name"], c["start"]) for c in running] or [(None, None)]
    items, seen = [], set()
    for name, start in calendars:
        for e in syllabus.upcoming(today, start=start):
            if e["deliverable"]:
                who = f"{name} deliverable due" if name and len(calendars) > 1 else "Deliverable due"
                items.append(((e["date"], -1), f"📦 {_label(e['date'], today)}: *{who}*, {e['deliverable']}"))
            elif "Office Hours" in (e["focus"] or "") and (e["date"], e["focus"]) not in seen:
                seen.add((e["date"], e["focus"]))
                items.append(((e["date"], -1), f"🗓 {_label(e['date'], today)}: {e['focus']}"))
    items += list(meetings or [])
    return [line for _, line in sorted(items, key=lambda it: it[0])[:limit]]


def build_mentor_blocks(summaries: list, today: date | None = None, tasks: list | None = None,
                        title: str = "Cohort pulse", footer: list | None = None, meetings: list | None = None,
                        cohort_list: list | None = None) -> list:
    today = today or date.today()
    cur = syllabus.current(today)
    attention = [s for s in summaries if s["health"] != "on_track"]
    healthy = [s for s in summaries if s["health"] == "on_track"]

    blocks = [{"type": "header", "text": {"type": "plain_text", "text": title}}]
    weeks = cohorts.week_labels(cohort_list or [], today)  # mentors cover every cohort: "MVP#1 week 3 · MVP#2 week 1"
    week = f"{weeks} · " if weeks else (f"Week {cur['week'].split()[-1].lstrip('0')} of 12 · " if cur else "")
    glance = (f"{week}{len(summaries)} startup{'s' if len(summaries) != 1 else ''} · "
              f"{len(attention)} need{'s' if len(attention) == 1 else ''} your attention · {len(healthy)} on track")
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": glance}]})

    if attention:
        lines = []
        for s in attention:
            icon = "🔴" if s["health"] == "blocked" else "🟠"
            head = f"{icon} *{s['name']}* ({_who(s)}) · {s['detail']}"
            if s["health"] == "blocked" and s["latest"]:
                head += f"{NL}> *Blocker:* {_short(s['latest'].get('blocker'))}"
            elif s["latest"]:
                head += f"{NL}> Last update {s['last_seen']}: {_short(s['latest']['digest'])}"
            if s.get("work"):
                head += f"{NL}> 💻 {s['work']}"
            if s.get("gap"):
                head += f"{NL}> ⚠️ Checking in but no code activity this week"
            lines.append(head)
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Needs your attention*" + NL + (NL * 2).join(lines)}})
    else:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "✅ *Nothing needs your attention right now.*"}})

    if healthy:
        lines = []
        for s in healthy:
            lat = s["latest"]
            lines.append(f"🟢 *{s['name']}* ({_who(s)}) · {lat['progress']}% · checked in {s['last_seen']}"
                         f"{NL}> {_short(lat['digest'])}" + (f"{NL}> 💻 {s['work']}" if s.get("work") else "")
                         + (f"{NL}> ⚠️ Checking in but no code activity this week" if s.get("gap") else ""))
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*On track*" + NL + (NL * 2).join(lines)}})

    lines = coming_up(today, meetings, cohort_list=cohort_list)
    if lines:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Coming up*" + NL + NL.join(lines)}})

    if tasks:
        lines = [f"• {t['title']} · {(t.get('startups') or {}).get('name', 'startup')}"
                 + (f" · due {t['due_date']}" if t.get("due_date") else "") for t in tasks[:6]]
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Your follow-ups*" + NL + NL.join(lines)}})

    blocks.append({"type": "divider"})
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": (
        "Progress % is how far a startup says it is on this week's deliverable. 🔴 blocked · 🟠 no check-in for "
        f"{QUIET_DAYS}+ days · 🟢 on track.{NL}Ask me anything in the *Messages* tab, e.g. _\"What is Auvira working on?\"_, "
        "_\"What's due tomorrow?\"_, _\"Who hasn't checked in?\"_ or _\"Note on SharedOut: needs a technical review.\"_")}]})
    blocks += footer or []
    return blocks
