"""
Venture Studio OS: Autonomous Slack Bot & Pulse Engine
Ingests founder voice notes & transcripts, maps deliverables, posts Block Kit confirmations,
commits to Supabase Realtime, and proactively chases 48h blockers.
"""

import os
import hmac
import re
import secrets
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import json
from urllib.parse import quote
from datetime import datetime, timedelta, timezone
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler
except ImportError:
    App = None
    SocketModeHandler = None

# Optional dependencies with graceful fallbacks
try:
    from supabase import create_client, Client
except ImportError:
    Client = None
    create_client = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from apscheduler.schedulers.background import BackgroundScheduler
except ImportError:
    BackgroundScheduler = None

# Load environment configuration
try:
    if "load_dotenv" in globals() and callable(load_dotenv):
        load_dotenv()
except Exception:
    pass

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN")
SUPABASE_URL = os.environ.get("VITE_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
# Optional shared secret founders must enter when self-onboarding (leave unset to disable the check)
ONBOARDING_CODE = os.environ.get("ONBOARDING_CODE")
# Secret code mentors enter in the profile form to verify they are mentors (share only with the studio team)
MENTOR_CODE = os.environ.get("MENTOR_CODE")
# Work-signal integrations: signed connect links + the GitHub App's slug
STATE_SECRET = os.environ.get("STATE_SECRET")
GITHUB_APP_SLUG = os.environ.get("GITHUB_APP_SLUG")
# Google Calendar (OAuth client from Google Cloud Console; leave empty to disable the integration)
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
# Public URL of the deployed dashboard; enables "Open dashboard" buttons in Slack
DASHBOARD_URL = os.environ.get("DASHBOARD_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
QWEN_API_KEY = os.environ.get("QWEN_API_KEY") or os.environ.get("OPENAI_API_KEY")
# Gemini is used when GEMINI_API_KEY is set (via Google's OpenAI-compatible endpoint); otherwise Qwen/OpenAI.
AI_API_KEY = GEMINI_API_KEY or QWEN_API_KEY
AI_BASE_URL = (
    os.environ.get("AI_BASE_URL")
    or os.environ.get("QWEN_BASE_URL")
    or (
        "https://generativelanguage.googleapis.com/v1beta/openai/"
        if GEMINI_API_KEY
        else "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
)
AI_MODEL = os.environ.get("AI_MODEL") or ("gemini-3.8-flash" if GEMINI_API_KEY else "qwen-plus")

# Initialize AI Client
ai_client = (
    OpenAI(api_key=AI_API_KEY, base_url=AI_BASE_URL)
    if (OpenAI and AI_API_KEY)
    else None
)

# Initialize Supabase Client (retrying requests whose idle connection the server closed)
try:
    import db_retry
    db_retry.install(SUPABASE_URL)
except ImportError:
    pass
supabase: Client = (
    create_client(SUPABASE_URL, SUPABASE_KEY)
    if (create_client and SUPABASE_URL and SUPABASE_KEY)
    else None
)

from mentor_home import build_mentor_blocks as mentor_blocks, summarize_startups
import threading

import digest
import transcribe
import github_app
import syllabus
import google_calendar
import meetings
import integrations
from profile_rules import match_person, looks_like_email, norm_name
from daily_checkin import send_daily_prompts, send_nudges
from bot_agent import Agent
from bot_memory import Memory
from channel_memory import ChannelMemory, NEEDED_SCOPES
import dev_controls
import dev_home

# Console output is also kept in bot_logs for the dashboard's Developer page.
log_tee = dev_controls.install_log_tee() if "--simulate" not in sys.argv else None
# Persistent memory + conversational agent (needs both an LLM and the database)
memory = Memory(supabase)
settings = dev_controls.Settings(supabase)  # Developer page settings (pause, model, daily prompts...)
channels = ChannelMemory(supabase)  # last 7 days of the channels switched on in the Developer page
gh = github_app.GitHubApp.from_env()  # None until GITHUB_APP_ID + a private key are configured


def refresh_repos(row: dict) -> dict:
    """Re-reads the granted repos from GitHub itself (no webhook or founder action needed)."""
    if not gh:
        return row
    try:
        repos = gh.list_repos(row["external_id"])
        account = row.get("account") or gh.account(row["external_id"])
        supabase.table("integrations").update({"repos": repos, "account": account}).eq("id", row["id"]).execute()
        return {**row, "repos": repos, "account": account}
    except Exception as e:
        print(f"[GitHub Refresh Warning] {e}")
        return row


_backfill_timers: dict = {}


def backfill_soon(row: dict, slack_id: str | None, delay: float = 6.0):
    """Waits for the founder to finish picking (each pick restarts the timer), then backfills once."""
    previous = _backfill_timers.pop(row["id"], None)
    if previous:
        previous.cancel()
    timer = threading.Timer(delay, backfill_in_background, args=(row, slack_id))
    timer.daemon = True
    _backfill_timers[row["id"]] = timer
    timer.start()


def backfill_in_background(row: dict, slack_id: str | None):
    """Pulls the last two weeks of activity for the monitored repos, then tells the founder."""
    if not gh:
        return

    def run():
        try:
            n = github_app.backfill_signals(gh, supabase, row)
            if slack_id:
                app.client.chat_postMessage(channel=slack_id, text=(
                    f"📈 I pulled in {n} recent activity item{'s' if n != 1 else ''} from the last 14 days, so your timeline isn't empty."
                    if n else "📈 I checked the last 14 days and found no commits or merged pull requests in those repos."))
        except Exception as e:
            print(f"[GitHub Backfill Error] {e}")

    threading.Thread(target=run, daemon=True).start()


GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI") or (
    (DASHBOARD_URL or "").rstrip("/") + "/api/google/callback" if DASHBOARD_URL else None)
gcal = (google_calendar.GoogleCalendar(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI, STATE_SECRET)
        if (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REDIRECT_URI and STATE_SECRET) else None)


def google_link(founder_id: str, startup_id: str) -> str | None:
    return google_calendar.connect_url(GOOGLE_CLIENT_ID, GOOGLE_REDIRECT_URI, STATE_SECRET, founder_id, startup_id) if gcal else None


def studio_row() -> dict | None:
    try:
        rows = supabase.table("studio_calendar").select("*").eq("id", "primary").execute().data
        return rows[0] if rows else None
    except Exception as e:
        print(f"[Studio Calendar Warning] {e}")
        return None


def studio_connected() -> bool:
    return studio_row() is not None


def studio_events_fn(days: int):
    """Upcoming events on the studio calendar, or None when it isn't connected."""
    studio = studio_row()
    if not (gcal and studio):
        return None
    now = datetime.now(timezone.utc)
    try:
        return gcal.events(studio["refresh_token"], now, now + timedelta(days=days), only_ours=True)
    except Exception as e:
        print(f"[Studio Events Warning] {e}")
        return []


_studio_cache = {"at": 0.0, "events": []}


def studio_events_cached(days: int = 14) -> list:
    """Raw studio-calendar events (the bot's own meetings), cached for a minute so Home refreshes stay quick."""
    import time as _time
    if _time.time() - _studio_cache["at"] >= 60:
        _studio_cache.update(at=_time.time(), events=studio_events_fn(14) or [])
    return _studio_cache["events"]


def upcoming_meeting_items() -> list:
    """Real meetings the bot created, as 'Coming up' items for the mentor view."""
    today = datetime.now(timezone(timedelta(hours=8))).date()
    items = [meetings.upcoming_item(ev, today) for ev in studio_events_cached()]
    return [i for i in items if i and i[0][0] <= today + timedelta(days=7)]


def founder_meeting_lines(slack_user_id: str) -> list:
    """A founder's own upcoming meetings (only ones they are invited to), as Home-tab lines."""
    try:
        rows = supabase.table("founders").select("email").eq("slack_user_id", slack_user_id).limit(1).execute().data
        email = rows[0]["email"] if rows else None
    except Exception:
        return []
    today = datetime.now(timezone(timedelta(hours=8))).date()
    items = [meetings.upcoming_item(ev, today) for ev in studio_events_cached() if meetings.visible_to(ev, email, False)]
    return [line for _, line in sorted(i for i in items if i)][:5]


def studio_link(slack_id: str) -> str | None:
    return google_calendar.connect_url(GOOGLE_CLIENT_ID, GOOGLE_REDIRECT_URI, STATE_SECRET, slack_id, "studio", studio=True) if gcal else None


def my_calendar_text(founder_id: str, days: int) -> str:
    """Live, private view of this founder's own calendar (titles stay out of the database)."""
    if not gcal:
        return "Google Calendar isn't set up for this workspace yet."
    rows = supabase.table("integrations").select("refresh_token").eq("provider", "google").eq("founder_id", founder_id).execute().data
    if not rows:
        return "Your Google Calendar isn't connected yet. Press *Connect Google Calendar* on your Home tab."
    return google_calendar.upcoming_text(gcal, rows[0]["refresh_token"], days)


def github_link(founder_id: str, startup_id: str) -> str | None:
    return integrations.github_connect_url(GITHUB_APP_SLUG, STATE_SECRET, founder_id, startup_id)


agent = (Agent(ai_client, AI_MODEL, supabase, memory, connect_url=github_link, calendar_link=google_link, calendar_text=my_calendar_text,
                studio_link=studio_link, studio_connected=studio_connected, studio_events=studio_events_fn,
                settings=settings, channel_context=channels.context_for)
         if (ai_client and supabase) else None)

# Initialize Slack Bolt App
app = None
if App:
    app = App(token=SLACK_BOT_TOKEN) if SLACK_BOT_TOKEN else App(token="xoxb-placeholder")
else:
    class DummyApp:
        def message(self, *args, **kwargs):
            return lambda f: f
        def event(self, *args, **kwargs):
            return lambda f: f
        def action(self, *args, **kwargs):
            return lambda f: f
        def view(self, *args, **kwargs):
            return lambda f: f
    app = DummyApp()
channels.client = getattr(app, "client", None)

# Fallback in-memory roster & syllabus for offline/dry-run execution
OFFLINE_ROSTER = {
    "U_NEXUS_LEAD": {
        "founder_id": "demo-founder-01",
        "name": "Demo Founder A",
        "startup_id": "startup-auvira",
        "startup_name": "Auvira",
        "stream": "GTM",
        "lead": "GTM Venture Advisor"
    },
    "U_VITALS_LEAD": {
        "founder_id": "demo-founder-02",
        "name": "Demo Founder B",
        "startup_id": "startup-sharedout",
        "startup_name": "SharedOut",
        "stream": "Tech",
        "lead": "Technical Advisor"
    }
}

DEFAULT_DELIVERABLE = {
    "id": "del-wk01",
    "week": "WK 01",
    "title": "1-page venture thesis & Top 10 assumptions ranked",
    "due_date": "Friday 18:00 SGT",
    "sprint_phase": "Sprint 1: Problem, Founder Thesis & Opportunity"
}

# --- SYSTEM PROMPT ---
SYSTEM_PROMPT = """
You are Venture Buddy, the autonomous venture studio AI mentor.
Your role is to extract structured, actionable milestone progress from unstructured founder messages,
voice note transcripts, and meeting summaries.

Rules:
1. Always evaluate the update in the context of the team's ACTIVE DELIVERABLE.
2. Determine realistic percentage progress (0 to 100).
3. If the founder mentions something impeding progress, flag status as 'Blocked' and articulate the blocker concisely.
4. If on schedule with no blockers, status is 'In progress' or 'On Track'.
5. If the deliverable is finished, status is 'Completed' with 100% progress.
6. Return STRICT JSON with no markdown wrapping.
"""

def resolve_founder_context(slack_user_id: str) -> dict:
    """
    Maps Slack User ID to their Startup, Founder profile, and current active deliverable.
    """
    if supabase:
        try:
            res = (
                supabase.table("founders")
                .select("*, startups(*)")
                .eq("slack_user_id", slack_user_id)
                .execute()
            )
            if res.data:
                founder = res.data[0]
                startup = founder.get("startups", {})
                active_del = syllabus.current_deliverable(datetime.now(timezone(timedelta(hours=8))).date())
                if not active_del:
                    del_res = (
                        supabase.table("deliverables")
                        .select("*")
                        .gte("due_date", datetime.now(timezone.utc).isoformat())
                        .order("due_date")
                        .limit(1)
                        .execute()
                    )
                    active_del = del_res.data[0] if del_res.data else DEFAULT_DELIVERABLE
                return {
                    "founder_id": founder.get("id"),
                    "name": founder.get("name"),
                    "startup_id": startup.get("id"),
                    "startup_name": startup.get("name"),
                    "stream": startup.get("stream", "General"),
                    "lead": startup.get("lead", "Studio Lead"),
                    "deliverable": active_del,
                }
        except Exception as e:
            print(f"[Lookup Warning] Supabase lookup failed: {e}. Falling back to roster.")

    # Fallback lookup
    roster_entry = OFFLINE_ROSTER.get(
        slack_user_id,
        {
            "founder_id": f"founder-{slack_user_id[:6]}",
            "name": f"Founder ({slack_user_id})",
            "startup_id": "startup-general",
            "startup_name": "Demo Venture",
            "stream": "Tech",
            "lead": "Studio Lead",
        },
    )
    roster_entry["deliverable"] = DEFAULT_DELIVERABLE
    return roster_entry


def extract_update_with_ai(text: str, context: dict) -> dict:
    """
    Sends the transcript and milestone context to the LLM for structured extraction.
    """
    deliverable = context["deliverable"]
    prompt = f"""
{SYSTEM_PROMPT}

Team: {context['startup_name']} ({context['name']})
Stream: {context['stream']}
Current Active Deliverable: {deliverable['week']} - {deliverable['title']} (Sprint: {deliverable['sprint_phase']})

Founder Message / Transcript:
"{text}"

Output JSON format:
{{
  "status": "In progress" | "Blocked" | "On Track" | "Completed",
  "progress": 0 to 100,
  "stream": "{context['stream']}",
  "blocker": "1-sentence blocker description or 'None'",
  "digest": "1-2 sentence executive summary of what was accomplished and next step"
}}
"""
    if not ai_client:
        # High-fidelity heuristic fallback when running without LLM API key
        is_blocked = any(w in text.lower() for w in ["stuck", "blocked", "bug", "failing", "cannot", "issue", "problem"])
        is_complete = any(w in text.lower() for w in ["finished", "done", "completed", "submitted", "ready"])
        return {
            "status": "Blocked" if is_blocked else ("Completed" if is_complete else "In progress"),
            "progress": 100 if is_complete else (35 if is_blocked else 75),
            "stream": context["stream"],
            "blocker": "Reported issue in recent update" if is_blocked else "None",
            "digest": f"Analyzed update: {text[:100]}...",
        }

    try:
        response = ai_client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": "You are a JSON-only API. Only output valid JSON."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        data = json.loads(response.choices[0].message.content)
        return {
            "status": data.get("status", "In progress"),
            "progress": int(data.get("progress", 50)),
            "stream": data.get("stream", context["stream"]),
            "blocker": data.get("blocker", "None"),
            "digest": data.get("digest", "Progress recorded."),
        }
    except Exception as e:
        print(f"[LLM Extraction Error]: {e}")
        return {
            "status": "In progress",
            "progress": 50,
            "stream": context["stream"],
            "blocker": "None",
            "digest": f"Transcript received: {text[:80]}",
        }


def build_confirmation_card(context: dict, parsed: dict, raw_text: str) -> list:
    """
    Constructs an interactive Slack Block Kit confirmation card.
    Founders verify the data before it commits to the dashboard ledger.
    """
    deliverable = context["deliverable"]
    payload_to_store = {
        "startup_id": context["startup_id"],
        "founder_id": context["founder_id"],
        "deliverable_id": deliverable.get("id", "del-wk01"),
        "status": parsed["status"],
        "progress": parsed["progress"],
        "blocker": parsed["blocker"],
        "digest": parsed["digest"],
        "stream": parsed["stream"],
        "raw_transcript": raw_text[:500],
    }

    status_emoji = "🔴" if parsed["status"] == "Blocked" else ("🟢" if parsed["status"] == "Completed" else "🟡")

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🎯 Dashboard Check-In Preview",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"Hey *{context['name']}* ({context['startup_name']}), I've prepared your update for the Venture Command Center.",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Deliverable:*\n{deliverable['week']} · {deliverable['title']}"},
                {"type": "mrkdwn", "text": f"*Status:*\n{status_emoji} {parsed['status']} ({parsed['progress']}%)"},
                {"type": "mrkdwn", "text": f"*Workstream:*\n{parsed['stream']} · Lead: {context['lead']}"},
                {"type": "mrkdwn", "text": f"*Blocker Flag:*\n{parsed['blocker']}"},
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*AI Synthesis for Mentors:*\n> _{parsed['digest']}_",
            },
        },
        {
            "type": "actions",
            "block_id": "confirmation_actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ Confirm & Sync Dashboard", "emoji": True},
                    "style": "primary",
                    "action_id": "confirm_checkin",
                    "value": json.dumps(payload_to_store),
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✏️ Adjust Details", "emoji": True},
                    "action_id": "edit_checkin",
                    "value": json.dumps(payload_to_store),
                },
            ],
        },
    ]
    return blocks



