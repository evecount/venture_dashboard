"""
Standing routines: recurring messages a mentor sets up in chat ("every Wednesday at 2 PM remind the founders to ...").
The mentor confirms a card first; the bot then sends it on schedule. Tailored routines are written per recipient
by the agent from that person's situation (connections, check-ins, sprint), so "until they do" conditions hold:
someone who has already done it gets a fitting message, or nothing. Pure helpers; storage in `bot_routines`.
"""

from datetime import date, datetime, time, timedelta, timezone

SGT = timezone(timedelta(hours=8))
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
AUDIENCES = ("founders", "mentors", "everyone", "cohort", "people")
WINDOW_MINUTES = 30  # a routine missed by a restart still goes out within this window
SKIP = "SKIP"


def parse_time(value: str) -> time | None:
    try:
        h, m = str(value).strip().split(":")[:2]
        return time(int(h), int(m))
    except (ValueError, TypeError):
        return None


def validate(args: dict) -> tuple[dict | None, str | None]:
    """Agent tool arguments -> a routine row (without id/created_by) or an error for the mentor."""
    day = str(args.get("weekday") or "").strip().lower()
    if day not in DAYS:
        return None, "Which day of the week should it go out?"
    t = parse_time(args.get("time") or "")
    if not t:
        return None, "What time should it go out (e.g. 2 PM)?"
    try:
        every = int(float(str(args.get("every_weeks") or 1).strip().split()[0]))
    except (ValueError, IndexError):
        every = 1
    if every not in (1, 2, 4):
        return None, "I can repeat every week, every two weeks or every four weeks."
    audience = str(args.get("audience") or "founders").lower()
    if audience not in AUDIENCES:
        audience = "founders"
    instruction = str(args.get("instruction") or "").strip()
    if not instruction:
        return None, "What should the message ask or tell them?"
    return {
        "title": str(args.get("title") or instruction)[:80], "instruction": instruction[:1500], "weekday": DAYS.index(day),
        "at_time": t.strftime("%H:%M"), "every_weeks": every, "audience": audience,
        "cohort_id": (args.get("cohort_id") or None) if audience == "cohort" else None,
        "people": [p for p in (args.get("people") or []) if isinstance(p, str)][:40] if audience == "people" else [],
        "tailored": bool(args.get("tailored", True)), "active": True,
    }, None


def first_run(row: dict, now: datetime) -> date:
    """The anchor date: the next matching weekday (today if its time hasn't passed)."""
    now = now.astimezone(SGT)
    d = now.date() + timedelta(days=(row["weekday"] - now.weekday()) % 7)
    if d == now.date() and now.time() >= parse_time(row["at_time"]):
        d += timedelta(days=7)
    return d


def occurrence(row: dict, now: datetime) -> datetime | None:
    """This run's scheduled moment if it is due now (within the window), else None."""
    now = now.astimezone(SGT)
    t = parse_time(row["at_time"])
    if not t or now.weekday() != row["weekday"]:
        return None
    anchor = date.fromisoformat(str(row["anchor_date"])[:10]) if row.get("anchor_date") else now.date()
    weeks = (now.date() - anchor).days // 7
    if now.date() < anchor or weeks % (row.get("every_weeks") or 1):
        return None
    at = datetime.combine(now.date(), t, tzinfo=SGT)
    return at if at <= now < at + timedelta(minutes=WINDOW_MINUTES) else None


def due(row: dict, now: datetime) -> datetime | None:
    if not row.get("active"):
        return None
    at = occurrence(row, now)
    if not at:
        return None
    last = row.get("last_run_at")
    if last:
        from timeparse import parse_ts
        if parse_ts(last) >= at:
            return None
    return at


def describe(row: dict) -> str:
    every = {1: "every", 2: "every other", 4: "every fourth"}.get(row.get("every_weeks") or 1, "every")
    t = parse_time(row["at_time"])
    when = f"{every} {DAYS[row['weekday']].capitalize()} at {t.strftime('%I:%M %p').lstrip('0')}"
    who = {"founders": "all founders", "mentors": "all mentors", "everyone": "everyone",
           "cohort": f"founders in {row.get('cohort_name') or row.get('cohort_id')}",
           "people": f"{len(row.get('people') or [])} people"}.get(row["audience"], row["audience"])
    return f"{when} → {who}{' (written for each person)' if row.get('tailored') else ''}: {row['instruction']}"


BUILTIN_NOTE = ("Built in (always on unless switched off in the Developer view): 5 PM check-in prompt on program days and a 9:30 AM "
                "nudge if no reply; Wednesday 2 PM founder nudge (connect Google Calendar/GitHub until they have, otherwise a "
                "progress check-in, plus tomorrow's sprint session for their cohort); a reminder about an hour before every "
                "studio-calendar meeting; Monday 9 AM weekly digest for mentors.")


COMPOSE_PROMPT = """You are writing ONE short Slack direct message on behalf of the studio team, carrying out this standing
instruction from a mentor ({mentor}):

"{instruction}"

Write it for the person described in CONTEXT, using what you know about them (what they've connected, their recent
check-ins, their cohort's deliverable and sprint session). Follow any conditions in the instruction: if the
instruction's condition is already met for this person, adapt (e.g. just ask for a progress update) or, if nothing
applies to them at all, reply with exactly {skip}. 2-5 sentences, warm and specific, Slack mrkdwn. Don't mention
that this is automated or that a mentor told you to. Never invent facts."""


class RoutineStore:
    """bot_routines access. Never raises: a missing table means no routines."""

    def __init__(self, sb):
        self.sb = sb

    def active(self) -> list:
        try:
            return self.sb.table("bot_routines").select("*").eq("active", True).order("created_at").execute().data or []
        except Exception as e:  # noqa: BLE001
            print(f"[Routines Warning] {e}")
            return []

    def add(self, row: dict) -> dict | None:
        try:
            return (self.sb.table("bot_routines").insert(row).execute().data or [None])[0]
        except Exception as e:  # noqa: BLE001
            print(f"[Routines Warning] add: {e}")
            return None

    def deactivate(self, routine_id: str) -> bool:
        try:
            return bool(self.sb.table("bot_routines").update({"active": False}).eq("id", routine_id).execute().data)
        except Exception as e:  # noqa: BLE001
            print(f"[Routines Warning] stop: {e}")
            return False

    def claim_run(self, row: dict, at: datetime) -> bool:
        """Marks this run before sending, only if no other run claimed it (so a restart never sends twice)."""
        try:
            q = self.sb.table("bot_routines").update({"last_run_at": at.isoformat()}).eq("id", row["id"])
            q = q.lt("last_run_at", at.isoformat()) if row.get("last_run_at") else q.is_("last_run_at", "null")
            return bool(q.execute().data)
        except Exception as e:  # noqa: BLE001
            print(f"[Routines Warning] claim: {e}")
            return False
