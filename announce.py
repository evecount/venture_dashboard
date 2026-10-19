"""
Announcements: a mentor tells the bot to message a group ("tell everyone office hours moved to 4 PM").
Pure helpers; the bot shows a card first and only sends after the mentor confirms.
"""

import re

SLACK_ID = re.compile(r"[UW][A-Z0-9]{8,}")
MAX_MESSAGE = 1500
MAX_RECIPIENTS = 60
DIRECT_MAX = 5  # a message to this many named people or fewer goes out at once, with no confirm card
GROUPS = {"everyone", "everybody", "all", "cohort", "founders", "mentors"}


def resolve_recipients(specs: list, founders: list, mentors: list, sender_slack_id: str) -> dict:
    """
    specs: 'everyone' (all founders and other mentors), 'founders', 'mentors', a startup's name, a Slack mention/id, or a name.
    founders rows: name, slack_user_id, startups(name). mentors rows: name, slack_user_id.
    Returns {people: [{name, slack}], unreachable: [names not on Slack yet], unknown: [specs that matched nobody]}.
    """
    pool = [{"name": r["name"], "slack": r.get("slack_user_id"), "role": "founder", "startup": ((r.get("startups") or {}).get("name") or "")}
            for r in founders] + \
           [{"name": r["name"], "slack": r.get("slack_user_id"), "role": "mentor", "startup": ""} for r in mentors]
    chosen: dict = {}
    unreachable: list = []
    unknown: list = []

    def add(p):
        if p["slack"] and SLACK_ID.fullmatch(p["slack"]) and p["slack"] != sender_slack_id:
            chosen.setdefault(p["slack"], {"name": p["name"], "slack": p["slack"]})
        elif not p["slack"] or not SLACK_ID.fullmatch(p["slack"] or ""):
            unreachable.append(p["name"])

    for raw in specs or []:
        spec = str(raw).strip()
        key = spec.lower().strip("<>@ ")
        if key in GROUPS:
            for p in pool:
                if key in ("everyone", "everybody", "all", "cohort") or p["role"] + "s" == key:
                    add(p)
            continue
        slack_id = re.sub(r"[<@>|].*$", "", spec.lstrip("<@")) if spec.startswith("<@") else spec
        matches = [p for p in pool if p["slack"] and p["slack"].lower() == slack_id.lower()] \
            or [p for p in pool if p["startup"] and p["startup"].lower() == key] \
            or [p for p in pool if p["name"].lower() == key]
        if not matches:  # a loose match ("Mo" inside "Thomas") must point at exactly one person, or nobody gets it
            loose = [p for p in pool if key and (key in p["name"].lower().split() or p["name"].lower().split()[0] == key)] \
                or [p for p in pool if key and key in p["name"].lower()]
            if len(loose) == 1:
                matches = loose
            elif loose:
                unknown.append(f"{spec} (which one? {', '.join(p['name'] for p in loose[:5])})")
                continue
        if not matches:
            unknown.append(spec)
        for p in matches:
            add(p)
    return {"people": list(chosen.values()), "unreachable": sorted(set(unreachable)), "unknown": unknown}


def is_direct(specs: list, people: list) -> bool:
    """A reminder to a few named people is sent straight away; anything addressed to a group keeps the preview card."""
    named_only = not any(str(s).strip().lower().strip("<>@ ") in GROUPS for s in specs or [])
    return named_only and 0 < len(people) <= DIRECT_MAX


def people_word(n: int) -> str:
    return "1 person" if n == 1 else f"{n} people"


def format_announcement(sender_name: str, message: str) -> str:
    return f"📣 *Announcement from {sender_name}*" + chr(10) + message.strip()