# --- SELF-ONBOARDING ---

def get_role(slack_user_id: str) -> str | None:
    """
    Deterministic role lookup from the database (never guessed by the LLM):
    'mentor' (mentors table), 'founder' (founders table) or None (unknown).
    Offline / DB failure fails open to 'founder' so nobody is locked out.
    """
    if not supabase:
        return "founder"
    try:
        res = supabase.table("mentors").select("id").eq("slack_user_id", slack_user_id).limit(1).execute()
        if res.data:
            return "mentor"
    except Exception as e:
        print(f"[Role Warning] Mentor lookup failed (is the mentors table created?): {e}")
    try:
        res = supabase.table("founders").select("id").eq("slack_user_id", slack_user_id).limit(1).execute()
        return "founder" if res.data else None
    except Exception as e:
        print(f"[Role Warning] Roster lookup failed: {e}")
        return "founder"


def is_registered(slack_user_id: str) -> bool:
    return get_role(slack_user_id) is not None


def cohort_overview() -> list:
    """Per-startup health summaries (see mentor_home.summarize_startups)."""
    if not supabase:
        return []
    startups = supabase.table("startups").select("id,name,stream,lead").execute().data or []
    founders = supabase.table("founders").select("name,startup_id").execute().data or []
    subs = (
        supabase.table("submissions")
        .select("startup_id,founder_id,status,progress,blocker,digest,created_at")
        .eq("confirmed", True).order("created_at", desc=True).limit(300).execute().data or []
    )
    summaries = summarize_startups(startups, founders, subs)
    now = datetime.now(timezone.utc)
    for sm in summaries:
        rows = integrations.github_connections(supabase, sm["id"])
        activity = integrations.activity_summary(supabase, sm["id"])
        sm["work"] = integrations.activity_line(activity, bool(rows))
        sm["checkins_7d"] = digest.count_recent(subs, sm["id"], now)
        sm["gap"] = digest.building_gap(sm["checkins_7d"], any(integrations.monitored_repos(r) for r in rows), activity)
        ms = memory.milestones(sm["id"])
        goals = [g for m in ms for g in (m.get("goals") or [])]
        sm["goals_total"], sm["goals_done"] = len(goals), sum(1 for g in goals if g.get("done"))
    return summaries


def safe_snapshot() -> list:
    try:
        return cohort_overview()
    except Exception as e:
        print(f"[Snapshot Error] {e}")
        return []


def build_mentor_blocks(summaries: list, title: str = "Cohort pulse", tasks: list | None = None,
                        slack_user_id: str | None = None) -> list:
    # Pass slack_user_id only where the blocks go to that mentor alone (Home tab, DM): it makes a personal sign-in link.
    return mentor_blocks(summaries, tasks=tasks, title=title, footer=dashboard_button_blocks(slack_user_id=slack_user_id),
                         meetings=upcoming_meeting_items())


def link_mentor_by_email(slack_user_id: str, email: str):
    """Links a pre-registered mentor to their Slack account by profile email. Returns the mentor row or None."""
    if not (supabase and email):
        return None
    try:
        res = (
            supabase.table("mentors").select("*")
            .ilike("email", email.strip()).is_("slack_user_id", "null").limit(1).execute()
        )
        if not res.data:
            return None
        mentor = res.data[0]
        supabase.table("mentors").update({"slack_user_id": slack_user_id}).eq("id", mentor["id"]).execute()
        return mentor
    except Exception as e:
        print(f"[Onboarding Warning] Mentor link failed: {e}")
        return None


def build_onboarding_card() -> list:
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "👋 Welcome to the cohort! I don't have your profile yet. Set it up (it takes 20 seconds) "
                    "and then you can check in just by messaging me."
                ),
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "style": "primary",
                    "text": {"type": "plain_text", "text": "Set up my profile"},
                    "action_id": "start_onboarding",
                    "value": "onboard",
                }
            ],
        },
    ]


def build_role_picker_modal() -> dict:
    """Step 1: two buttons, so each person only ever sees the form meant for them."""
    return {
        "type": "modal",
        "callback_id": "modal_role_picker",
        "title": {"type": "plain_text", "text": "Set up your profile"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text": "*Welcome! Which one are you?*"}},
            {"type": "actions", "elements": [
                {"type": "button", "style": "primary", "text": {"type": "plain_text", "text": "I'm a Founder"}, "action_id": "pick_founder"},
                {"type": "button", "text": {"type": "plain_text", "text": "I'm a Mentor / Advisor"}, "action_id": "pick_mentor"},
            ]},
        ],
    }


def _text_input(block_id: str, action_id: str, label: str, optional: bool = False, hint: str | None = None, **extra) -> dict:
    block = {"type": "input", "block_id": block_id, "optional": optional,
             "label": {"type": "plain_text", "text": label},
             "element": {"type": "plain_text_input", "action_id": action_id, **extra}}
    if hint:
        block["hint"] = {"type": "plain_text", "text": hint}
    return block


