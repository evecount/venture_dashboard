"""
Tell founders when a mentor gives their startup new milestones or tasks: one Slack DM and one email per founder,
both saying which mentor set them.

Works for every way they appear (asking the bot, a syllabus upload, a direct database edit) by polling for new
mentor-issued milestones and startup tasks instead of hooking each writer. Items are announced once they are a
minute old, so goals are in and a syllabus upload arrives as one message. Each item is announced once.
Email is sent from the studio Google account (Gmail API, gmail.send); replies go to the mentor who set the work.
"""

import re
from datetime import datetime, timedelta, timezone

SETTLE = timedelta(seconds=60)
LOOKBACK = timedelta(days=2)
MAX_LISTED = 6
NL = chr(10)
STARTED = datetime.now(timezone.utc) - timedelta(minutes=10)  # never announce work from before this ran


def fmt_due(due) -> str:
    try:
        d = datetime.strptime(str(due)[:10], "%Y-%m-%d").date()
        return f"{d.strftime('%a %b')} {d.day}"
    except ValueError:
        return ""


def _settled(row: dict, now: datetime) -> bool:
    return max(STARTED, now - LOOKBACK).isoformat() <= (row.get("created_at") or "") <= (now - SETTLE).isoformat()


def pending(milestones: list, tasks: list, mentor_ids: set, now: datetime, seen) -> list:
    """New, settled, not yet announced: mentor milestones, and tasks a mentor gave the startup (no single owner)."""
    out = [dict(m, kind="milestone") for m in milestones
           if m.get("created_by_role") == "mentor" and m.get("status", "open") == "open" and _settled(m, now)
           and not seen(f"ms-notify:{m['id']}")]
    out += [dict(t, kind="task") for t in tasks
            if t.get("startup_id") and not t.get("owner_slack_id") and t.get("created_by") in mentor_ids
            and t.get("status", "open") == "open" and _settled(t, now) and not seen(f"task-notify:{t['id']}")]
    return out


def seen_key(item: dict) -> str:
    return f"{'ms' if item['kind'] == 'milestone' else 'task'}-notify:{item['id']}"


def _what(items: list) -> str:
    """'a new milestone', '3 new milestones and a task', ..."""
    def n(kind, word):
        c = sum(1 for i in items if i["kind"] == kind)
        return "" if not c else (f"a new {word}" if c == 1 else f"{c} new {word}s")
    parts = [p for p in (n("milestone", "milestone"), n("task", "task")) if p]
    if len(parts) == 2:
        parts[1] = parts[1].replace("a new ", "a ").replace(" new ", " ")
    return " and ".join(parts)


def _lines(items: list, markdown: bool, by_line: bool) -> list:
    """Milestones (with goals) then tasks, each with its due date and, when several mentors are involved, who set it."""
    lines = []
    for kind, heading in (("milestone", "Milestones"), ("task", "Tasks")):
        group = [i for i in items if i["kind"] == kind]
        if not group:
            continue
        if not markdown:
            lines += ["", heading.upper()]
        for i in group[:MAX_LISTED]:
            due = fmt_due(i.get("due_date"))
            title = f"*{i['title']}*" if markdown else i["title"]
            lines.append(("• " if markdown else "- ") + title + (f" · due {due}" if due else "")
                         + (f" · from {i['mentor']}" if by_line else ""))
            lines += [("      ⬜ " if markdown else "    [ ] ") + g["title"] for g in (i.get("goals") or [])[:5]]
        if len(group) > MAX_LISTED:
            lines.append(f"…and {len(group) - MAX_LISTED} more {heading.lower()}")
    return lines


def _from(items: list) -> tuple:
    """(names joined for a sentence, whether each line needs its own 'from')."""
    names = list(dict.fromkeys(i["mentor"] for i in items))
    joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    return joined, len(names) > 1


def slack_text(first_name: str, items: list, startup: str) -> str:
    who, by_line = _from(items)
    return NL.join([f"🎯 Hey {first_name}, {who} set {_what(items)} for {startup}:", *_lines(items, True, by_line), "",
                    "Tell me when you finish something and I'll tick it off, e.g. _\"I finished the interview script\"_. "
                    "It's all on your *Home* tab too."])


