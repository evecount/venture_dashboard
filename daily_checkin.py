"""
Proactive daily check-in: the bot starts the conversation instead of waiting to be told.

- 17:00 SGT on program days: DM every linked founder "what did you get done today?", mentioning their open goals.
  The prompt is stored in the conversation history, so the founder's reply is understood as an answer to it.
- 09:30 SGT next program day: one gentle nudge for founders who never replied.
Dependencies are injected so this can be tested without Slack or a database.
"""

import re
from datetime import date, datetime, timedelta, timezone

import syllabus

SGT = timezone(timedelta(hours=8))
NL = chr(10)


def build_prompt(first_name: str, open_goals: list, weekday: str) -> str:
    lines = [f"Hey {first_name} 👋 End-of-day check-in: *what did you get done today?*",
             "A line or two is plenty (or paste a voice-note transcript). Tell me about any blocker too."]
    if open_goals:
        lines.append(NL + "Your open goals right now:")
        lines += [f"• {g}" for g in open_goals[:5]]
        lines.append("Tell me which of these moved and I'll update them.")
    return NL.join(lines)


def build_nudge(first_name: str) -> str:
    return (f"Morning {first_name}! I didn't catch an update from you yesterday. "
            "A one-liner on what you're working on is enough, and tell me if anything's blocking you.")


def stale_blockers(subs: list, now: datetime, hours: int = 48) -> list:
    """Each founder's LATEST confirmed check-in, kept only if it is still Blocked and older than `hours`.
    An older Blocked check-in followed by a newer one is resolved and never reported."""
    latest = {}
    for s in sorted(subs, key=lambda s: s.get("created_at") or ""):
        if s.get("founder_id"):
            latest[s["founder_id"]] = s
    cutoff = (now - timedelta(hours=hours)).astimezone(timezone.utc).isoformat()
    return [s for s in latest.values() if s.get("status") == "Blocked" and (s.get("created_at") or "") < cutoff]


def build_blocker_followup(first_name: str, blocker: str) -> str:
    return (f"Hey {first_name}, your last check-in said you were blocked on: *{blocker or 'something'}*. "
            "Is that still the case?" + NL + NL +
            "• *Sorted?* Tell me what changed and I'll update your check-in." + NL +
            "• *Still stuck?* Tell me more, or name a mentor and a time (e.g. _\"set up a call with Mo tomorrow at 2 PM\"_) "
            "and I'll set it up. Mentors can already see the blocker on their side.")


def _first_name(full: str) -> str:
    return (full or "there").split()[0]


def _open_goals(memory, startup_id: str) -> list:
    goals = []
    for m in memory.milestones(startup_id):
        goals += [g["title"] for g in (m.get("goals") or []) if not g.get("done")]
    return goals


def linked_founders(sb) -> list:
    rows = sb.table("founders").select("id,name,startup_id,slack_user_id").execute().data or []
    # Real Slack member ids only: skips unlinked founders and the demo placeholders (e.g. U_NEXUS_LEAD).
    return [r for r in rows if re.fullmatch(r"[UW][A-Z0-9]{8,}", r.get("slack_user_id") or "")]


def send_daily_prompts(client, sb, memory, now: datetime | None = None, dry_run: bool = False) -> list:
    """Returns the list of (slack_user_id, text) sent (or that would be sent when dry_run)."""
    now = now or datetime.now(SGT)
    if not syllabus.has_session(now.date()):
        return []
    sent = []
    for f in linked_founders(sb):
        text = build_prompt(_first_name(f["name"]), _open_goals(memory, f["startup_id"]), now.strftime("%A"))
        sent.append((f["slack_user_id"], text))
        if dry_run:
            continue
        try:
            client.chat_postMessage(channel=f["slack_user_id"], text=text)
            memory.log(f["slack_user_id"], "assistant", text)
        except Exception as e:  # noqa: BLE001 - one failed DM must not stop the rest
            print(f"[Daily Prompt Error] {f['slack_user_id']}: {e}")
    return sent


def _previous_session_day(today: date) -> date | None:
    d = today - timedelta(days=1)
    for _ in range(7):
        if syllabus.has_session(d):
            return d
        d -= timedelta(days=1)
    return None


def send_nudges(client, sb, memory, now: datetime | None = None, dry_run: bool = False) -> list:
    """Nudge founders who did not message the bot since the previous program day's 17:00 prompt."""
    now = now or datetime.now(SGT)
    if not syllabus.has_session(now.date()):
        return []
    prev = _previous_session_day(now.date())
    if prev is None:
        return []
    since = datetime(prev.year, prev.month, prev.day, 17, 0, tzinfo=SGT).astimezone(timezone.utc).isoformat()
    sent = []
    for f in linked_founders(sb):
        try:
            replied = (sb.table("bot_messages").select("id").eq("slack_user_id", f["slack_user_id"])
                       .eq("role", "user").gte("created_at", since).limit(1).execute().data)
        except Exception as e:  # noqa: BLE001
            print(f"[Nudge Warning] {e}")
            continue
        if replied:
            continue
        text = build_nudge(_first_name(f["name"]))
        sent.append((f["slack_user_id"], text))
        if dry_run:
            continue
        try:
            client.chat_postMessage(channel=f["slack_user_id"], text=text)
            memory.log(f["slack_user_id"], "assistant", text)
        except Exception as e:  # noqa: BLE001
            print(f"[Nudge Error] {f['slack_user_id']}: {e}")
    return sent