def build_founder_modal(startups: list, need_email: bool, require_code: bool) -> dict:
    blocks = [_text_input("name_input", "name_text", "Your full name", max_length=80)]
    if need_email:
        blocks.append(_text_input("email_input", "email_text", "Your email",
                                  hint="Use the email you were invited with."))
    if startups:
        blocks.append({
            "type": "input", "block_id": "startup_input", "optional": True,
            "label": {"type": "plain_text", "text": "Joining an existing startup?"},
            "element": {"type": "static_select", "action_id": "startup_select",
                        "placeholder": {"type": "plain_text", "text": "Pick your startup"},
                        "options": [{"text": {"type": "plain_text", "text": st["name"][:75]}, "value": st["id"]} for st in startups]},
        })
    blocks.append(_text_input("new_startup_input", "new_startup_text", "Or name a new startup", optional=True,
                              hint="No name yet? Leave it blank, you can rename it later.", max_length=80))
    if require_code:
        blocks.append(_text_input("code_input", "code_text", "Cohort join code", optional=True))
    return {
        "type": "modal", "callback_id": "modal_onboarding_founder",
        "title": {"type": "plain_text", "text": "Founder profile"},
        "submit": {"type": "plain_text", "text": "Save profile"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": blocks,
    }


def build_mentor_modal(need_email: bool) -> dict:
    blocks = [_text_input("name_input", "name_text", "Your full name", max_length=80)]
    if need_email:
        blocks.append(_text_input("email_input", "email_text", "Your email"))
    blocks.append(_text_input("mentor_code_input", "mentor_code_text", "Mentor code",
                              hint="Ask the Program Coordinator for the code."))
    return {
        "type": "modal", "callback_id": "modal_onboarding_mentor",
        "title": {"type": "plain_text", "text": "Mentor / Advisor profile"},
        "submit": {"type": "plain_text", "text": "Verify & save"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": blocks,
    }


def code_matches(supplied: str, expected: str | None) -> bool:
    """Constant-time comparison; an unset expected code never matches."""
    return bool(expected) and hmac.compare_digest(supplied.strip().encode(), expected.strip().encode())


def slugify_startup_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"startup-{slug}" if slug else f"startup-{secrets.token_hex(3)}"


def create_startup(name: str) -> dict:
    """Creates a startup in the newest cohort. Stream/lead stay 'Unassigned' until a mentor sets them."""
    cohort = supabase.table("cohorts").select("id").order("created_at", desc=True).limit(1).execute().data
    startup_id = slugify_startup_id(name)
    if supabase.table("startups").select("id").eq("id", startup_id).execute().data:
        startup_id = f"{startup_id}-{secrets.token_hex(2)}"
    row = {
        "id": startup_id,
        "cohort_id": cohort[0]["id"] if cohort else None,
        "name": name.strip(),
        "stream": "Unassigned",
        "lead": "Unassigned",
    }
    supabase.table("startups").insert(row).execute()
    return row


def register_founder(slack_user_id: str, name: str, startup_id: str, email: str = "") -> dict:
    """Creates the founders row linking a Slack user to a startup. Raises on failure."""
    row = {
        "id": f"founder-{slack_user_id.lower()}",
        "startup_id": startup_id,
        "slack_user_id": slack_user_id,
        "name": name.strip(),
        "role": "Founder",
    }
    if email:
        row["email"] = email.lower()
    supabase.table("founders").insert(row).execute()
    return row


def link_by_email(slack_user_id: str, email: str):
    """
    Matches a Slack profile email to a pre-registered, not-yet-linked founder and links them.
    Returns the founder row (with startup name) or None.
    """
    if not (supabase and email):
        return None
    try:
        res = (
            supabase.table("founders")
            .select("*, startups(name)")
            .ilike("email", email.strip())
            .is_("slack_user_id", "null")
            .limit(1)
            .execute()
        )
        if not res.data:
            return None
        founder = res.data[0]
        supabase.table("founders").update({"slack_user_id": slack_user_id}).eq("id", founder["id"]).execute()
        return founder
    except Exception as e:
        print(f"[Onboarding Error] Email link failed: {e}")
        return None


def onboard_member(slack_user_id: str, client=None):
    """
    Called when someone joins the workspace/channel (or messages the bot unregistered).
    Auto-links by email and welcomes them; otherwise falls back to the self-onboarding card.
    Returns True if the user ends up linked.
    """
    client = client or app.client
    if is_registered(slack_user_id):
        return True
    try:
        user = client.users_info(user=slack_user_id)["user"]
    except Exception as e:
        print(f"[Onboarding Error] users_info failed: {e}")
        return False
    if user.get("is_bot") or user.get("deleted"):
        return False

    email = user.get("profile", {}).get("email", "")
    mentor = link_mentor_by_email(slack_user_id, email)
    if mentor:
        client.chat_postMessage(
            channel=slack_user_id,
            text=f"Welcome, {mentor['name']}! You're signed in as a mentor. Ask me for the cohort pulse any time.",
            blocks=build_mentor_blocks(safe_snapshot(), slack_user_id=slack_user_id),
        )
        publish_home(slack_user_id, client)
        return True

    founder = link_by_email(slack_user_id, email)
    if founder:
        startup = (founder.get("startups") or {}).get("name", "your startup")
        welcome = (
            f"👋 Welcome, {founder['name']}! You're linked to *{startup}*.\n\n"
            f"No forms or Jira here: message me any update, blocker or voice note and I'll turn it "
            f"into a check-in for you to confirm. Mentors see it live on the Venture Command Center."
        )
        client.chat_postMessage(
            channel=slack_user_id,
            text=welcome,
            blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": welcome}}, *dashboard_button_blocks(founder["id"]),
                    *connect_blocks(founder["id"], founder["startup_id"])],
        )
        publish_home(slack_user_id, client)
        return True

    client.chat_postMessage(
        channel=slack_user_id,
        blocks=build_onboarding_card(),
        text="Set up your profile to start checking in.",
    )
    return False


@app.event("team_join")
def handle_team_join(event, client):
    onboard_member(event["user"]["id"], client)


@app.event("member_joined_channel")
def handle_member_joined_channel(event, client):
    channels.members_changed(event.get("channel"))
    onboard_member(event["user"], client)


@app.event("member_left_channel")
def handle_member_left_channel(event):
    channels.members_changed(event.get("channel"))


@app.event({"type": "message", "subtype": "message_changed"})
def handle_message_changed(event):
    channels.edited(event)


@app.event({"type": "message", "subtype": "message_deleted"})
def handle_message_deleted(event):
    channels.deleted(event)


def prompt_onboarding(say):
    say(blocks=build_onboarding_card(), text="Set up your profile to start checking in.")


def slack_email(client, user_id: str) -> str:
    """The email Slack itself holds for this account (verified), or '' if the workspace doesn't expose it."""
    try:
        return client.users_info(user=user_id)["user"].get("profile", {}).get("email", "") or ""
    except Exception as e:
        print(f"[Onboarding Warning] users_info failed: {e}")
        return ""


def already_registered_text(user_id: str) -> str | None:
    """Message for someone who already has a profile, or None if they don't."""
    role = get_role(user_id)
    if role is None:
        return None
    if role == "mentor":
        return "You already have a profile as a *mentor*, so there's nothing more to set up."
    try:
        row = supabase.table("founders").select("name,startups(name)").eq("slack_user_id", user_id).limit(1).execute().data
        who = f"*{row[0]['name']}* at *{(row[0].get('startups') or {}).get('name', 'your startup')}*" if row else "a founder"
    except Exception:
        who = "a founder"
    return f"You already have a profile as {who}. To change your startup's name or details, just tell me here."


@app.action("start_onboarding")
def handle_start_onboarding(ack, body, client):
    ack()
    user_id = body["user"]["id"]
    existing = already_registered_text(user_id)
    if existing:
        client.chat_postMessage(channel=user_id, text=existing)
        publish_home(user_id, client)
        return
    client.views_open(trigger_id=body["trigger_id"], view=build_role_picker_modal())


@app.action("pick_founder")
def handle_pick_founder(ack, body, client):
    ack()
    user_id = body["user"]["id"]
    try:
        startups = supabase.table("startups").select("id,name").order("name").execute().data if supabase else []
    except Exception as e:
        print(f"[Onboarding Error] Could not load startups: {e}")
        startups = []
    view = build_founder_modal(startups, need_email=not slack_email(client, user_id), require_code=bool(ONBOARDING_CODE))
    client.views_update(view_id=body["view"]["id"], hash=body["view"]["hash"], view=view)


@app.action("pick_mentor")
def handle_pick_mentor(ack, body, client):
    ack()
    user_id = body["user"]["id"]
    view = build_mentor_modal(need_email=not slack_email(client, user_id))
    client.views_update(view_id=body["view"]["id"], hash=body["view"]["hash"], view=view)


def _val(values: dict, block: str, action: str) -> str:
    return (values.get(block, {}).get(action, {}).get("value") or "").strip()


def _resolve_email(client, user_id: str, values: dict):
    """(email, verified, error_or_None). Slack's own email wins; a typed one is unverified."""
    email = slack_email(client, user_id)
    if email:
        return email, True, None
    typed = _val(values, "email_input", "email_text")
    return (typed, False, None) if looks_like_email(typed) else ("", False, "Please enter a valid email address.")


def _duplicate_text(row: dict, group: str) -> str:
    return (f"A profile for *{row.get('name', 'that person')}* already exists in {group}. If that's you, it may be linked to "
            "another Slack account, so please ask a mentor to sort it out. If you're a different person with the same name, "
            "use your full name (including surname) and your own email.")


@app.view("modal_onboarding_founder")
def handle_founder_submit(ack, body, client, view):
    values = view["state"]["values"]
    user_id = body["user"]["id"]
    email, verified, email_err = _resolve_email(client, user_id, values)
    errors = {}
    if email_err:
        errors["email_input"] = email_err
    if ONBOARDING_CODE and not code_matches(_val(values, "code_input", "code_text"), ONBOARDING_CODE):
        errors["code_input"] = "That join code isn't right."
    if errors:
        ack(response_action="errors", errors=errors)
        return
    ack()

    existing = already_registered_text(user_id)
    if existing:
        client.chat_postMessage(channel=user_id, text=existing)
        return
    name = _val(values, "name_input", "name_text")
    ids = None
    try:
        startups = supabase.table("startups").select("id,name").execute().data or []
        picked = values.get("startup_input", {}).get("startup_select", {}).get("selected_option")
        new_name = _val(values, "new_startup_input", "new_startup_text")
        startup = next((st for st in startups if picked and st["id"] == picked["value"]), None)
        if not startup and new_name:  # naming an existing startup means joining it, not creating a twin
            startup = next((st for st in startups if norm_name(st["name"]) == norm_name(new_name)), None)

        founders = supabase.table("founders").select("id,name,email,slack_user_id,startup_id").execute().data or []
        if email and any((m.get("email") or "").casefold() == email.casefold()
                         for m in (supabase.table("mentors").select("email").execute().data or [])):
            client.chat_postMessage(channel=user_id, text="That email already belongs to a mentor profile.")
            return
        scoped = [f for f in founders if startup and f["startup_id"] == startup["id"]]
        verdict, row = match_person(founders, scoped, name, email, verified)
        if verdict == "duplicate":
            client.chat_postMessage(channel=user_id, text=_duplicate_text(row, "this startup" if startup else "the cohort"))
            return
        if verdict == "claim":
            supabase.table("founders").update({"slack_user_id": user_id, "email": email.lower()}).eq("id", row["id"]).execute()
            st_name = next((st["name"] for st in startups if st["id"] == row["startup_id"]), "your startup")
            msg = f"✅ Welcome, {row['name']}! I found your invite and linked it to *{st_name}*."
            ids = (row["id"], row["startup_id"])
        else:
            if not startup:
                startup = create_startup(new_name or "Untitled startup")
            register_founder(user_id, name, startup["id"], email)
            ids = (f"founder-{user_id.lower()}", startup["id"])
            msg = (f"✅ You're in, {name}! You're set up with *{startup['name']}* (you can rename it later). "
                   "Send me an update any time and I'll turn it into a check-in for you to confirm.")
    except Exception as e:
        print(f"[Onboarding Error] {e}")
        msg = "Something went wrong saving your profile. Please ask a mentor."
        ids = None
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": msg}}] + (connect_blocks(*ids) if ids else [])
    client.chat_postMessage(channel=user_id, text=msg, blocks=blocks)
    publish_home(user_id, client)


@app.view("modal_onboarding_mentor")
def handle_mentor_submit(ack, body, client, view):
    values = view["state"]["values"]
    user_id = body["user"]["id"]
    email, verified, email_err = _resolve_email(client, user_id, values)
    errors = {}
    if email_err:
        errors["email_input"] = email_err
    if not code_matches(_val(values, "mentor_code_input", "mentor_code_text"), MENTOR_CODE):
        errors["mentor_code_input"] = "That mentor code isn't right."
    if errors:
        ack(response_action="errors", errors=errors)
        return
    ack()

    existing = already_registered_text(user_id)
    if existing:
        client.chat_postMessage(channel=user_id, text=existing)
        return
    name = _val(values, "name_input", "name_text")
    try:
        mentors = supabase.table("mentors").select("id,name,email,slack_user_id").execute().data or []
        if email and any((f.get("email") or "").casefold() == email.casefold()
                         for f in (supabase.table("founders").select("email").execute().data or [])):
            client.chat_postMessage(channel=user_id, text="That email already belongs to a founder profile.")
            return
        verdict, row = match_person(mentors, mentors, name, email, verified)
        if verdict == "duplicate":
            client.chat_postMessage(channel=user_id, text=_duplicate_text(row, "the mentor list"))
            return
        if verdict == "claim":
            supabase.table("mentors").update({"slack_user_id": user_id, "email": email.lower()}).eq("id", row["id"]).execute()
        else:
            supabase.table("mentors").insert({"id": f"mentor-{user_id.lower()}", "slack_user_id": user_id,
                                              "name": name, "email": email.lower()}).execute()
        msg = (f"✅ Welcome, {name}! You're verified as a *mentor*. Message me any time for the cohort pulse; "
               "your Home tab shows it too.")
    except Exception as e:
        print(f"[Onboarding Error] {e}")
        msg = "Something went wrong saving your profile. Please check the mentors table exists, or ask the Program Coordinator."
    client.chat_postMessage(channel=user_id, text=msg)
    publish_home(user_id, client)


# --- APP HOME TAB ---

STATUS_EMOJI = {"Blocked": "🔴", "Completed": "✅", "On Track": "🟢", "In progress": "🟡"}


def dashboard_button_blocks(founder_id: str | None = None, slack_user_id: str | None = None) -> list:
    url = integrations.dashboard_url(DASHBOARD_URL, STATE_SECRET, founder_id, slack_user_id)
    if not url:
        return []
    return [{
        "type": "actions",
        "elements": [{
            "type": "button",
            "text": {"type": "plain_text", "text": "Open dashboard"},
            "url": url,
            "action_id": "open_dashboard",
        }],
    }]


@app.action("open_dashboard")
def handle_open_dashboard(ack):
    ack()  # link buttons still send an interaction event


def calendar_connect_blocks(founder_id: str, startup_id: str, with_divider: bool = False) -> list:
    url = google_link(founder_id, startup_id)
    if not url:
        return []
    return ([{"type": "divider"}] if with_divider else []) + [
        {"type": "section", "text": {"type": "mrkdwn", "text": (
            "*Google Calendar* 📅" + chr(10) +
            "Share your calendar (read-only) and I'll count your meetings and how many were with people outside your team, "
            "a good sign of customer conversations. I never store titles, descriptions or who was invited. You can disconnect any time.")}},
        {"type": "actions", "elements": [{"type": "button", "text": {"type": "plain_text", "text": "Connect Google Calendar"},
                                          "url": url, "action_id": "connect_google"}]},
    ]


def build_calendar_blocks(founder_id: str, startup_id: str, rows: list) -> list:
    """Home tab: who has shared a calendar, and a connect button for founders who haven't."""
    blocks = []
    if rows:
        lines = [f"✅ *{(r.get('founders') or {}).get('name', 'a founder')}* · {r.get('account', '')}" for r in rows]
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Google Calendar*" + chr(10) + chr(10).join(lines)}})
    if not any(r.get("founder_id") == founder_id for r in rows):
        blocks += calendar_connect_blocks(founder_id, startup_id)
    return blocks


def connect_blocks(founder_id: str, startup_id: str) -> list:
    """Optional 'connect your work' step shown right after profile setup."""
    url = github_link(founder_id, startup_id)
    if not url:
        return calendar_connect_blocks(founder_id, startup_id, with_divider=True)
    return [
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": (
            "*One more optional step: connect your work* 🔌" + chr(10) +
            "Link your GitHub and I can see real progress (commits, pull requests) without you typing it. "
            "GitHub lets you choose *all repositories* or just the ones for your startup. I only get read access. "
            "Code in a GitHub *organisation*? If you're not an owner, GitHub asks an owner to approve first. "
            "Press the second button and tell me the organisation's name; I'll link it the moment it's approved.")}},
        {"type": "actions", "elements": [
            {"type": "button", "style": "primary", "text": {"type": "plain_text", "text": "Connect GitHub"},
             "url": url, "action_id": "connect_github"},
            {"type": "button", "text": {"type": "plain_text", "text": "My code is in an organisation"},
             "action_id": "claim_org", "value": f"{founder_id}|{startup_id}"}]},
    ] + calendar_connect_blocks(founder_id, startup_id)


def build_connections_blocks(founder_id: str, startup_id: str, rows: list) -> list:
    """GitHub connections for the whole startup, with the repo picker inline (no extra messages to hunt for)."""
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "*Connected work (GitHub)*"}}] if rows else []
    for row in rows:
        repos = integrations.monitored_repos(row)
        who = (row.get("founders") or {}).get("name") or "a founder"
        where = f" ({row['account']})" if row.get("account") else ""
        if repos:
            head = f"✅ *{who}*{where} · tracking " + ", ".join(f"*{r}*" for r in repos)
        elif len(row.get("repos") or []) > 1:
            head = f"🟡 *{who}*{where} · connected. *Pick the repository to track below.*"
        else:
            head = f"🟡 *{who}*{where} · connected, but no repositories were shared with me."
        blocks += integrations.build_repo_selector(row, head, compact=True)
    mine = any(r.get("founder_id") == founder_id for r in rows)
    url = github_link(founder_id, startup_id)
    if url and not mine:
        text = ("*GitHub*" + chr(10) if not rows else "") + (
            "Not connected yet, so I can only see what you tell me." if not rows
            else "Your own GitHub isn't connected yet. Connect it so your work counts too.")
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text}})
        blocks.append({"type": "actions", "elements": [
            {"type": "button", "style": "primary", "text": {"type": "plain_text", "text": "Connect GitHub"},
             "url": url, "action_id": "connect_github_home"},
            {"type": "button", "text": {"type": "plain_text", "text": "My code is in an organisation"},
             "action_id": "claim_org", "value": f"{founder_id}|{startup_id}"}]})
    return blocks


