"""
Tell founders when a mentor gives their startup new milestones or tasks: one Slack DM and one email per founder,
both saying which mentor set them.

Works for every way they appear (asking the bot, a syllabus upload, a direct database edit) by polling for new
mentor-issued milestones and startup tasks instead of hooking each writer. Items are announced once they are a
minute old, so goals are in and a syllabus upload arrives as one message. Each item is announced once.
Email is sent from the studio Google account (Gmail API, gmail.send); replies go to the mentor who set the work.
"""

import html
import re
from urllib.parse import urljoin
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
    """(subject, text body, from_name, reply_to, html body). The mentor is named in the subject, the sender name and a sign-off."""
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
    return subject, body, from_name, reply_to, email_html(first_name, items, startup, mentor_emails, dashboard_url)


# Email colours: the dashboard's palette (src/styles.css), with the orange darkened for white button text.
INK, MUTED, LINE, PAGE, SOFT, ORANGE, ORANGE_DARK = "#1D1F24", "#6C727B", "#E1E3E7", "#F7F8F9", "#FFF0E2", "#F76F23", "#C9531A"
LOGO_PATH = "/email-logo.png"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def _initials(name: str) -> str:
    parts = [p for p in re.split(r"\s+", name or "") if p]
    return "".join(p[0] for p in parts[:2]).upper() or "M"


def _pill(text: str) -> str:
    return (f'<span style="display:inline-block;padding:2px 10px;border-radius:999px;background:{SOFT};color:{ORANGE_DARK};'
            f'font-size:12px;font-weight:600;white-space:nowrap">{html.escape(text)}</span>')


def _item_html(i: dict, by_line: bool) -> str:
    e = html.escape
    due = fmt_due(i.get("due_date"))
    meta = " ".join(x for x in [_pill(f"Due {due}") if due else "",
                                 f'<span style="color:{MUTED};font-size:12px">from {e(i["mentor"])}</span>' if by_line else ""] if x)
    goals = "".join(f'<tr><td style="padding:3px 0 0 0;color:{INK};font-size:14px;line-height:20px">'
                    f'<span style="display:inline-block;width:12px;height:12px;border:1.5px solid #C4C8CF;border-radius:3px;'
                    f'vertical-align:-1px;margin-right:8px"></span>{e(g["title"])}</td></tr>' for g in (i.get("goals") or [])[:5])
    accent = ORANGE if i["kind"] == "milestone" else "#C4C8CF"
    return (f'<tr><td style="padding:0 0 10px 0"><table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
            f'style="border:1px solid {LINE};border-left:3px solid {accent};border-radius:8px;background:#FFFFFF">'
            f'<tr><td style="padding:14px 16px">'
            f'<div style="font-size:15px;line-height:22px;font-weight:600;color:{INK}">{e(i["title"])}</div>'
            + (f'<div style="padding-top:6px">{meta}</div>' if meta else "")
            + (f'<table role="presentation" cellspacing="0" cellpadding="0" style="margin-top:8px">{goals}</table>' if goals else "")
            + '</td></tr></table></td></tr>')


def _section_html(title: str, items: list, by_line: bool) -> str:
    if not items:
        return ""
    more = len(items) - MAX_LISTED
    rows = "".join(_item_html(i, by_line) for i in items[:MAX_LISTED])
    if more > 0:
        rows += f'<tr><td style="padding:0 0 10px 2px;color:{MUTED};font-size:13px">…and {more} more {title.lower()}</td></tr>'
    return (f'<tr><td style="padding:20px 0 10px 0;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;'
            f'color:{MUTED}">{html.escape(title)}</td></tr><tr><td><table role="presentation" width="100%" cellspacing="0" '
            f'cellpadding="0">{rows}</table></td></tr>')


