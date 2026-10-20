"""
Google Calendar as a work signal (read-only, opt-in per founder).

What it is used for
  - Weekly rhythm: how many meetings a founder had, and how many were with people OUTSIDE their team
    (a good proxy for customer interviews and advisor sessions). Stored as one aggregated `meeting` signal per day:
    counts only, never titles, descriptions or attendee emails.
  - On-demand answers for the founder themself ("what's on my calendar tomorrow?"): fetched live, never stored.

Scopes: calendar.events.readonly + openid/email (to know which Google account was connected).
The refresh token is encrypted at rest (Fernet, key derived from STATE_SECRET) and only the bot can read it.
HTTP is injectable so everything is testable offline.
"""

import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from cryptography.fernet import Fernet, InvalidToken

import integrations

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
SCOPES = "openid email https://www.googleapis.com/auth/calendar.events.readonly"
STUDIO_SCOPES = ("openid email https://www.googleapis.com/auth/calendar.events "
                 "https://www.googleapis.com/auth/meetings.space.settings "
                 "https://www.googleapis.com/auth/meetings.space.created "
                 "https://www.googleapis.com/auth/gmail.send")  # created: make Meet rooms that anyone with the link can join  # create meetings on the studio calendar
MEET_API = "https://meet.googleapis.com/v2/spaces/{code}"
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
SYNC_DAYS = 14


# ---------- connect link & token handling ----------

def connect_url(client_id: str | None, redirect_uri: str | None, secret: str | None, founder_id: str, startup_id: str,
                studio: bool = False) -> str | None:
    """Google's consent screen, carrying a signed state that ties the result to this founder."""
    if not (client_id and redirect_uri and secret):
        return None
    state = integrations.sign_state({"f": founder_id, "s": "studio" if studio else startup_id, "p": "google-studio" if studio else "google"}, secret)
    return AUTH_URL + "?" + urlencode({
        "client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": STUDIO_SCOPES if studio else SCOPES,
        "access_type": "offline", "prompt": "consent", "state": state, "include_granted_scopes": "true",
    })


def _fernet(secret: str) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256((secret + ":google-calendar").encode()).digest()))


def encrypt_token(token: str, secret: str) -> str:
    return _fernet(secret).encrypt(token.encode()).decode()