def _milestone_lines(items: list) -> list:
    lines = []
    for m in items[:4]:
        goals = m.get("goals") or []
        done = sum(1 for g in goals if g.get("done"))
        due = f" · due {m['due_date']}" if m.get("due_date") else ""
        lines.append(f"🎯 *{m['title']}*{due} · {done}/{len(goals)} goals")
        lines += [("      ✅ " if g.get("done") else "      ⬜ ") + g["title"] for g in goals[:6]]
    return lines


HOW_TO = {
    "founder": [
        ("📝 Check in", [
            "_\"Finished 3 customer interviews, but I'm stuck on pricing\"_",
            "Send a voice note instead: I'll write out what I heard and you confirm the check-in"]),
        ("🎯 Milestones & tasks", [
            "_\"Set a milestone: 10 customer interviews by Oct 23. Goals: draft script, book 10 calls\"_",
            "_\"I finished the script\"_ (I tick the goal off)",
            "_\"Remind me to send the deck on Friday\"_"]),
        ("❓ Ask me", [
            "_\"What's due this week?\"_  ·  _\"What did I report last time?\"_",
            "_\"What's on my calendar tomorrow?\"_  ·  _\"What meetings do I have coming up?\"_"]),
        ("🗓 Meetings", [
            "_\"Set up a meeting with Mo on Thursday at 3 PM, virtually\"_ (name the people; mentors can invite everyone)",
            "_\"Move our Thursday meeting to 4 PM\"_ or _\"Cancel it\"_ for meetings you set up"]),
        ("🔌 Connect your work", [
            "Use the buttons above, or say _\"connect my GitHub\"_ / _\"connect my Google Calendar\"_",
            "_\"Rename my startup to Acme\"_"]),
    ],
    "mentor": [
        ("🔎 Ask me about the cohort", [
            "_\"How is Auvira doing?\"_  ·  _\"What is Takshma working on?\"_",
            "_\"Who's blocked?\"_  ·  _\"Who hasn't checked in?\"_  ·  _\"What's due tomorrow?\"_  ·  _pulse_"]),
        ("📌 Notes, tasks & milestones", [
            "_\"Note on SharedOut: needs a technical review\"_ (private to mentors)",
            "_\"Add a task for Auvira: send the deck by Friday\"_  ·  _\"Mark the deck task done\"_",
            "_\"Set a milestone for Auvira: Landing page live by Oct 20. Goals: copy approved, page published\"_ (founders see it as set by mentors)",
            "_\"Assign Auvira to the GTM stream\"_  ·  _\"Rename SharedOut to Acme\"_"]),
        ("🗓 Meetings", [
            "_\"Set up a meet with everyone at 3 PM on Thursday at 111 Somerset\"_ or _\"...virtually\"_ (I show a card first)",
            "_\"Set up a fortnightly sprint with Takshma and Matthew, Thursdays at 3 PM\"_",
            "_\"Move Thursday's sprint to 4 PM\"_  ·  _\"Cancel the sprint\"_  ·  _\"What meetings are coming up?\"_"]),
        ("🤖 Automatic", [
            "Monday 9:00 AM digest, and a 9:15 AM nudge when a startup is blocked, quiet, or checking in without code activity",
            "Reminders an hour before meetings, and a 5:00 PM daily prompt to founders"]),
    ],
}


def how_to_blocks(role: str) -> list:
    """A short, copy-able 'how to use Venture Buddy' section, different for founders and mentors."""
    nl = chr(10)
    blocks = [{"type": "divider"}, {"type": "header", "text": {"type": "plain_text", "text": "How to use Venture Buddy"}},
              {"type": "context", "elements": [{"type": "mrkdwn", "text": "Chat with me in the *Messages* tab. Just write naturally; these are examples. "
                                                "I always show a card to confirm before anything is saved or sent."}]}]
    for title, lines in HOW_TO[role]:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*{title}*{nl}" + nl.join("• " + l for l in lines)}})
    return blocks


def build_milestone_blocks(milestones: list) -> list:
    """Two kinds: ones the founder set for themselves, and ones issued by mentors/advisors."""
    nl = chr(10)
    issued = [m for m in milestones if m.get("created_by_role") == "mentor"]
    own = [m for m in milestones if m.get("created_by_role") != "mentor"]
    blocks = []
    if issued:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text":
                       "*Set by your mentors*" + nl + nl.join(_milestone_lines(issued))}})
    if own:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Your own milestones*" + nl + nl.join(_milestone_lines(own))}})
    else:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text":
                       "*Your own milestones*" + nl + "None yet. Tell me a goal in your own words, e.g. "
                       "_\"Set a milestone: 10 customer interviews by Oct 23\"_."}})
    return blocks


def build_task_blocks(tasks: list) -> list:
    if not tasks:
        return []
    nl = chr(10)
    lines = [f"• {t['title']}" + (f" (due {t['due_date']})" if t.get("due_date") else "") for t in tasks[:8]]
    return [{"type": "section", "text": {"type": "mrkdwn", "text": "*Follow-ups*" + nl + nl.join(lines)}}]


def build_home_view(context: dict | None, latest: dict | None, tasks: list | None = None, milestones: list | None = None, conns: list | None = None, gcal_rows: list | None = None,
                    meeting_lines: list | None = None) -> dict:
    """Founder's personal sprint radar. context=None means the user isn't on the roster yet."""
    if context is None:
        return {"type": "home", "blocks": [{"type": "header", "text": {"type": "plain_text", "text": "Your sprint radar"}}] + build_onboarding_card()}
    nl = chr(10)
    blocks = [{"type": "header", "text": {"type": "plain_text", "text": f"Your sprint radar – {context['startup_name']}"[:150]}}]

    today = datetime.now(timezone(timedelta(hours=8))).date()
    cur = syllabus.current(today)
    bits = []
    if cur:
        bits.append(f"Week {int(cur['week'].split()[-1])} of 12 · {cur['phase']}")
    if context.get("stream") not in (None, "", "Unassigned", "General"):
        bits.append(f"{context['stream']} stream")
    if context.get("lead") not in (None, "", "Unassigned"):
        bits.append(f"Advisor: {context['lead']}")
    if bits:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": " · ".join(bits)}]})

    d = context["deliverable"]
    due = str(d.get("due_date", ""))[:10]
    try:
        due_text = syllabus.long_date(datetime.strptime(due, "%Y-%m-%d").date())
    except ValueError:
        due_text = due
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": (
        f"*Due this week*{nl}{d['title']}" + (f"{nl}📅 Due {due_text}" if due_text else ""))}})

    if meeting_lines:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Your upcoming meetings*" + nl + nl.join(meeting_lines)}})
    if latest:
        emoji = STATUS_EMOJI.get(latest["status"], "⚪")
        text = f"{emoji} *{latest['status']}* · {latest.get('progress', 0)}%{nl}_{latest['digest']}_"
        blocker = latest.get("blocker")
        if blocker and blocker != "None":
            text += f"{nl}*Blocker:* {blocker}"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Your last check-in*" + nl + text}})
    else:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": (
            "*You haven't checked in yet*" + nl +
            "Message me what you worked on (a line or two is fine, or a voice-note transcript) and I'll turn it into a check-in for you to confirm.")}})
    blocks += build_milestone_blocks(milestones or [])
    blocks += build_connections_blocks(context["founder_id"], context["startup_id"], conns or [])
    blocks += build_calendar_blocks(context["founder_id"], context["startup_id"], gcal_rows or [])
    blocks += build_task_blocks(tasks or [])
    blocks += how_to_blocks("founder")
    blocks += dashboard_button_blocks(context["founder_id"])
    return {"type": "home", "blocks": blocks}


