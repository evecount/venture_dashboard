"""
Proactive daily check-in: the bot starts the conversation instead of waiting to be told.

- 17:00 SGT on program days: DM every linked founder "what did you get done today?", mentioning their open goals.
  The prompt is stored in the conversation history, so the founder's reply is understood as an answer to it.
  When their startup pushed to GitHub that day, the prompt lists it, so "yes" is enough for a check-in draft.
- 09:30 SGT next program day: one gentle nudge for founders who never replied.
Dependencies are injected so this can be tested without Slack or a database.
"""

import re
from datetime import date, datetime, timedelta, timezone

import cohorts
import custom_schedule
import integrations
import syllabus

SGT = timezone(timedelta(hours=8))
NL = chr(10)


def build_prompt(first_name: str, open_goals: list, weekday: str, shipped: list | None = None) -> str:
    lines = [f"Hey {first_name} 👋 End-of-day check-in: *what did you get done today?*",
             "A line or two is plenty (or paste a voice-note transcript). Tell me about any blocker too."]
    if shipped:
        lines.append(NL + "I saw this on GitHub today:")
        lines += [f"• {s}" for s in shipped[:6]] + ([f"• …and {len(shipped) - 6} more"] if len(shipped) > 6 else [])
        lines.append("Reply *yes* and I'll draft your check-in from that, or add what the code doesn't show.")
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


def shipped_today(sb, startup_id: str, now: datetime) -> list:
    """Today's (SGT) commit and PR headlines on the startup's tracked repositories, oldest first. [] on any problem."""
    start = datetime.combine(now.astimezone(SGT).date(), datetime.min.time(), SGT)
    try:
        rows = (sb.table("signals").select("type,headline,detail,meta,created_at").eq("startup_id", startup_id)
                .in_("type", ["commit", "pull_request"]).gte("created_at", start.isoformat())
                .order("created_at").limit(50).execute().data) or []
        watched = integrations.monitored_for_startup(sb, startup_id)
    except Exception as e:  # noqa: BLE001 - the prompt still goes out without it
        print(f"[Daily Prompt Warning] shipped: {e}")
        return []
    return [(r.get("detail") or r.get("headline") or "").strip() for r in rows
            if (r.get("meta") or {}).get("repo") in watched and (r.get("detail") or r.get("headline"))]


def send_daily_prompts(client, sb, memory, now: datetime | None = None, dry_run: bool = False) -> list:
    """Returns the list of (slack_user_id, text) sent (or that would be sent when dry_run)."""
    now = now or datetime.now(SGT)
    custom = custom_schedule.fetch(sb)
    starts = _cohort_starts(sb)
    sent = []
    for f in linked_founders(sb):
        if not _session_day(now.date(), custom.get(f["startup_id"]), starts.get(f["startup_id"])):
            continue
        text = build_prompt(_first_name(f["name"]), _open_goals(memory, f["startup_id"]), now.strftime("%A"),
                            shipped_today(sb, f["startup_id"], now))
        sent.append((f["slack_user_id"], text))
        if dry_run:
            continue
        try:
            client.chat_postMessage(channel=f["slack_user_id"], text=text)
            memory.log(f["slack_user_id"], "assistant", text)
        except Exception as e:  # noqa: BLE001 - one failed DM must not stop the rest
            print(f"[Daily Prompt Error] {f['slack_user_id']}: {e}")
    return sent


def _cohort_starts(sb) -> dict:
    """startup_id -> its cohort's start Monday (each cohort runs the program days on its own calendar)."""
    return {sid: c["start"] for c in cohorts.load(sb) for sid in c["startup_ids"]}


def _session_day(d: date, weeks: list | None, start: date | None = None) -> bool:
    """A program day for this person: their own schedule's weekdays when they have one, else their cohort's program days."""
    return custom_schedule.is_session_day(weeks, d) if weeks else syllabus.has_session(d, start)


def _previous_session_day(today: date, weeks: list | None = None, start: date | None = None) -> date | None:
    d = today - timedelta(days=1)
    for _ in range(7):
        if _session_day(d, weeks, start):
            return d
        d -= timedelta(days=1)
    return None


def send_nudges(client, sb, memory, now: datetime | None = None, dry_run: bool = False) -> list:
    """Nudge founders who did not message the bot since the previous program day's 17:00 prompt."""
    now = now or datetime.now(SGT)
    custom = custom_schedule.fetch(sb)
    starts = _cohort_starts(sb)
    sent = []
    for f in linked_founders(sb):
        weeks, start = custom.get(f["startup_id"]), starts.get(f["startup_id"])
        prev = _previous_session_day(now.date(), weeks, start) if _session_day(now.date(), weeks, start) else None
        if prev is None:
            continue
        since = datetime(prev.year, prev.month, prev.day, 17, 0, tzinfo=SGT).astimezone(timezone.utc).isoformat()
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
