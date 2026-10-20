"""
Tell founders when a mentor gives their startup a new milestone: one Slack DM and one email per founder.

Works for every way a mentor milestone appears (asking the bot, a syllabus upload, a direct database edit) by
polling for new mentor-issued milestones instead of hooking each writer. A milestone is announced once it is a
minute old, so its goals are in and a syllabus upload arrives as one message. Each milestone is announced once.
Email goes out over SMTP (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM); without it only Slack is used.
"""

import os
import re
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

SETTLE = timedelta(seconds=60)
LOOKBACK = timedelta(days=2)
MAX_LISTED = 6
NL = chr(10)
STARTED = datetime.now(timezone.utc) - timedelta(minutes=10)  # never announce milestones from before this ran


def fmt_due(due) -> str:
    try:
        d = datetime.strptime(str(due)[:10], "%Y-%m-%d").date()
        return f"{d.strftime('%a %b')} {d.day}"
    except ValueError:
        return ""


def pending(rows: list, now: datetime, seen) -> list:
    """Mentor milestones that are new, settled and not yet announced."""
    floor = max(STARTED, now - LOOKBACK).isoformat()
    cutoff = (now - SETTLE).isoformat()
    return [m for m in rows if m.get("created_by_role") == "mentor" and m.get("status", "open") == "open"
            and floor <= (m.get("created_at") or "") <= cutoff and not seen(f"ms-notify:{m['id']}")]


def _item_lines(milestones: list, markdown: bool) -> list:
    lines = []
    for m in milestones[:MAX_LISTED]:
        due = fmt_due(m.get("due_date"))
        title = f"*{m['title']}*" if markdown else m["title"]
        lines.append(f"• {title}" + (f" · due {due}" if due else ""))
        goals = [g["title"] for g in (m.get("goals") or [])][:5]
        lines += [("      ⬜ " if markdown else "    - ") + g for g in goals]
    if len(milestones) > MAX_LISTED:
        lines.append(f"…and {len(milestones) - MAX_LISTED} more")
    return lines


def _headline(milestones: list, mentor: str) -> str:
    n = len(milestones)
    return f"{mentor} set {'a new milestone' if n == 1 else f'{n} new milestones'} for {milestones[0].get('startup_name') or 'your startup'}"


def slack_text(first_name: str, milestones: list, mentor: str) -> str:
    return NL.join([f"🎯 Hey {first_name}, {_headline(milestones, mentor)}:", *_item_lines(milestones, True), "",
                    "Tell me when you finish a goal and I'll tick it off, e.g. _\"I finished the interview script\"_. "
                    "They're on your *Home* tab too."])


def email_parts(first_name: str, milestones: list, mentor: str, dashboard_url: str = "") -> tuple:
    subject = _headline(milestones, mentor)
    body = NL.join([f"Hi {first_name},", "", subject + ":", "", *_item_lines(milestones, False), "",
                    "Message Venture Buddy on Slack when you finish a goal and it will tick it off."]
                   + ([f"You can also see them on the dashboard: {dashboard_url}"] if dashboard_url else [])
                   + ["", "Venture Buddy"])
    return subject, body


def smtp_sender():
    """A send(to, subject, body) function from SMTP_* settings, or None when email isn't configured."""
    host, user, pw = os.environ.get("SMTP_HOST"), os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASSWORD")
    if not (host and user and pw):
        return None
    port, sender = int(os.environ.get("SMTP_PORT") or 587), os.environ.get("SMTP_FROM") or user

    def send(to: str, subject: str, body: str):
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = sender, to, subject
        msg.set_content(body)
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=30) as s:
                s.login(user, pw)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as s:
                s.starttls()
                s.login(user, pw)
                s.send_message(msg)
    return send


def slack_email(client, slack_id: str) -> str:
    try:
        return client.users_info(user=slack_id)["user"].get("profile", {}).get("email", "") or ""
    except Exception:  # noqa: BLE001
        return ""


def run(sb, client, seen, mark, send_email=None, log=None, now: datetime | None = None, dashboard_url: str = "") -> list:
    """Announces settled new mentor milestones. Returns [(founder name, channel, count)] for what was sent."""
    now = now or datetime.now(timezone.utc)
    try:
        rows = (sb.table("milestones").select("id,startup_id,title,due_date,status,created_by,created_by_role,created_at,"
                                              "startups(name),goals(title)")
                .eq("created_by_role", "mentor").gte("created_at", (now - LOOKBACK).isoformat())
                .order("created_at").limit(300).execute().data or [])
    except Exception as e:  # noqa: BLE001
        print(f"[Milestone Notify Warning] {e}")
        return []
    new = pending(rows, now, seen)
    if not new:
        return []
    try:
        mentors = {m.get("slack_user_id"): m["name"] for m in (sb.table("mentors").select("name,slack_user_id").execute().data or [])}
        founders = sb.table("founders").select("name,email,slack_user_id,startup_id").execute().data or []
    except Exception as e:  # noqa: BLE001
        print(f"[Milestone Notify Warning] {e}")
        return []
    by_startup: dict = {}
    for m in new:
        m["startup_name"] = (m.get("startups") or {}).get("name")
        by_startup.setdefault(m["startup_id"], []).append(m)
    sent = []
    for startup_id, items in by_startup.items():
        authors = list(dict.fromkeys(mentors.get(m.get("created_by")) or "Your mentor" for m in items))
        mentor = authors[0] if len(authors) == 1 else "Your mentors"
        for f in (x for x in founders if x.get("startup_id") == startup_id):
            first = (f.get("name") or "there").split()[0]
            sid = f.get("slack_user_id") or ""
            if re.fullmatch(r"[UW][A-Z0-9]{8,}", sid):
                try:
                    text = slack_text(first, items, mentor)
                    client.chat_postMessage(channel=sid, text=text)
                    if log:
                        log(sid, "assistant", text)  # so a reply about it is understood
                    sent.append((f.get("name"), "slack", len(items)))
                except Exception as e:  # noqa: BLE001
                    print(f"[Milestone Notify Error] Slack {sid}: {e}")
            email = (slack_email(client, sid) if sid else "") or f.get("email") or ""
            if send_email and "@" in email:
                try:
                    send_email(email, *email_parts(first, items, mentor, dashboard_url))
                    sent.append((f.get("name"), "email", len(items)))
                except Exception as e:  # noqa: BLE001
                    print(f"[Milestone Notify Error] email to {f.get('name')}: {e}")
        for m in items:
            mark(f"ms-notify:{m['id']}")
    return sent
