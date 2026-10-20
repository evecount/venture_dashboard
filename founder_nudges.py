"""
The Wednesday 2 PM founder nudge, tailored per founder:
- not connected yet -> ask them to connect Google Calendar and/or GitHub (buttons added by the caller), every week until they do;
- all connected -> ask how this week is going, so they check in;
- either way, if their cohort's sprint session is tomorrow, say when and where (from the studio calendar).
Mentors get a heads-up when a cohort's sprint session tomorrow isn't on the studio calendar.
Pure text builders; slack_bot sends them.
"""

from datetime import date, timedelta

import cohorts
import profile_rules

NL = "\n"


def first_name(name: str) -> str:
    """'Takshma Patel' -> 'Takshma'. A hyphenated given name usually means surname-first ('Leung Wai-Leng'), so keep it whole."""
    return profile_rules.first_name(name)


def founder_text(f: dict, has_github: bool, has_calendar: bool, last_checkin_days: int | None,
                 sprint_tomorrow: str | None, deliverable: dict | None) -> str:
    parts = [f"Hi {first_name(f['name'])}, your Wednesday check-in from Venture Buddy 👋"]
    missing = [label for ok, label in ((has_calendar, "Google Calendar"), (has_github, "GitHub")) if not ok]
    if missing:
        parts.append(
            f"You haven't connected your *{' and '.join(missing)}* yet. It takes a minute and means your meetings and code "
            "count as progress without you typing anything:" + NL
            + (f"• *Google Calendar*: press Connect Google Calendar below and allow read-only access. I only count meetings, never read titles." + NL
               if not has_calendar else "")
            + ("• *GitHub*: press Connect GitHub and choose *All repositories* when GitHub asks, then pick the ones that matter on my Home tab (➕ adds more). "
               "No code yet, or it's in a company organisation? Tell me and I'll guide you." if not has_github else "")
        )
    if last_checkin_days is None:
        parts.append("I haven't had a check-in from you yet. Reply here with a line or two on what you've worked on and any blockers.")
    elif last_checkin_days >= 3 or not missing:
        when = "today" if last_checkin_days == 0 else f"{last_checkin_days} day{'s' if last_checkin_days != 1 else ''} ago"
        parts.append(f"How's the week going? Your last check-in was {when}. Reply with your progress and anything blocking you.")
    if deliverable:
        parts.append(f"📦 This week's deliverable: *{deliverable['title']}*, due {deliverable['due'].strftime('%a %d %b')}.")
    if sprint_tomorrow:
        parts.append(f"🗓 Tomorrow: {sprint_tomorrow}. Bring your progress and questions.")
    return (NL + NL).join(parts)


def plan(founders: list, connections: dict, last_checkins: dict, cohort_list: list, events: list, today: date) -> dict:
    """
    founders: [{id, name, startup_id, slack_user_id}] (linked only). connections: {founder_id: {'github': bool, 'google': bool}}.
    last_checkins: {startup_id: date}. Returns {founders: [{slack, founder, text, missing}], mentors_note: str|None}.
    """
    by_startup = {sid: c for c in cohort_list for sid in c["startup_ids"]}
    tomorrow = today + timedelta(days=1)
    sessions, unscheduled = {}, []
    for c in cohort_list:
        s = next((x for x in cohorts.sprint_sessions(c["start"], c["weeks"]) if x["date"] == tomorrow), None)
        if s:
            match = cohorts.calendar_match(tomorrow, events, c.get("emails"))
            sessions[c["id"]] = cohorts.describe_session(s, match)
            if not match:
                unscheduled.append(f"{c['name']} Sprint {s['sprint']} session")
    out = []
    for f in founders:
        c = by_startup.get(f["startup_id"])
        conn = connections.get(f["id"], {})
        last = last_checkins.get(f["startup_id"])
        text = founder_text(f, conn.get("github", False), conn.get("google", False),
                            (today - last).days if last else None,
                            sessions.get(c["id"]) if c else None,
                            cohorts.this_weeks_deliverable(c["start"], today) if c else None)
        out.append({"slack": f["slack_user_id"], "founder": f, "text": text,
                    "missing": [k for k in ("google", "github") if not conn.get(k)]})
    note = None
    if unscheduled:
        note = ("⚠️ Heads-up: tomorrow is the " + " and the ".join(unscheduled) + ", but there's no sprint meeting on the "
                "studio calendar for it, so I told founders the date without a time or place. Ask me to schedule it "
                "(e.g. \"set up the sprint tomorrow at 11 AM at 111 Somerset with MVP#2\") and I'll invite them.")
    return {"founders": out, "mentors_note": note}
