"""
Announcements: a mentor tells the bot to message a group ("tell everyone office hours moved to 4 PM").
Pure helpers; the bot shows a card first and only sends after the mentor confirms.
"""

import re

SLACK_ID = re.compile(r"[UW][A-Z0-9]{8,}")
MAX_MESSAGE = 1500
MAX_RECIPIENTS = 60
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
            or [p for p in pool if p["name"].lower() == key] \
            or [p for p in pool if key and (key in p["name"].lower() or p["name"].lower().split()[0] == key)]
        if not matches:
            unknown.append(spec)
        for p in matches:
            add(p)
    return {"people": list(chosen.values()), "unreachable": sorted(set(unreachable)), "unknown": unknown}


def format_announcement(sender_name: str, message: str) -> str:
    return f"📣 *Announcement from {sender_name}*" + chr(10) + message.strip()