def email_parts(first_name: str, items: list, startup: str, mentor_emails: dict, dashboard_url: str = "") -> tuple:
    """(subject, body, from_name, reply_to). The mentor is named in the subject, the sender name and a sign-off line."""
    who, by_line = _from(items)
    names = list(dict.fromkeys(i["mentor"] for i in items))
    subject = f"{who} set {_what(items)} for {startup}"
    contacts = [f"{n} ({mentor_emails[n]})" if mentor_emails.get(n) else n for n in names]
    body = NL.join([f"Hi {first_name},", "", f"{who} {'(your mentor) ' if len(names) == 1 else '(your mentors) '}set "
                    f"{_what(items)} for {startup}:", *_lines(items, False, by_line), "",
                    "Message Venture Buddy on Slack when you finish something and it will tick it off."]
                   + ([f"Everything is also on the dashboard: {dashboard_url}"] if dashboard_url else [])
                   + ["", f"Sent by: {', '.join(contacts)}, via Venture Buddy."]
                   + (["Reply to this email to answer " + (names[0] if len(names) == 1 else "them") + " directly."]
                      if any(mentor_emails.get(n) for n in names) else []))
    from_name = f"{names[0] if len(names) == 1 else 'Your mentors'} via Venture Studio"
    reply_to = [mentor_emails[n] for n in names if mentor_emails.get(n)]
    return subject, body, from_name, reply_to


def slack_email(client, slack_id: str) -> str:
    try:
        return client.users_info(user=slack_id)["user"].get("profile", {}).get("email", "") or ""
    except Exception:  # noqa: BLE001
        return ""


def run(sb, client, seen, mark, send_email=None, log=None, now: datetime | None = None, dashboard_url: str = "") -> list:
    """Announces settled new mentor milestones and tasks. send_email(to, subject, body, from_name, reply_to).
    Returns [(founder name, channel, count)] for what was sent."""
    now = now or datetime.now(timezone.utc)
    since = (now - LOOKBACK).isoformat()
    try:
        mentor_rows = sb.table("mentors").select("name,email,slack_user_id").execute().data or []
        milestones = (sb.table("milestones").select("id,startup_id,title,due_date,status,created_by,created_by_role,created_at,"
                                                    "startups(name),goals(title)")
                      .eq("created_by_role", "mentor").gte("created_at", since).order("created_at").limit(300).execute().data or [])
        tasks = (sb.table("tasks").select("id,startup_id,owner_slack_id,title,due_date,status,created_by,created_at,startups(name)")
                 .gte("created_at", since).order("created_at").limit(300).execute().data or [])
    except Exception as e:  # noqa: BLE001
        print(f"[Milestone Notify Warning] {e}")
        return []
    names = {m["slack_user_id"]: m["name"] for m in mentor_rows if m.get("slack_user_id")}
    new = pending(milestones, tasks, set(names), now, seen)
    if not new:
        return []
    try:
        founders = sb.table("founders").select("name,email,slack_user_id,startup_id").execute().data or []
    except Exception as e:  # noqa: BLE001
        print(f"[Milestone Notify Warning] {e}")
        return []
    mentor_emails = {m["name"]: m.get("email") for m in mentor_rows}
    by_startup: dict = {}
    for i in new:
        i["mentor"] = names.get(i.get("created_by")) or "Your mentor"
        by_startup.setdefault(i["startup_id"], []).append(i)
    sent = []
    for startup_id, items in by_startup.items():
        startup = (items[0].get("startups") or {}).get("name") or "your startup"
        for f in (x for x in founders if x.get("startup_id") == startup_id):
            first = (f.get("name") or "there").split()[0]
            sid = f.get("slack_user_id") or ""
            if re.fullmatch(r"[UW][A-Z0-9]{8,}", sid):
                try:
                    text = slack_text(first, items, startup)
                    client.chat_postMessage(channel=sid, text=text)
                    if log:
                        log(sid, "assistant", text)  # so a reply about it is understood
                    sent.append((f.get("name"), "slack", len(items)))
                except Exception as e:  # noqa: BLE001
                    print(f"[Milestone Notify Error] Slack {sid}: {e}")
            email = (slack_email(client, sid) if sid else "") or f.get("email") or ""
            if send_email and "@" in email:
                try:
                    send_email(email, *email_parts(first, items, startup, mentor_emails, dashboard_url))
                    sent.append((f.get("name"), "email", len(items)))
                except Exception as e:  # noqa: BLE001
                    hint = " (reconnect the studio calendar to grant Gmail sending)" if "403" in str(e) else ""
                    print(f"[Milestone Notify Error] email to {f.get('name')}: {e}{hint}")
        for i in items:
            mark(seen_key(i))
    return sent