def publish_home(slack_user_id: str, client=None):
    """Renders the Home tab for a user. Safe to call after any state change."""
    client = client or app.client
    try:
        role = get_role(slack_user_id)
        if role == "mentor":
            developer = is_developer(slack_user_id)
            if developer and _home_mode.get(slack_user_id) == "dev":
                publish_dev_home(slack_user_id, client)
                return
            mine = [t for t in memory.open_tasks() if t.get("owner_slack_id") == slack_user_id]
            blocks = (build_mentor_blocks(safe_snapshot(), title="Mentor view", tasks=mine, slack_user_id=slack_user_id)
                      + studio_connect_blocks(slack_user_id) + how_to_blocks("mentor"))
            if developer:
                blocks.insert(1, dev_home.mode_switch("mentor"))
            client.views_publish(user_id=slack_user_id, view={"type": "home", "blocks": blocks})
            return
        context = resolve_founder_context(slack_user_id) if role else None
        latest = None
        if supabase and context:
            res = (
                supabase.table("submissions")
                .select("status,progress,blocker,digest")
                .eq("founder_id", context["founder_id"])
                .eq("confirmed", True)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            latest = res.data[0] if res.data else None
        client.views_publish(user_id=slack_user_id, view=build_home_view(context, latest, memory.open_tasks(context["startup_id"]) if context else [], memory.milestones(context["startup_id"]) if context else [], integrations.github_connections(supabase, context["startup_id"]) if context else [],
                                               integrations.google_connections(supabase, context["startup_id"]) if context else [],
                                               meeting_lines=founder_meeting_lines(slack_user_id) if context else []))
    except Exception as e:
        print(f"[Home Tab Error] {e}")


@app.event("app_home_opened")
def handle_app_home_opened(event, client):
    if event.get("tab", "home") == "home":
        publish_home(event["user"], client)


# --- SLACK HANDLERS ---

@app.message(re.compile(r"^(help|onboard|hi|hello|start)", re.IGNORECASE))
def handle_greeting(message, say):
    user_id = message.get("user")
    if user_id and get_role(user_id) == "mentor":
        say(blocks=build_mentor_blocks(safe_snapshot()), text="Cohort pulse")
        return
    say(
        f"Hey <@{user_id}>! 👋 I'm *Venture Buddy*, your automated venture studio lead.\n\n"
        f"You don't need to log into Jira or fill out forms. Whenever you work, hit a blocker, or finish customer interviews, "
        f"just send me a voice note or type an update right here!\n\n"
        f"I'll automatically parse your progress against the syllabus, generate a confirmation card for you to approve, "
        f"and sync it live to the Venture Command Center for your mentors."
    )
    if user_id and not is_registered(user_id):
        onboard_member(user_id)


@app.event("app_mention")
def handle_app_mention(event, say):
    text = event.get("text", "")
    user_id = event.get("user")
    process_inbound_message(user_id, text, event.get("files", []), say)


@app.message(re.compile(r".+"))
def handle_direct_or_channel_message(message, say):
    # Only process if direct message (channel type 'im') or explicitly in checkin context
    channel_type = message.get("channel_type")
    if channel_type != "im":
        channels.ingest(message)  # remembered for 7 days only if the channel is switched on in the Developer page
    if channel_type != "im" and not message.get("text", "").startswith("/checkin"):
        return  # Avoid hijacking regular chatter in public channels

    user_id = message.get("user")
    text = message.get("text", "").replace("/checkin", "").strip()
    process_inbound_message(user_id, text, message.get("files", []), say)


PULSE_RE = re.compile(r"^\s*(pulse|cohort pulse|status)\s*[?.!]*\s*$", re.IGNORECASE)


def build_identity(user_id: str, role: str) -> dict:
    if role == "mentor":
        name = "Mentor"
        try:
            rows = supabase.table("mentors").select("name").eq("slack_user_id", user_id).limit(1).execute().data
            name = rows[0]["name"] if rows else name
        except Exception as e:
            print(f"[Identity Warning] {e}")
        return {"role": "mentor", "slack_id": user_id, "name": name}
    context = resolve_founder_context(user_id)
    return {"role": "founder", "slack_id": user_id, "name": context["name"], "context": context}


def build_rename_card(proposal: dict) -> list:
    return [
        {"type": "section", "text": {"type": "mrkdwn",
         "text": f"Rename *{proposal['old_name']}* to *{proposal['new_name']}*?"}},
        {"type": "actions", "elements": [
            {"type": "button", "style": "primary", "text": {"type": "plain_text", "text": "Rename"},
             "action_id": "confirm_rename", "value": json.dumps(proposal)},
            {"type": "button", "text": {"type": "plain_text", "text": "Cancel"},
             "action_id": "cancel_rename", "value": "cancel"},
        ]},
    ]


def voice_hints() -> list:
    """Real startup, founder and mentor names so spoken names are spelled right ("Auvira", not "our offer")."""
    hints = ["Venture Buddy", "VentureOS", "GitHub", "milestone", "Slack"]
    try:
        for table, col in (("startups", "name"), ("founders", "name"), ("mentors", "name")):
            hints += [r[col] for r in (supabase.table(table).select(col).execute().data or [])]
    except Exception as e:
        print(f"[Voice Hints Warning] {e}")
    return hints


def transcribe_voice(audio_files: list, say) -> str:
    """Transcribes Slack voice notes with Gemini and replies with what was heard so mistakes can be spotted. '' on failure."""
    if not (GEMINI_API_KEY and SLACK_BOT_TOKEN):
        say("I can't transcribe voice notes yet (the transcription key isn't set up). Type it out for now?")
        return ""
    parts, hints = [], voice_hints()
    for f in audio_files[:transcribe.MAX_FILES]:
        try:
            data = transcribe.download(f, SLACK_BOT_TOKEN)
            parts.append(transcribe.transcribe_audio(data, transcribe.gemini_mime(f), GEMINI_API_KEY, AI_MODEL, hints=hints))
        except Exception as e:
            print(f"[Voice Error] {e}")
            say("I couldn't transcribe that voice note. It may be too long or in a format I can't read. Could you try again or type it out?")
            return ""
    heard = chr(10).join(t for t in parts if t).strip()
    if not heard:
        say("I couldn't make out any speech in that voice note. Could you try again?")
        return ""
    quoted = chr(10).join("> " + line for line in heard.splitlines() if line.strip())
    say(f"🎙 *I heard:*{chr(10)}{quoted}{chr(10)}_If I got something wrong, tell me and I'll fix it._")
    return heard


def process_inbound_message(user_id: str, text: str, files: list, say):
    """
    Core pipeline: resolve role, then hand the message to the conversational agent
    (answers, notes, tasks, memory, check-in proposals). Falls back to plain extraction
    when no LLM or database is configured.
    """
    if settings.get("paused") and not is_developer(user_id):
        say("I'm being updated right now and will be back shortly. Please try again in a few minutes.")
        return
    role = get_role(user_id)
    if role is None:
        if not onboard_member(user_id):
            return
        role = get_role(user_id)
        # Linked just now by email; welcome DM already sent, carry on.

    # Voice notes: transcribe, show the founder what I heard, then treat it like a typed update.
    audio = [f for f in (files or []) if transcribe.is_audio(f)]
    if audio:
        heard = transcribe_voice(audio, say)
        if heard:
            text = (text + chr(10) + heard).strip()
        elif not text.strip():
            return  # nothing intelligible and nothing typed: I already said so
    # Other attached files (documents, exports): just note their names
    for f in files or []:
        if f not in audio:
            text += f"\n[Attachment: {f.get('name')}]"

    if role == "mentor" and PULSE_RE.match(text):
        say(blocks=build_mentor_blocks(safe_snapshot()), text="Cohort pulse")
        return

    if agent is not None:
        try:
            ident = build_identity(user_id, role)
            result = agent.respond(ident, text)
            say(result["text"])
            if result["checkin"]:
                say(blocks=build_confirmation_card(ident["context"], result["checkin"], text),
                    text="Please confirm your dashboard update.")
            if result["rename"]:
                say(blocks=build_rename_card(result["rename"]), text="Confirm startup rename")
            if result.get("meeting"):
                say(blocks=build_meeting_card(result["meeting"]), text="Confirm meeting")
            return
        except Exception as e:
            print(f"[Agent Error] {e}. Falling back to basic handling.")

    if role == "mentor":
        say(blocks=build_mentor_blocks(safe_snapshot()), text="Cohort pulse")
        return
    say(f"Processing your check-in with Studio AI, <@{user_id}>... ⚡")
    context = resolve_founder_context(user_id)
    extracted = extract_update_with_ai(text, context)
    say(blocks=build_confirmation_card(context, extracted, text), text="Please confirm your dashboard update.")


@app.action("confirm_rename")
def handle_confirm_rename(ack, body, client):
    ack()
    user_id = body["user"]["id"]
    proposal = json.loads(body["actions"][0]["value"])
    role = get_role(user_id)
    allowed = role == "mentor"
    if role == "founder":
        try:
            own = supabase.table("founders").select("startup_id").eq("slack_user_id", user_id).execute().data
            allowed = bool(own) and own[0]["startup_id"] == proposal["startup_id"]
        except Exception as e:
            print(f"[Rename Warning] {e}")
    if not allowed:
        text = "⚠️ You can't rename that startup."
    else:
        try:
            supabase.table("startups").update({"name": proposal["new_name"]}).eq("id", proposal["startup_id"]).execute()
            text = f"✅ Renamed *{proposal['old_name']}* to *{proposal['new_name']}*."
        except Exception as e:
            print(f"[Rename Error] {e}")
            text = "⚠️ I couldn't rename it."
    client.chat_update(channel=body["channel"]["id"], ts=body["message"]["ts"], text=text,
                       blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": text}}])
    publish_home(user_id, client)


@app.action("cancel_rename")
def handle_cancel_rename(ack, body, client):
    ack()
    client.chat_update(channel=body["channel"]["id"], ts=body["message"]["ts"], text="Rename cancelled.",
                       blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": "Rename cancelled."}}])


def commit_checkin(action_value: dict, actor: str):
    """Writes a confirmed check-in to Supabase and emits the ticker signal."""
    if not supabase:
        return
    try:
        supabase.table("submissions").insert({
            "startup_id": action_value["startup_id"],
            "deliverable_id": action_value["deliverable_id"],
            "founder_id": action_value["founder_id"],
            "status": action_value["status"],
            "progress": action_value["progress"],
            "blocker": action_value["blocker"],
            "digest": action_value["digest"],
            "raw_transcript": action_value.get("raw_transcript"),
            "confirmed": True,
        }).execute()
        signal_type = "blocker" if action_value["status"] == "Blocked" else "checkin"
        supabase.table("signals").insert({
            "startup_id": action_value["startup_id"],
            "type": signal_type,
            "headline": f"{action_value['status']} update logged",
            "detail": action_value["digest"],
            "stream": action_value.get("stream", "General"),
            "actor": actor,
        }).execute()
    except Exception as e:
        print(f"[Supabase Commit Error]: {e}")


@app.view("modal_edit_checkin")
def handle_edit_checkin_submit(ack, body, client, view):
    """Founder saved the Adjust Details modal: commit the edited values."""
    ack()
    action_value = json.loads(view["private_metadata"])
    values = view["state"]["values"]
    action_value["blocker"] = values["blocker_input"]["blocker_text"]["value"] or "None"
    action_value["digest"] = values["digest_input"]["digest_text"]["value"] or action_value["digest"]
    commit_checkin(action_value, body["user"]["name"])
    user_id = body["user"]["id"]
    client.chat_postMessage(channel=user_id, text="✅ Your adjusted check-in is synced to the dashboard.")
    publish_home(user_id, client)


@app.action("confirm_checkin")
def handle_confirm_checkin(ack, body, client):
    """
    Founder clicked 'Confirm': Write to Supabase & Emit Live Signal
    """
    ack()
    action_value = json.loads(body["actions"][0]["value"])
    user_id = body["user"]["id"]
    channel_id = body["channel"]["id"]
    message_ts = body["message"]["ts"]

    commit_checkin(action_value, body["user"]["name"])
    publish_home(user_id, client)

    # 3. Update original Slack card to locked confirmed state
    client.chat_update(
        channel=channel_id,
        ts=message_ts,
        text="✅ Synchronized to Venture Dashboard!",
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"✅ *Logged to Venture Command Center!*\n"
                        f"• Deliverable: *{action_value['deliverable_id']}*\n"
                        f"• Status: *{action_value['status']} ({action_value['progress']}%)*\n"
                        f"• Synthesis: _{action_value['digest']}_\n"
                        f"• Mentors notified on live dashboard."
                    ),
                },
            }
        ],
    )


@app.action("edit_checkin")
def handle_edit_checkin(ack, body, client):
    """
    Founder clicked 'Adjust Details': Opens Slack modal for quick override.
    """
    ack()
    trigger_id = body["trigger_id"]
    action_value = json.loads(body["actions"][0]["value"])

    client.views_open(
        trigger_id=trigger_id,
        view={
            "type": "modal",
            "callback_id": "modal_edit_checkin",
            "private_metadata": json.dumps(action_value),
            "title": {"type": "plain_text", "text": "Adjust Check-In"},
            "submit": {"type": "plain_text", "text": "Save & Sync"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": [
                {
                    "type": "input",
                    "block_id": "blocker_input",
                    "label": {"type": "plain_text", "text": "Blocker Details"},
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "blocker_text",
                        "initial_value": action_value.get("blocker", "None"),
                    },
                },
                {
                    "type": "input",
                    "block_id": "digest_input",
                    "label": {"type": "plain_text", "text": "Summary for Mentors"},
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "digest_text",
                        "initial_value": action_value.get("digest", ""),
                        "multiline": True,
                    },
                },
            ],
        },
    )


# --- BACKGROUND PROACTIVE CHASER & NUDGE WORKER ---

def audit_deadlines_and_blockers():
    """
    Runs daily to:
    1. Alert teams with upcoming deadlines (<48h) lacking a submission.
    2. Proactively DM founders stuck on blockers for >48h.
    """
    print(f"[{datetime.now().isoformat()}] Running proactive studio audit...")
    if not supabase:
        print("Supabase connection not active; skipping automated chaser pass.")
        return

    try:
        # Check blocked items older than 48 hours
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        res = (
            supabase.table("submissions")
            .select("*, startups(*), founders(*)")
            .eq("status", "Blocked")
            .lt("created_at", cutoff)
            .execute()
        )
        for item in res.data or []:
            founder = item.get("founders", {})
            slack_id = founder.get("slack_user_id")
            startup = item.get("startups", {})
            lead = startup.get("lead", "Studio Lead")

            if slack_id and SLACK_BOT_TOKEN:
                app.client.chat_postMessage(
                    channel=slack_id,
                    text=(
                        f"Hey {founder.get('name', 'there')}! 👋 The dashboard shows you've been blocked on: "
                        f"*{item.get('blocker')}* for over 48 hours.\n\n"
                        f"Would you like me to schedule a priority unblocking sync with your lead ({lead})?"
                    ),
                )
    except Exception as e:
        print(f"[Audit Error]: {e}")


# --- SCHEDULING MEETINGS ---

def build_meeting_card(m: dict) -> list:
    nl = chr(10)
    if m.get("kind") == "change":
        if m["action"] == "cancel":
            body = (f"I'll *cancel* {m['title']} ({m['old']}). The {m['attendee_count']} people invited will be told.")
            yes, no = "Cancel meeting & notify", "Keep it"
        else:
            body = (f"I'll *move* {m['title']}{nl}From: {m['old']}{nl}To: *{m['new']}*{nl}"
                    f"The {m['attendee_count']} people invited get an updated invitation.")
            yes, no = "Reschedule & notify", "Keep as is"
        return [
            {"type": "section", "text": {"type": "mrkdwn", "text": body}},
            {"type": "actions", "elements": [
                {"type": "button", "style": "primary" if m["action"] != "cancel" else "danger", "text": {"type": "plain_text", "text": yes},
                 "action_id": "confirm_meeting", "value": m["id"]},
                {"type": "button", "text": {"type": "plain_text", "text": no}, "action_id": "cancel_meeting", "value": m["id"]}]},
        ]
    begin = datetime.fromisoformat(m["begin"])
    end = datetime.fromisoformat(m["end"])
    names = ", ".join(a["name"] for a in m["attendees"][:12]) + (f" and {len(m['attendees']) - 12} more" if len(m["attendees"]) > 12 else "")
    where = "Online (a Google Meet link will be added)" if meetings.is_virtual(m["where"]) else m["where"]
    repeat = {"weekly": "every week", "fortnightly": "every two weeks", "monthly": "every month"}.get(m.get("repeat") or "", "")
    lines = [f"*{m['title']}*", f"🗓 {meetings.format_when(begin, end)}" + (f" · repeats {repeat}" if repeat else ""),
             f"📍 {where}", f"👥 {len(m['attendees'])} invited: {names}"]
    if m.get("missing"):
        lines.append("⚠️ Not invited (no match or no email on file): " + ", ".join(m["missing"]))
    for c in m.get("conflicts") or []:
        lines.append(f"⚠️ Overlaps with *{c}* for some of the same people")
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": "Here's the meeting I'll create. Invitations are emailed as soon as you confirm." + nl + nl.join(lines)}},
        {"type": "actions", "elements": [
            {"type": "button", "style": "primary", "text": {"type": "plain_text", "text": "Create & send invites"},
             "action_id": "confirm_meeting", "value": m["id"]},
            {"type": "button", "text": {"type": "plain_text", "text": "Cancel"}, "action_id": "cancel_meeting", "value": m["id"]}]},
    ]