def email_html(first_name: str, items: list, startup: str, mentor_emails: dict, dashboard_url: str = "") -> str:
    """A light, table-based HTML email (inline styles only, so Gmail and Outlook render it the same)."""
    e = html.escape
    who, by_line = _from(items)
    names = list(dict.fromkeys(i["mentor"] for i in items))
    headline = f"{who} set {_what(items)} for {startup}"
    one = len(names) == 1
    contact = mentor_emails.get(names[0]) if one else ""
    badge = _initials(names[0]) if one else f"+{len(names)}"
    sender = (f'<table role="presentation" cellspacing="0" cellpadding="0" style="margin-top:20px"><tr>'
              f'<td width="40" height="40" style="width:40px;height:40px;border-radius:20px;background:{SOFT};color:{ORANGE_DARK};'
              f'font-weight:700;font-size:15px;text-align:center;vertical-align:middle">{e(badge)}</td>'
              f'<td style="padding-left:12px"><div style="font-size:14px;font-weight:600;color:{INK}">{e(who)}</div>'
              f'<div style="font-size:13px;color:{MUTED}">{"Your mentor" if one else "Your mentors"}'
              + (f' · <a href="mailto:{e(contact)}" style="color:{MUTED}">{e(contact)}</a>' if contact else "")
              + '</div></td></tr></table>')
    button = (f'<tr><td style="padding:24px 0 4px 0"><a href="{e(dashboard_url)}" style="display:inline-block;background:{ORANGE_DARK};'
              f'color:#FFFFFF;text-decoration:none;font-weight:600;font-size:15px;padding:12px 22px;border-radius:8px">'
              f'Open the dashboard</a></td></tr>') if dashboard_url else ""
    replies = [n for n in names if mentor_emails.get(n)]
    footer = ("Reply to this email to answer " + (e(names[0]) if one else "your mentors") + " directly. ") if replies else ""
    milestones = [i for i in items if i["kind"] == "milestone"]
    tasks = [i for i in items if i["kind"] == "task"]
    logo = urljoin(dashboard_url, LOGO_PATH) if dashboard_url else ""  # served by the dashboard site (public/email-logo.png)
    mark = (f'<img src="{e(logo)}" width="28" height="28" alt="" style="display:inline-block;width:28px;height:28px;border:0;'
            f'border-radius:7px;vertical-align:middle;margin-right:10px">' if logo else
            f'<span style="display:inline-block;width:10px;height:10px;border-radius:5px;background:{ORANGE};margin-right:8px"></span>')
    brand = f'{mark}<span style="vertical-align:middle">VENTURE STUDIO</span>'
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><meta name="supported-color-schemes" content="light"><title>{e(headline)}</title></head>
<body style="margin:0;padding:0;background:{PAGE};font-family:{FONT};color:{INK}">
<div style="display:none;max-height:0;overflow:hidden;opacity:0">{e(headline)}. Tell Venture Buddy on Slack when you finish something.</div>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:{PAGE}"><tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px">
<tr><td style="padding:0 4px 14px 4px;font-size:13px;font-weight:700;letter-spacing:.06em;color:{INK}">
{brand}</td></tr>
<tr><td style="background:#FFFFFF;border:1px solid {LINE};border-radius:12px;padding:28px 28px 24px 28px">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0">
<tr><td style="font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:{ORANGE_DARK}">New for {e(startup)}</td></tr>
<tr><td style="padding-top:8px;font-size:22px;line-height:30px;font-weight:700;color:{INK}">{e(headline)}</td></tr>
<tr><td style="padding-top:12px;font-size:15px;line-height:23px;color:{INK}">Hi {e(first_name)}, here's what has been added to your plan.
When you finish something, just tell Venture Buddy on Slack and it will tick it off.</td></tr>
<tr><td>{sender}</td></tr>
{_section_html("Milestones", milestones, by_line)}
{_section_html("Tasks", tasks, by_line)}
{button}
</table></td></tr>
<tr><td style="padding:18px 4px 0 4px;font-size:12px;line-height:18px;color:{MUTED}">{footer}Sent by {e(who)} via Venture Buddy, the studio's Slack assistant.</td></tr>
</table></td></tr></table></body></html>"""


def slack_email(client, slack_id: str) -> str:
    try:
        return client.users_info(user=slack_id)["user"].get("profile", {}).get("email", "") or ""
    except Exception:  # noqa: BLE001
        return ""


def run(sb, client, seen, mark, send_email=None, log=None, now: datetime | None = None, dashboard_url: str = "") -> list:
    """Announces settled new mentor milestones and tasks. send_email(to, subject, body, from_name, reply_to, html).
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
