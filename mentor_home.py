"""
Mentor-facing views: per-startup health summaries and the Slack blocks built from them.
Pure functions (no I/O) so they can be unit tested.

Health rules (kept deliberately simple and explainable):
  blocked  = the latest check-in says Blocked
  quiet    = no check-in for QUIET_DAYS or more (or none at all)
  on track = everything else
"""

from datetime import date, datetime, timezone

import syllabus

QUIET_DAYS = 7
NL = chr(10)


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


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
        health, detail = "on_track", ""
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
                health = "blocked"
                detail = "Blocked " + ("for " + str(days) + " day" + ("s" if days != 1 else "") if days else "since today")
            elif idle_days >= QUIET_DAYS:
                health, detail = "quiet", f"No check-in for {idle_days} days"
        out.append({
            "id": st["id"], "name": st["name"], "stream": st.get("stream"), "lead": st.get("lead"),
            "founders": names, "latest": latest, "recent": mine[:3], "health": health, "detail": detail,
            "last_seen": relative(latest["created_at"], now) if latest else None,
        })
    order = {"blocked": 0, "quiet": 1, "on_track": 2}
    return sorted(out, key=lambda s: (order[s["health"]], s["name"].lower()))


def _who(s: dict) -> str:
    return ", ".join(s["founders"]) or "no founder linked yet"


def _short(text: str, n: int = 160) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def build_mentor_blocks(summaries: list, today: date | None = None, tasks: list | None = None,
                        title: str = "Cohort pulse", footer: list | None = None) -> list:
    today = today or date.today()
    cur = syllabus.current(today)
    attention = [s for s in summaries if s["health"] != "on_track"]
    healthy = [s for s in summaries if s["health"] == "on_track"]

    blocks = [{"type": "header", "text": {"type": "plain_text", "text": title}}]
    week = f"Week {cur['week'].split()[-1].lstrip('0')} of 12 · " if cur else ""
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
            lines.append(head)
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Needs your attention*" + NL + (NL * 2).join(lines)}})
    else:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "✅ *Nothing needs your attention right now.*"}})

    if healthy:
        lines = []
        for s in healthy:
            lat = s["latest"]
            lines.append(f"🟢 *{s['name']}* ({_who(s)}) · {lat['progress']}% · checked in {s['last_seen']}"
                         f"{NL}> {_short(lat['digest'])}" + (f"{NL}> 💻 {s['work']}" if s.get("work") else ""))
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*On track*" + NL + (NL * 2).join(lines)}})

    events = [e for e in syllabus.upcoming(today) if e["deliverable"] or "Office Hours" in (e["focus"] or "")][:4]
    if events:
        lines = [("📦 " if e["deliverable"] else "🗓 ") + syllabus.describe(e) for e in events]
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