@app.action("confirm_meeting")
def handle_confirm_meeting(ack, body, client):
    ack()
    user_id = body["user"]["id"]
    channel, ts = body["channel"]["id"], body["message"]["ts"]

    def finish(text):
        client.chat_update(channel=channel, ts=ts, text=text, blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": text}}])

    row = memory.get_meeting(body["actions"][0]["value"])
    if not row:
        finish("That meeting request has expired or was already handled.")
        return
    if row["requested_by"] != user_id:
        client.chat_postEphemeral(channel=channel, user=user_id, text="Only the person who asked for this meeting can confirm it.")
        return
    m, studio = row["payload"], studio_row()
    if not (gcal and studio):
        finish("⚠️ The studio calendar isn't connected, so I couldn't do that.")
        return
    try:
        if m.get("kind") == "change":
            if not (get_role(user_id) == "mentor" or m.get("requester_slack") == user_id):
                client.chat_postEphemeral(channel=channel, user=user_id, text="Only a mentor or the person who set this meeting up can change it.")
                return
            if m["action"] == "cancel":
                gcal.delete_event(studio["refresh_token"], m["event_id"])
                finish(f"🗑 *{m['title']}* ({m['old']}) is cancelled. Everyone invited was told.")
            else:
                gcal.update_event(studio["refresh_token"], m["event_id"], {
                    "start": {"dateTime": m["new_begin"], "timeZone": "Asia/Singapore"},
                    "end": {"dateTime": m["new_end"], "timeZone": "Asia/Singapore"}})
                finish(f"✅ *{m['title']}* moved to *{m['new']}*. Everyone invited got an updated invitation.")
            memory.delete_meeting(row["id"])
            _studio_cache["at"] = 0.0
            return
        begin, end = datetime.fromisoformat(m["begin"]), datetime.fromisoformat(m["end"])
        description = (f"Requested by {m['requester']} through VentureOS. Join with the Google account this invitation was sent to.")
        event = gcal.create_event(studio["refresh_token"], meetings.build_event_body(
            m["title"], begin, end, m["where"], m["attendees"], description, m.get("repeat"), m.get("requester_slack")))
        memory.delete_meeting(row["id"])
        _studio_cache["at"] = 0.0
        link, meet = event.get("htmlLink"), event.get("hangoutLink")
        note = ""
        if meet:  # let guests in without anyone signing in to the studio account to admit them
            code = google_calendar.meet_code(meet)
            ok = bool(code) and gcal.open_meet(studio["refresh_token"], code)
            note = (" Guests can join without being admitted." if ok else
                    " ⚠️ Guests may need to be admitted: a mentor needs to reconnect the studio calendar once to allow open joining.")
        finish(f"✅ *{m['title']}* is on the calendar for {meetings.format_when(begin, end)}. Invitations went to "
               f"{len(m['attendees'])} people." + (f" <{meet}|Google Meet link>" if meet else f" 📍 {m['where']}")
               + (f" · <{link}|Open in Google Calendar>" if link else "") + note)
    except Exception as e:
        print(f"[Meeting Create Error] {e}")
        finish("⚠️ Google wouldn't do that. The studio calendar connection may need renewing; a mentor can reconnect it.")


@app.action("cancel_meeting")
def handle_cancel_meeting(ack, body, client):
    ack()
    memory.delete_meeting(body["actions"][0]["value"])
    client.chat_update(channel=body["channel"]["id"], ts=body["message"]["ts"], text="Meeting cancelled.",
                       blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": "Meeting cancelled. Nothing was sent."}}])


def studio_connect_blocks(slack_id: str) -> list:
    """Mentor Home: connect the shared studio calendar once, or reconnect it (e.g. to grant a new permission)."""
    url = studio_link(slack_id)
    if not url:
        return []
    row = studio_row()
    if row:
        return [
            {"type": "section", "text": {"type": "mrkdwn", "text": "*Meetings* 🗓" + chr(10) + f"Studio calendar: *{row.get('account', 'connected')}*. "
                                         "Ask me to set up, move or cancel a meeting."}},
            {"type": "actions", "elements": [{"type": "button", "text": {"type": "plain_text", "text": "Reconnect studio calendar"},
                                              "url": url, "action_id": "connect_studio"}]},
        ]
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": (
            "*Meetings* 🗓" + chr(10) + "Connect the studio Google Calendar once and I can set up meetings with the cohort when you ask "
            "(\"set up a meet with everyone at 3 PM on Thursday at 111 Somerset\"). You confirm each one before invitations go out.")}},
        {"type": "actions", "elements": [{"type": "button", "style": "primary", "text": {"type": "plain_text", "text": "Connect studio calendar"},
                                          "url": url, "action_id": "connect_studio"}]},
    ]


@app.action("connect_studio")
def handle_connect_studio(ack):
    ack()  # link button


# --- GOOGLE CALENDAR ---

@app.action("connect_google")
def handle_connect_google(ack):
    ack()  # link button


def team_emails_for(startup_id: str) -> set:
    """Everyone whose meetings with the founder are NOT 'outside the team': co-founders and all mentors."""
    emails = set()
    for table, filt in (("founders", {"startup_id": startup_id}), ("mentors", {})):
        q = supabase.table(table).select("email")
        for k, v in filt.items():
            q = q.eq(k, v)
        emails |= {r["email"].lower() for r in (q.execute().data or []) if r.get("email")}
    return emails


def sync_calendar(row: dict):
    try:
        n = google_calendar.sync_signals(gcal, supabase, row, team_emails_for(row["startup_id"]))
        print(f"[Calendar] synced {n} day(s) for {row.get('account')}")
    except Exception as e:
        print(f"[Calendar Sync Warning] {row.get('account')}: {e}")


def sync_all_calendars():
    if not (gcal and supabase):
        return
    try:
        rows = supabase.table("integrations").select("*").eq("provider", "google").execute().data or []
    except Exception as e:
        print(f"[Calendar Warning] {e}")
        return
    for row in rows:
        sync_calendar(row)


def process_google_pending():
    """Exchanges the one-time codes our website parked for tokens, stores them encrypted, and confirms in Slack."""
    if not (gcal and supabase and SLACK_BOT_TOKEN):
        return
    try:
        pending = supabase.table("google_pending").select("*").execute().data or []
    except Exception as e:
        print(f"[Calendar Pending Warning] {e}")
        return
    for item in pending:
        try:
            supabase.table("google_pending").delete().eq("id", item["id"]).execute()  # single use, whatever happens next
            got = gcal.exchange_code(item["code"])
            if item.get("kind") == "studio":
                if not got.get("refresh_token"):
                    raise RuntimeError("Google returned no refresh token")
                supabase.table("studio_calendar").upsert({
                    "id": "primary", "account": got["email"], "connected_by": item.get("slack_user_id"),
                    "refresh_token": google_calendar.encrypt_token(got["refresh_token"], STATE_SECRET)}).execute()
                if item.get("slack_user_id"):
                    app.client.chat_postMessage(channel=item["slack_user_id"], text=(
                        f"✅ *Studio calendar connected* ({got['email']}). Anyone can now ask me to set up a meeting, and I'll "
                        "show a confirmation card before any invitation is sent."))
                    publish_home(item["slack_user_id"], app.client)
                continue
            if not got.get("refresh_token"):
                raise RuntimeError("Google returned no refresh token")
            row = {"startup_id": item["startup_id"], "founder_id": item["founder_id"], "provider": "google",
                   "external_id": got["email"], "account": got["email"],
                   "refresh_token": google_calendar.encrypt_token(got["refresh_token"], STATE_SECRET),
                   "notified_at": datetime.now(timezone.utc).isoformat()}
            supabase.table("integrations").upsert(row, on_conflict="provider,external_id").execute()
            founder = supabase.table("founders").select("slack_user_id").eq("id", item["founder_id"]).execute().data
            slack_id = founder[0]["slack_user_id"] if founder else None
            if slack_id:
                app.client.chat_postMessage(channel=slack_id, text=(
                    f"✅ *Google Calendar connected* ({got['email']}). I'll count your meetings and how many were with people "
                    "outside your team. I never store titles, descriptions or who was invited, and you can ask me "
                    "\"what's on my calendar tomorrow?\" any time. Syncing the last 2 weeks now..."))
            full = supabase.table("integrations").select("*").eq("provider", "google").eq("external_id", got["email"]).execute().data
            if full:
                threading.Thread(target=lambda r=full[0], sid=slack_id: (sync_calendar(r), sid and publish_home(sid, app.client)),
                                 daemon=True).start()
        except Exception as e:
            print(f"[Calendar Connect Error] {e}")


# --- MENTOR DIGEST & NUDGES ---

WEEKLY_DIGEST = os.environ.get("WEEKLY_DIGEST", "on").lower() != "off"
MENTOR_ALERTS = os.environ.get("MENTOR_ALERTS", "on").lower() != "off"
_alerts_seen_memory: set = set()  # fallback while the mentor_alerts table doesn't exist


def mentor_slack_ids() -> list:
    try:
        rows = supabase.table("mentors").select("slack_user_id").execute().data or []
    except Exception as e:
        print(f"[Mentor Lookup Warning] {e}")
        return []
    return [r["slack_user_id"] for r in rows if re.fullmatch(r"[UW][A-Z0-9]{8,}", r.get("slack_user_id") or "")]


def alert_seen(key: str) -> bool:
    if key in _alerts_seen_memory:
        return True
    try:
        return bool(supabase.table("mentor_alerts").select("key").eq("key", key).execute().data)
    except Exception:
        return False


def alert_mark(key: str):
    _alerts_seen_memory.add(key)
    try:
        supabase.table("mentor_alerts").upsert({"key": key}).execute()
    except Exception:
        pass  # table not created yet: the in-memory set still prevents repeats until the next restart


def blocks_to_text(blocks: list) -> str:
    out = []
    for bl in blocks:
        if isinstance(bl.get("text"), dict):
            out.append(bl["text"].get("text", ""))
        for el in bl.get("elements", []) if isinstance(bl.get("elements"), list) else []:
            if isinstance(el.get("text"), str):
                out.append(el["text"])
    return chr(10).join(t for t in out if t)


def _today_sgt():
    return datetime.now(timezone(timedelta(hours=8))).date()


def send_weekly_digest(dry_run: bool = False):
    """Monday-morning summary DM for every mentor. Also marks today's nudge candidates as told, so they aren't repeated."""
    today = _today_sgt()
    if not (supabase and syllabus.has_session(today)):
        return []
    summaries = safe_snapshot()
    blocks = digest.build_digest_blocks(summaries, today, upcoming_meeting_items(), memory.open_tasks())
    if dry_run:
        return blocks
    sent = []
    for uid in mentor_slack_ids():
        try:
            app.client.chat_postMessage(channel=uid, text="Weekly digest", blocks=blocks + dashboard_button_blocks(slack_user_id=uid))
            sent.append(uid)
        except Exception as e:
            print(f"[Digest Error] {uid}: {e}")
    for a in digest.alert_candidates(summaries, today):
        alert_mark(a["key"])
    return sent


def run_mentor_alerts(dry_run: bool = False) -> list:
    """Daily 09:15: tell mentors about NEW things that need them (blocked 3+ days, gone quiet, talking but not building)."""
    today = _today_sgt()
    if not (supabase and syllabus.has_session(today)):
        return []
    fresh = [a for a in digest.alert_candidates(safe_snapshot(), today) if not alert_seen(a["key"])]
    if not fresh or dry_run:
        return fresh
    text = "*Heads up from Venture Buddy*" + chr(10) + chr(10).join(a["text"] for a in fresh)
    for uid in mentor_slack_ids():
        try:
            app.client.chat_postMessage(channel=uid, text="Heads up", blocks=[
                {"type": "section", "text": {"type": "mrkdwn", "text": text}},
                {"type": "context", "elements": [{"type": "mrkdwn", "text": "Ask me about any of them, e.g. _\"what's going on with Auvira?\"_"}]}])
        except Exception as e:
            print(f"[Alert Error] {uid}: {e}")
    for a in fresh:
        alert_mark(a["key"])
    return fresh


def run_weekly_digest():
    if WEEKLY_DIGEST and SLACK_BOT_TOKEN:
        print(f"[Digest] sent to {len(send_weekly_digest())} mentor(s)")


def run_alerts():
    if MENTOR_ALERTS and SLACK_BOT_TOKEN:
        print(f"[Alerts] {len(run_mentor_alerts())} new alert(s)")


# --- MEETING REMINDERS ---

def send_meeting_reminders():
    """About an hour before a studio-calendar meeting, DM each invited person who is in Slack (once per person per meeting)."""
    if not (gcal and supabase and SLACK_BOT_TOKEN and studio_connected()):
        return
    now = datetime.now(timezone.utc)
    due = [ev for ev in studio_events_cached() if meetings.reminder_due(ev, now)]
    if not due:
        return
    people = {}
    for table in ("founders", "mentors"):
        for r in supabase.table(table).select("email,slack_user_id").execute().data or []:
            if r.get("email") and re.fullmatch(r"[UW][A-Z0-9]{8,}", r.get("slack_user_id") or ""):
                people[r["email"].lower()] = r["slack_user_id"]
    for ev in due:
        begin, end = meetings.event_times(ev)
        where = f"<{ev['hangoutLink']}|Join the Google Meet>" if ev.get("hangoutLink") else (ev.get("location") or "")
        text = f"⏰ *{ev.get('summary', 'Meeting')}* starts in about an hour ({meetings.time_12h(begin)}–{meetings.time_12h(end)})" + (f" · {where}" if where else "")
        for a in ev.get("attendees") or []:
            uid = people.get((a.get("email") or "").lower())
            key = f"remind:{ev.get('id')}:{begin.isoformat()}:{uid}"
            if uid and a.get("responseStatus") != "declined" and not alert_seen(key):
                try:
                    app.client.chat_postMessage(channel=uid, text=text)
                    alert_mark(key)
                except Exception as e:
                    print(f"[Reminder Error] {uid}: {e}")


# --- HEALTH HEARTBEAT ---

_socket_handler = None  # set when the Socket Mode connection starts


def beat():
    """Tells the site the bot is alive. slack_connected is the real state of the Slack websocket, not just 'process running'."""
    if not supabase:
        return
    try:
        connected = bool(_socket_handler and _socket_handler.client.is_connected())
        supabase.table("bot_heartbeat").upsert({"id": "main", "beat_at": datetime.now(timezone.utc).isoformat(),
                                                "slack_connected": connected, "version": "venture-buddy"}).execute()
    except Exception as e:
        print(f"[Heartbeat Warning] {e}")


# --- KEEP HOME TABS FRESH ---

_home_watch = {"since": datetime.now(timezone.utc).isoformat()}
HOME_TABLES = (("signals", "created_at", "startup_id"), ("submissions", "created_at", "startup_id"),
               ("milestones", "updated_at", "startup_id"), ("tasks", "created_at", "startup_id"),
               ("integrations", "created_at", "startup_id"))