def decrypt_token(blob: str, secret: str) -> str | None:
    try:
        return _fernet(secret).decrypt(blob.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def _default_http(method: str, url: str, headers: dict | None = None, data: dict | None = None, params: dict | None = None,
                  json: dict | None = None):
    import requests
    r = requests.request(method, url, headers=headers, data=data, params=params, json=json, timeout=20)
    r.raise_for_status()
    return r.json() if r.content else {}  # DELETE answers with no body


class GoogleCalendar:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, state_secret: str, http=_default_http):
        self.client_id, self.client_secret, self.redirect_uri = client_id, client_secret, redirect_uri
        self.state_secret, self.http = state_secret, http

    def exchange_code(self, code: str) -> dict:
        """code -> {refresh_token, access_token, email}."""
        tok = self.http("POST", TOKEN_URL, data={
            "code": code, "client_id": self.client_id, "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri, "grant_type": "authorization_code"})
        info = self.http("GET", USERINFO_URL, headers={"Authorization": f"Bearer {tok['access_token']}"})
        return {"refresh_token": tok.get("refresh_token"), "access_token": tok["access_token"], "email": info.get("email", "")}

    def access_token(self, encrypted_refresh: str) -> str | None:
        refresh = decrypt_token(encrypted_refresh, self.state_secret)
        if not refresh:
            return None
        data = self.http("POST", TOKEN_URL, data={
            "client_id": self.client_id, "client_secret": self.client_secret,
            "refresh_token": refresh, "grant_type": "refresh_token"})
        return data["access_token"]

    def create_event(self, encrypted_refresh: str, body: dict) -> dict:
        """Creates the event on the connected (studio) calendar and emails the invitations. Returns Google's event resource."""
        token = self.access_token(encrypted_refresh)
        if not token:
            raise RuntimeError("could not read the calendar token")
        return self.http("POST", EVENTS_URL, headers={"Authorization": f"Bearer {token}"},
                         params={"conferenceDataVersion": 1, "sendUpdates": "all"}, json=body)

    def send_email(self, encrypted_refresh: str, to: str, subject: str, body: str, from_name: str = "",
                   from_email: str = "", reply_to: list | None = None, html: str = "") -> dict:
        """Sends an email (plain text, plus an HTML version when given) from the connected (studio) Gmail account. Needs the gmail.send permission
        (granted by reconnecting the studio calendar); Google answers 403 without it."""
        import base64
        from email.message import EmailMessage
        from email.utils import formataddr
        token = self.access_token(encrypted_refresh)
        if not token:
            raise RuntimeError("could not read the studio account token")
        msg = EmailMessage()
        msg["To"], msg["Subject"] = to, subject
        if from_email:
            msg["From"] = formataddr((from_name, from_email)) if from_name else from_email
        if reply_to:
            msg["Reply-To"] = ", ".join(reply_to)
        msg.set_content(body)
        if html:
            msg.add_alternative(html, subtype="html")  # mail apps show the HTML; the text stays as the fallback
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        return self.http("POST", GMAIL_SEND_URL, headers={"Authorization": f"Bearer {token}"}, json={"raw": raw})

    def create_open_meet(self, encrypted_refresh: str) -> str | None:
        """
        Creates a Meet room whose access type is OPEN from the start: anyone with the link joins without the host admitting
        them. (Changing a Calendar-created room afterwards is refused by Google for this kind of account.)
        Returns the meeting link, or None if the account hasn't granted the permission or Google refuses.
        """
        token = self.access_token(encrypted_refresh)
        if not token:
            return None
        for attempt in range(3):  # Google's Meet service is occasionally slow; a retry beats falling back to a lobby room
            try:
                space = self.http("POST", "https://meet.googleapis.com/v2/spaces", headers={"Authorization": f"Bearer {token}"},
                                  json={"config": {"accessType": "OPEN"}})
                return space.get("meetingUri")
            except Exception as e:  # noqa: BLE001
                print(f"[Open Meet Warning] attempt {attempt + 1}: {e}")
                if "403" in str(e) or "401" in str(e):
                    break  # a permission problem won't fix itself by retrying
        return None

    def open_meet(self, encrypted_refresh: str, meet_code: str) -> bool:
        """
        Lets anyone with the link join the Meet without the host admitting them (access type OPEN), so nobody has to sign in
        to the studio account to let guests in. Returns False if the account hasn't granted the Meet settings permission.
        """
        token = self.access_token(encrypted_refresh)
        if not token:
            return False
        try:
            self.http("PATCH", MEET_API.format(code=meet_code), headers={"Authorization": f"Bearer {token}"},
                      params={"updateMask": "config.accessType"}, json={"config": {"accessType": "OPEN"}})
            return True
        except Exception as e:  # noqa: BLE001
            print(f"[Meet Access Warning] {e}")
            return False

    def update_event(self, encrypted_refresh: str, event_id: str, patch: dict) -> dict:
        """Changes an event (e.g. its time) and emails the update to everyone invited."""
        token = self.access_token(encrypted_refresh)
        if not token:
            raise RuntimeError("could not read the calendar token")
        return self.http("PATCH", f"{EVENTS_URL}/{event_id}", headers={"Authorization": f"Bearer {token}"},
                         params={"sendUpdates": "all"}, json=patch)

    def delete_event(self, encrypted_refresh: str, event_id: str) -> None:
        """Cancels an event and emails the cancellation to everyone invited."""
        token = self.access_token(encrypted_refresh)
        if not token:
            raise RuntimeError("could not read the calendar token")
        self.http("DELETE", f"{EVENTS_URL}/{event_id}", headers={"Authorization": f"Bearer {token}"}, params={"sendUpdates": "all"})

    def events(self, encrypted_refresh: str, since: datetime, until: datetime, only_ours: bool = False) -> list:
        token = self.access_token(encrypted_refresh)
        if not token:
            return []
        out, page = [], None
        while True:
            params = {"timeMin": since.isoformat(), "timeMax": until.isoformat(), "singleEvents": "true",
                      "orderBy": "startTime", "maxResults": 250,
                      "fields": "nextPageToken,items(id,summary,start,end,status,transparency,attendees(email,displayName,self,responseStatus),visibility,location,hangoutLink,extendedProperties/private)"}
            if only_ours:
                params["privateExtendedProperty"] = "ventureos=1"  # never read anyone's other calendar events
            if page:
                params["pageToken"] = page
            data = self.http("GET", EVENTS_URL, headers={"Authorization": f"Bearer {token}"}, params=params)
            out += data.get("items", [])
            page = data.get("nextPageToken")
            if not page:
                return out


# ---------- turning events into counts ----------

def _domain(email: str) -> str:
    return email.rsplit("@", 1)[-1].lower() if "@" in email else ""


def _event_day(ev: dict) -> str | None:
    start = ev.get("start", {})
    stamp = start.get("dateTime") or start.get("date")
    return stamp[:10] if stamp else None


def classify(events: list, team_emails: set, my_email: str) -> dict:
    """
    {day: {'meetings': n, 'external': m}}. A meeting is an accepted-or-pending event with at least one other attendee.
    External = at least one attendee who isn't on the founder's team (other founders, mentors) and doesn't share the
    founder's email domain unless that domain is a public mail provider.
    """
    public = {"gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "yahoo.com", "icloud.com", "proton.me", "protonmail.com"}
    team = {e.lower() for e in team_emails} | {my_email.lower()}
    mine = _domain(my_email)
    days: dict = {}
    for ev in events:
        if ev.get("status") == "cancelled":
            continue
        attendees = ev.get("attendees") or []
        others = [a for a in attendees if not a.get("self") and (a.get("email") or "").lower() != my_email.lower()]
        me = next((a for a in attendees if a.get("self") or (a.get("email") or "").lower() == my_email.lower()), None)
        if not others or (me and me.get("responseStatus") == "declined"):
            continue
        day = _event_day(ev)
        if not day:
            continue
        external = any((a.get("email") or "").lower() not in team
                       and (_domain(a.get("email") or "") != mine or mine in public) for a in others)
        d = days.setdefault(day, {"meetings": 0, "external": 0})
        d["meetings"] += 1
        d["external"] += 1 if external else 0
    return days


def sync_signals(gc: GoogleCalendar, sb, integration: dict, team_emails: set, now: datetime | None = None) -> int:
    """Replaces this startup's last-14-days calendar signals with fresh per-day counts. Returns rows written."""
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=SYNC_DAYS)
    my_email = integration.get("account") or ""
    events = gc.events(integration["refresh_token"], since, now)
    days = classify(events, team_emails, my_email)

    old = (sb.table("signals").select("id,meta").eq("startup_id", integration["startup_id"]).eq("type", "meeting")
           .gte("created_at", since.isoformat()).limit(500).execute().data) or []
    for r in old:
        m = r.get("meta") or {}
        if m.get("source") == "google" and m.get("founder_id") == integration["founder_id"]:
            sb.table("signals").delete().eq("id", r["id"]).execute()
    rows = [{
        "startup_id": integration["startup_id"], "type": "meeting", "stream": "GTM", "actor": "Google Calendar",
        "headline": f"{v['meetings']} meeting{'s' if v['meetings'] != 1 else ''} on {day}"
                    + (f" ({v['external']} with people outside the team)" if v["external"] else ""),
        "detail": "", "created_at": f"{day}T12:00:00+00:00",
        "meta": {"source": "google", "founder_id": integration["founder_id"], "meetings": v["meetings"], "external": v["external"]},
    } for day, v in sorted(days.items())]
    if rows:
        sb.table("signals").insert(rows).execute()
    return len(rows)


# ---------- on-demand, private to the founder ----------

def upcoming_text(gc: GoogleCalendar, encrypted_refresh: str, days: int = 2, now: datetime | None = None) -> str:
    """Titles and times for the founder's own eyes only; fetched live and never stored."""
    now = now or datetime.now(timezone.utc)
    events = [e for e in gc.events(encrypted_refresh, now, now + timedelta(days=days))
              if e.get("status") != "cancelled" and e.get("visibility") not in ("private", "confidential")]
    if not events:
        return f"Nothing on your calendar in the next {days} day{'s' if days != 1 else ''}."
    lines = []
    for e in events[:15]:
        start = e.get("start", {})
        when = (start.get("dateTime") or start.get("date") or "")[:16].replace("T", " ")
        lines.append(f"- {when}: {e.get('summary', '(no title)')}")
    return chr(10).join(lines)


def meet_code(url: str | None) -> str | None:
    """'https://meet.google.com/abc-defg-hij' -> 'abc-defg-hij'."""
    import re
    m = re.search(r"meet\.google\.com/([a-z]{3}-[a-z]{4}-[a-z]{3})", url or "")
    return m.group(1) if m else None