def refresh_changed_homes():
    """
    Every few seconds: find startups with new activity (commits, check-ins, milestones, tasks, connections) and
    republish the Home tab of their founders and of every mentor, so the page never goes stale.
    """
    if not (supabase and SLACK_BOT_TOKEN):
        return
    since, latest, startups = _home_watch["since"], _home_watch["since"], set()
    for table, stamp, key in HOME_TABLES:
        try:
            rows = supabase.table(table).select(f"{key},{stamp}").gt(stamp, since).limit(200).execute().data or []
        except Exception:
            continue
        for r in rows:
            startups.add(r[key])
            latest = max(latest, r[stamp])
    _home_watch["since"] = latest
    if not startups:
        return
    try:
        slack_ids = {f["slack_user_id"] for f in (supabase.table("founders").select("slack_user_id,startup_id")
                                                  .in_("startup_id", list(startups)).execute().data or []) if f.get("slack_user_id")}
        slack_ids |= {m["slack_user_id"] for m in (supabase.table("mentors").select("slack_user_id").execute().data or [])
                      if m.get("slack_user_id")}
    except Exception as e:
        print(f"[Home Refresh Warning] {e}")
        return
    for uid in slack_ids:
        publish_home(uid, app.client)


# --- GITHUB CONNECTION CONFIRMATION & REPO PICKER ---

_poll_warned = False


def poll_new_connections():
    """Confirms freshly connected GitHub installs in Slack and offers the repo picker."""
    if not (supabase and SLACK_BOT_TOKEN):
        return
    try:
        rows = supabase.table("integrations").select("*").eq("provider", "github").is_("notified_at", "null").execute().data or []
    except Exception as e:
        global _poll_warned
        if not _poll_warned:  # most likely the 2026-10-github-repos.sql migration hasn't been run yet
            print(f"[GitHub Poll Warning] {e} (will keep retrying quietly)")
            _poll_warned = True
        return
    now = datetime.now(timezone.utc)
    for row in rows:
        row = refresh_repos(row)
        age = (now - datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))).total_seconds()
        if not row.get("repos") and not gh and age < 60:
            continue  # GitHub's repo list usually lands within seconds; give it a moment
        try:
            founder = supabase.table("founders").select("slack_user_id,startups(name)").eq("id", row["founder_id"]).execute().data
            slack_id = founder[0]["slack_user_id"] if founder else None
            if slack_id:
                headline = integrations.connected_headline(row, (founder[0].get("startups") or {}).get("name", "your startup"))
                app.client.chat_postMessage(channel=slack_id, text="GitHub connected",
                                            blocks=integrations.build_repo_selector(row, headline))
                publish_home(slack_id, app.client)
                if len(row.get("repos") or []) == 1:
                    backfill_in_background(row, slack_id)  # one repo: nothing to choose, so start right away
            supabase.table("integrations").update({"notified_at": now.isoformat()}).eq("id", row["id"]).execute()
        except Exception as e:
            print(f"[GitHub Poll Error] {e}")


def _owns_integration(user_id: str, integration_id: str):
    """The integration row if this Slack user is a founder of its startup, else None."""
    rows = supabase.table("integrations").select("*").eq("id", integration_id).execute().data
    if not rows:
        return None
    mine = supabase.table("founders").select("id").eq("slack_user_id", user_id).eq("startup_id", rows[0]["startup_id"]).execute().data
    return rows[0] if mine else None


def _stale_connection(client, user_id: str):
    """Old Home tab or message pointing at a connection that no longer exists (or isn't theirs): say so and refresh."""
    client.chat_postMessage(channel=user_id, text=(
        "That GitHub connection no longer exists (it may have been removed), so I can't change it. "
        "I've refreshed your Home tab. Press *Connect GitHub* there to link it again."))
    publish_home(user_id, client)


@app.action("select_repos")
def handle_select_repos(ack, body, client):
    ack()
    user_id = body["user"]["id"]
    action = body["actions"][0]
    integration_id = action["block_id"].removeprefix("repos_")
    try:
        row = _owns_integration(user_id, integration_id)
        if not row:
            _stale_connection(client, user_id)
            return
        chosen = [o["value"] for o in action.get("selected_options", [])]
        supabase.table("integrations").update({"selected_repos": chosen or None}).eq("id", integration_id).execute()
        row["selected_repos"] = chosen or None
        names = ", ".join(f"*{r}*" for r in integrations.monitored_repos(row))
        headline = (f"✅ Now monitoring {names}. You can change this any time." if chosen
                    else "I'm not tracking any repository right now. Pick one below when you're ready.")
        if (body.get("container") or {}).get("type") == "message":  # picked from a DM: update that message
            client.chat_update(channel=body["channel"]["id"], ts=body["message"]["ts"], text="Repositories updated",
                               blocks=integrations.build_repo_selector(row, headline))
        publish_home(user_id, client)  # the Home tab always reflects the choice straight away
        if chosen:
            backfill_soon(row, user_id)
    except Exception as e:
        print(f"[Repo Select Error] {e}")


@app.action("change_repos")
def handle_change_repos(ack, body, client):
    ack()
    user_id = body["user"]["id"]
    try:
        row = _owns_integration(user_id, body["actions"][0]["value"])
        if not row:
            _stale_connection(client, user_id)
        else:
            row = refresh_repos(row)
            client.chat_postMessage(channel=user_id, text="Choose repositories",
                                    blocks=integrations.build_repo_selector(row, "Which repositories should I monitor?"))
    except Exception as e:
        print(f"[Change Repos Error] {e}")


@app.action("connect_github")
def handle_noop_link_button(ack):
    ack()  # link buttons still send an interaction event; acknowledge so Slack doesn't show a warning


@app.action("connect_github_home")
def handle_noop_link_button_home(ack):
    ack()


# --- GITHUB ORGANISATIONS (an owner must approve the install) ---

@app.action("claim_org")
def handle_claim_org(ack, body, client):
    ack()
    user_id = body["user"]["id"]
    founder_id, startup_id = body["actions"][0]["value"].split("|", 1)
    own = supabase.table("founders").select("id").eq("id", founder_id).eq("slack_user_id", user_id).execute().data
    if not own:
        return
    client.views_open(trigger_id=body["trigger_id"], view={
        "type": "modal", "callback_id": "modal_claim_org", "private_metadata": body["actions"][0]["value"],
        "title": {"type": "plain_text", "text": "GitHub organisation"},
        "submit": {"type": "plain_text", "text": "Link it"}, "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text": (
                "Type the organisation's GitHub name (the part after `github.com/`). "
                "If you're not an owner, press *Connect GitHub* first and choose that organisation: GitHub will send the owners "
                "an approval request. I'll link it automatically once it's approved.")}},
            _text_input("org_input", "org_text", "Organisation name", max_length=39),
        ],
    })


@app.view("modal_claim_org")
def handle_claim_org_submit(ack, body, client, view):
    org = (view["state"]["values"]["org_input"]["org_text"]["value"] or "").strip().removeprefix("https://github.com/").strip("/")
    if not integrations.valid_org_login(org):
        ack(response_action="errors", errors={"org_input": "That doesn't look like a GitHub organisation name."})
        return
    ack()
    user_id = body["user"]["id"]
    founder_id, startup_id = view["private_metadata"].split("|", 1)
    try:
        own = supabase.table("founders").select("id").eq("id", founder_id).eq("slack_user_id", user_id).execute().data
        if not own:
            return
        supabase.table("github_claims").insert({"startup_id": startup_id, "founder_id": founder_id, "org_login": org}).execute()
        supabase.table("signals").insert({"startup_id": startup_id, "type": "ai_digest", "stream": "Tech", "actor": "Studio AI",
                                          "headline": f"A founder asked to link GitHub organisation {org}"}).execute()
        client.chat_postMessage(channel=user_id, text=(
            f"👍 Noted: *{org}*. Once the app is installed on that organisation (an owner may need to approve the request "
            "GitHub sends them), I'll link it to your startup and message you here to choose the repository. "
            "This request stays open for 14 days."))
        link_org_claims()  # in case it's already installed
    except Exception as e:
        print(f"[Org Claim Error] {e}")
        client.chat_postMessage(channel=user_id, text="Something went wrong saving that. Did you run the latest SQL migration?")


def link_org_claims():
    """Links claimed organisations whose app installation now exists (approved by an owner)."""
    if not supabase:
        return
    for claim in integrations.open_claims(supabase):
        try:
            found = None
            if gh:
                found = gh.installation_for(claim["org_login"])
            if not found:
                staged = supabase.table("github_installations").select("installation_id,account").ilike("account", claim["org_login"]).execute().data
                found = {"id": staged[0]["installation_id"], "account": staged[0]["account"]} if staged else None
            if not found:
                continue
            existing = supabase.table("integrations").select("id").eq("provider", "github").eq("external_id", found["id"]).execute().data
            if not existing:
                supabase.table("integrations").insert({
                    "startup_id": claim["startup_id"], "founder_id": claim["founder_id"], "provider": "github",
                    "external_id": found["id"], "account": found["account"], "repos": []}).execute()
            # An installation already linked to someone else is never re-pointed by a claim; the claim just closes.
            supabase.table("github_claims").update({"resolved_at": datetime.now(timezone.utc).isoformat()}).eq("id", claim["id"]).execute()
        except Exception as e:
            print(f"[Org Claim Warning] {e}")


# --- DEVELOPER PAGE: commands queued from the dashboard (only the developer can queue them) ---

DEV_EMAILS = {e.strip().lower() for e in os.environ.get("DEV_EMAILS", "ben@evecount.com").split(",") if e.strip()}


def is_developer(slack_user_id: str) -> bool:
    if not (supabase and slack_user_id):
        return False
    try:
        rows = supabase.table("mentors").select("email").eq("slack_user_id", slack_user_id).limit(1).execute().data
        return bool(rows and (rows[0].get("email") or "").lower() in DEV_EMAILS)
    except Exception:
        return False


def prune_dev_data():
    print(f"[Channels] pruned {channels.prune()} messages older than 7 days")
    dev_controls.prune_logs(supabase)


def granted_scopes() -> list:
    try:
        return sorted(s for s in (app.client.auth_test().headers.get("x-oauth-scopes") or "").replace(" ", "").split(",") if s)
    except Exception as e:
        print(f"[Dev Warning] scopes: {e}")
        return []


def dev_status(_args, _by) -> str:
    scopes = granted_scopes()
    missing = [s for s in NEEDED_SCOPES if s not in scopes]
    try:
        supabase.table("bot_heartbeat").update({"scopes": ",".join(scopes)}).eq("id", "main").execute()
    except Exception as e:
        print(f"[Dev Warning] heartbeat scopes: {e}")
    connected = bool(_socket_handler and _socket_handler.client.is_connected())
    return (f"Model: {settings.get('ai_model') or AI_MODEL} · agent {'on' if agent else 'OFF'} · "
            f"Slack {'connected' if connected else 'NOT connected'}\n"
            f"Scopes: {', '.join(scopes) or 'unknown'}\n"
            + (f"Missing for channel reading: {', '.join(missing)}" if missing else "All channel-reading scopes granted."))


def _dev_target(args, by):
    who = str(args.get("as_slack_id") or by or "").strip()
    return who, get_role(who) if who else None


def dev_ask(args, by) -> str:
    """Asks the agent as the developer (or as someone else, to preview their answer). Tools run for real."""
    who, role = _dev_target(args, by)
    if agent is None or role is None:
        return "The agent is off, or that Slack id isn't a mentor or founder."
    result = agent.respond(build_identity(who, role), str(args.get("text") or "")[:4000])
    cards = [k for k in ("checkin", "rename", "meeting") if result.get(k)]
    return result["text"] + (f"\n\n(In Slack this would also show a {', '.join(cards)} card to confirm.)" if cards else "")


def dev_context(args, by) -> str:
    who, role = _dev_target(args, by)
    if agent is None or role is None:
        return "The agent is off, or that Slack id isn't a mentor or founder."
    return agent._system(build_identity(who, role))


def dev_post(args, _by) -> str:
    channel, text = str(args.get("channel_id") or ""), str(args.get("text") or "").strip()
    if not (channel and text):
        return "Pick a channel and write a message."
    app.client.chat_postMessage(channel=channel, text=text)
    return "Posted."


def dev_republish(_args, _by) -> str:
    ids = set()
    for table in ("founders", "mentors"):
        ids |= {r["slack_user_id"] for r in (supabase.table(table).select("slack_user_id").execute().data or [])
                if r.get("slack_user_id")}
    for uid in ids:
        publish_home(uid, app.client)
    return f"Republished {len(ids)} Home tabs."


def dev_daily_preview(_args, _by) -> str:
    prompts = send_daily_prompts(None, supabase, memory, dry_run=True)
    nudges = send_nudges(None, supabase, memory, dry_run=True)
    body = "\n\n".join(f"to {uid}:\n{text}" for uid, text in prompts) or "No prompts would go out right now."
    return f"{body}\n\nNudges that would go out now: {len(nudges)}"


def dev_clear_history(args, by) -> str:
    who = str(args.get("as_slack_id") or by or "").strip()
    supabase.table("bot_messages").delete().eq("slack_user_id", who).execute()
    return f"Cleared the bot's recent conversation memory with {who}."


DEV_COMMANDS = {
    "status": dev_status,
    "refresh_channels": lambda _a, _b: channels.refresh_list(),
    "sync_channel": lambda a, _b: channels.activate(str(a.get("channel_id") or "")),
    "prune": lambda _a, _b: f"Removed {channels.prune()} messages older than 7 days.",
    "ask": dev_ask,
    "show_context": dev_context,
    "post_message": dev_post,
    "republish_homes": dev_republish,
    "daily_preview": dev_daily_preview,
    "clear_history": dev_clear_history,
}


# --- DEVELOPER VIEW ON THE SLACK HOME TAB (developers only; every handler re-checks) ---

_home_mode: dict = {}   # slack_id -> "dev" | "mentor"
_dev_last: dict = {}    # slack_id -> {"label", "text", "working"}: tool result shown under the Tools buttons
_channels_note: dict = {}  # slack_id -> result of the last "Refresh list", shown under the Channels heading
_scope_cache = {"at": 0.0, "scopes": []}
DEV_LABELS = {"status": "Status & scopes", "show_context": "What the bot sees", "daily_preview": "Preview daily prompts",
              "republish_homes": "Republish Home tabs", "clear_history": "Clear my chat memory",
              "refresh_channels": "Refresh channel list"}


def dev_home_state(uid: str) -> dict:
    import time as _time
    if _time.time() - _scope_cache["at"] > 3600:
        _scope_cache.update(at=_time.time(), scopes=granted_scopes())
    missing = [s for s in NEEDED_SCOPES if _scope_cache["scopes"] and s not in _scope_cache["scopes"]]
    connected = bool(_socket_handler and _socket_handler.client.is_connected())
    status = (f"{'🟢 Slack connected' if connected else '🔴 Slack not connected'} · agent {'on' if agent else 'OFF'} · "
              f"model `{settings.get('ai_model') or AI_MODEL}`"
              + (f" · ⚠️ missing scopes: {', '.join(missing)}" if missing else ""))
    try:
        chans = supabase.table("bot_channels").select("id,name,is_private,num_members,enabled,status").order("name").execute().data or []
    except Exception as e:
        chans, status = [], status + f" · ⚠️ channel table unavailable ({e})"[:200]
    try:
        logs = (supabase.table("bot_logs").select("line,created_at").or_("line.ilike.*warning*,line.ilike.*error*")
                .order("id", desc=True).limit(8).execute().data or [])
        sgt = timezone(timedelta(hours=8))
        warnings = [datetime.strptime(r["created_at"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                    .astimezone(sgt).strftime("%d %b %I:%M %p") + f"  {r['line'][:300]}" for r in logs]
    except Exception:
        warnings = []
    return {"status": status, "settings": settings.all(), "channels": chans, "last": _dev_last.get(uid), "warnings": warnings,
            "channels_note": _channels_note.get(uid)}


def publish_dev_home(uid: str, client=None):
    try:
        (client or app.client).views_publish(user_id=uid, view={"type": "home", "blocks": dev_home.build_dev_home(dev_home_state(uid))})
    except Exception as e:
        print(f"[Dev Home Error] {e}")


def _developer(body) -> str | None:
    uid = body["user"]["id"]
    return uid if is_developer(uid) else None


def _in_background(fn):
    threading.Thread(target=fn, daemon=True).start()


@app.action("home_mode_dev")
def handle_home_mode_dev(ack, body, client):
    ack()
    uid = _developer(body)
    if uid:
        _home_mode[uid] = "dev"
        publish_home(uid, client)


@app.action("home_mode_mentor")
def handle_home_mode_mentor(ack, body, client):
    ack()
    uid = body["user"]["id"]
    _home_mode.pop(uid, None)
    publish_home(uid, client)


@app.action("dev_channel_toggle")
def handle_dev_channel_toggle(ack, body, client):
    ack()
    uid = _developer(body)
    if not uid:
        return
    act = body["actions"][0]
    cid, turn_on = act["value"], act["text"]["text"] == "Turn on"
    print(f"[Dev] channel {cid} {'on' if turn_on else 'off'} by {uid}")

    def run():
        now = datetime.now(timezone.utc).isoformat()
        try:
            supabase.table("bot_channels").update({"enabled": turn_on, "updated_at": now,
                                                   "status": "Syncing…" if turn_on else "Off. Its messages were forgotten."}).eq("id", cid).execute()
            if not turn_on:
                supabase.table("channel_messages").delete().eq("channel_id", cid).execute()
        except Exception as e:
            print(f"[Dev Warning] channel toggle: {e}")
        channels.forget_cache()
        publish_dev_home(uid, client)
        if turn_on:
            channels.activate(cid)
            publish_dev_home(uid, client)
    _in_background(run)


@app.action("dev_refresh_channels")
def handle_dev_refresh_channels(ack, body, client):
    ack()
    uid = _developer(body)
    if uid:
        def run():
            _channels_note[uid] = "⏳ Refreshing…"
            publish_dev_home(uid, client)
            _channels_note[uid] = channels.refresh_list()
            publish_dev_home(uid, client)
        _in_background(run)


@app.action("dev_setting_toggle")
def handle_dev_setting_toggle(ack, body, client):
    ack()
    uid = _developer(body)
    key = body["actions"][0]["value"]
    if uid and key in ("paused", "daily_checkin", "channel_context"):
        value = not settings.get(key)
        print(f"[Dev] setting {key}={value} by {uid}: {'saved' if settings.set(key, value) else 'NOT saved'}")
        publish_dev_home(uid, client)


@app.action("dev_edit_settings")
def handle_dev_edit_settings(ack, body, client):
    ack()
    if _developer(body):
        client.views_open(trigger_id=body["trigger_id"], view=dev_home.build_settings_modal(settings.all()))


@app.view("modal_dev_settings")
def handle_dev_settings_submit(ack, body, client, view):
    ack()
    uid = _developer(body)
    if uid:
        values = view["state"]["values"]
        settings.set("ai_model", (values["model"]["v"].get("value") or "").strip())
        settings.set("extra_instructions", (values["extra"]["v"].get("value") or "").strip())
        publish_dev_home(uid, client)


@app.action("dev_test_as")
def handle_dev_test_as(ack, body, client):
    ack()
    if _developer(body):
        client.views_open(trigger_id=body["trigger_id"], view=dev_home.build_test_modal())


@app.view("modal_dev_test")
def handle_dev_test_submit(ack, body, client, view):
    ack()
    uid = _developer(body)
    if not uid:
        return
    values = view["state"]["values"]
    who, text = values["who"]["v"].get("selected_user"), values["text"]["v"].get("value") or ""

    label = f"Test as <@{who}>: “{text[:200]}”"
    print(f"[Dev] test as {who} by {uid}")

    def run():
        _dev_last[uid] = {"label": label, "working": True}
        publish_dev_home(uid, client)
        try:
            answer = dev_ask({"as_slack_id": who, "text": text}, uid)
        except Exception as e:
            answer = f"Error: {type(e).__name__}: {e}"
        _dev_last[uid] = {"label": label, "text": answer}
        publish_dev_home(uid, client)
    _in_background(run)


@app.action("dev_clear_result")
def handle_dev_clear_result(ack, body, client):
    ack()
    uid = _developer(body)
    if uid:
        _dev_last.pop(uid, None)
        publish_dev_home(uid, client)


@app.action(re.compile(r"^dev_cmd_"))
def handle_dev_cmd(ack, body, client):
    ack()
    uid = _developer(body)
    cmd = body["actions"][0]["value"]
    if not uid or cmd not in DEV_COMMANDS:
        return

    print(f"[Dev] {cmd} by {uid}")

    def run():
        _dev_last[uid] = {"label": DEV_LABELS.get(cmd, cmd), "working": True}
        publish_dev_home(uid, client)
        try:
            result = DEV_COMMANDS[cmd]({}, uid)
        except Exception as e:
            result = f"Error: {type(e).__name__}: {e}"
        if cmd == "status":
            _scope_cache["at"] = 0.0
        _dev_last[uid] = {"label": DEV_LABELS.get(cmd, cmd), "text": result}
        publish_dev_home(uid, client)
    _in_background(run)


def resume_channel_syncs():
    """At startup: finish channel syncs a restart interrupted (switched on but still 'Syncing…')."""
    if not supabase:
        return
    try:
        stuck = supabase.table("bot_channels").select("id,name").eq("enabled", True).eq("status", "Syncing…").execute().data or []
    except Exception:
        return
    for c in stuck:
        print(f"[Channels] resuming sync of #{c['name']}: {channels.activate(c['id'])}")


@app.event("message")
def handle_other_message_events(event, say):
    """Registered last: catches messages no listener above took (a file shared with no text)."""
    if event.get("channel_type") == "im" and event.get("user") and any(transcribe.is_audio(f) for f in event.get("files") or []):
        process_inbound_message(event["user"], (event.get("text") or "").strip(), event.get("files") or [], say)  # a voice note on its own
        return
    if event.get("channel_type") in ("channel", "group") and not (event.get("subtype") or "").startswith("message_"):
        channels.ingest(event)


# Initialize scheduler if available (all times Singapore time)
DAILY_CHECKIN = os.environ.get("DAILY_CHECKIN", "on").lower() != "off"
DAILY_CHECKIN_HOUR = int(os.environ.get("DAILY_CHECKIN_HOUR", "17"))


def run_daily_prompts():
    if supabase and SLACK_BOT_TOKEN and settings.get("daily_checkin"):
        print(f"[Daily] prompts sent: {len(send_daily_prompts(app.client, supabase, memory))}")


def run_daily_nudges():
    if supabase and SLACK_BOT_TOKEN and settings.get("daily_checkin"):
        print(f"[Daily] nudges sent: {len(send_nudges(app.client, supabase, memory))}")


if BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="Asia/Singapore")
    scheduler.add_job(audit_deadlines_and_blockers, "cron", hour=9, minute=0)
    scheduler.add_job(poll_new_connections, "interval", seconds=10, max_instances=1)
    scheduler.add_job(refresh_changed_homes, "interval", seconds=15, max_instances=1)
    scheduler.add_job(beat, "interval", seconds=30, max_instances=1)
    scheduler.add_job(send_meeting_reminders, "interval", minutes=5, max_instances=1)
    scheduler.add_job(run_weekly_digest, "cron", day_of_week="mon", hour=9, minute=0)
    scheduler.add_job(run_alerts, "cron", day_of_week="mon-fri", hour=9, minute=15)
    scheduler.add_job(process_google_pending, "interval", seconds=10, max_instances=1)
    scheduler.add_job(sync_all_calendars, "interval", minutes=60, max_instances=1)
    scheduler.add_job(link_org_claims, "interval", seconds=60, max_instances=1)
    scheduler.add_job(lambda: dev_controls.run_commands(supabase, DEV_COMMANDS), "interval", seconds=5, max_instances=1)
    scheduler.add_job(lambda: dev_controls.flush_logs(supabase, log_tee), "interval", seconds=10, max_instances=1)
    scheduler.add_job(prune_dev_data, "interval", minutes=60, max_instances=1)
    scheduler.add_job(lambda: SLACK_BOT_TOKEN and channels.refresh_list(), "interval", hours=6, max_instances=1)
    if DAILY_CHECKIN:
        scheduler.add_job(run_daily_prompts, "cron", day_of_week="mon-fri", hour=DAILY_CHECKIN_HOUR, minute=0)
        scheduler.add_job(run_daily_nudges, "cron", day_of_week="mon-fri", hour=9, minute=30)
    scheduler.start()


# --- CLI SIMULATOR / ENTRY POINT ---

if __name__ == "__main__":
    if "--digest-dry-run" in sys.argv:
        print("=== Weekly digest preview (nothing is sent) ===")
        print(blocks_to_text(send_weekly_digest(dry_run=True) or []))
        print(chr(10) + "=== New mentor nudges right now ===")
        for a in run_mentor_alerts(dry_run=True):
            print("-", a["text"])
        sys.exit(0)
    if "--daily-dry-run" in sys.argv:
        print("Prompts that would be sent now (nothing is sent):")
        for uid, text in send_daily_prompts(None, supabase, memory, dry_run=True):
            print(f"--- to {uid}" + chr(10) + text)
        print("Nudges that would be sent now:", len(send_nudges(None, supabase, memory, dry_run=True)))
        sys.exit(0)
    if "--simulate" in sys.argv or "--dry-run" in sys.argv:
        print("\n=== RUNNING SIMULATED INBOUND CHECK-IN (DRY RUN) ===")
        sample_transcript = (
            "We finished talking to 4 warehouse operations managers. They really hated the AI buzzwords, "
            "so we rewrote the headline to focus on 15% fewer delayed shipments. My blocker right now is "
            "getting feedback on our copy before launching the landing page test."
        )
        ctx = resolve_founder_context("U_NEXUS_LEAD")
        extracted = extract_update_with_ai(sample_transcript, ctx)
        blocks = build_confirmation_card(ctx, extracted, sample_transcript)

        print("\n1. RESOLVED CONTEXT:")
        print(json.dumps(ctx, indent=2))
        print("\n2. STRUCTURED EXTRACTION:")
        print(json.dumps(extracted, indent=2))
        print("\n3. BLOCK KIT CONFIRMATION CARD (PREVIEW):")
        print(f"Header: {blocks[0]['text']['text']}")
        print(f"Status: {extracted['status']} ({extracted['progress']}%)")
        print(f"Blocker: {extracted['blocker']}")
        print(f"Digest: {extracted['digest']}")
        print("Interactive buttons: [Confirm & Sync Dashboard] [Adjust Details]")
        print("\nDry run completed successfully! 🚀\n")
        sys.exit(0)

    print("Venture Studio Slack Bot starting in Socket Mode...")
    if SLACK_BOT_TOKEN and SLACK_APP_TOKEN:
        threading.Thread(target=resume_channel_syncs, daemon=True).start()
        _socket_handler = SocketModeHandler(app, SLACK_APP_TOKEN)
        _socket_handler.start()
    else:
        print(
            "SLACK_BOT_TOKEN or SLACK_APP_TOKEN not provided in .env.\n"
            "Run with 'python slack_bot.py --simulate' to test extraction and card generation in dry-run mode."
        )
