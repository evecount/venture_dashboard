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

# Initialize Supabase Client
supabase: Client = (
    create_client(SUPABASE_URL, SUPABASE_KEY)
    if (create_client and SUPABASE_URL and SUPABASE_KEY)
    else None
)

from mentor_home import build_mentor_blocks as mentor_blocks, summarize_startups
import threading

import github_app
import syllabus
import google_calendar
import meetings
import integrations
from profile_rules import match_person, looks_like_email, norm_name
from daily_checkin import send_daily_prompts, send_nudges
from bot_agent import Agent
from bot_memory import Memory

# Persistent memory + conversational agent (needs both an LLM and the database)
memory = Memory(supabase)
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
                studio_link=studio_link, studio_connected=studio_connected, studio_events=studio_events_fn)
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
    for sm in summaries:
        conn = integrations.connections(supabase, sm["id"])
        sm["work"] = integrations.activity_line(integrations.activity_summary(supabase, sm["id"]), "github" in conn)
    return summaries


def safe_snapshot() -> list:
    try:
        return cohort_overview()
    except Exception as e:
        print(f"[Snapshot Error] {e}")
        return []


def build_mentor_blocks(summaries: list, title: str = "Cohort pulse", tasks: list | None = None) -> list:
    return mentor_blocks(summaries, tasks=tasks, title=title, footer=dashboard_button_blocks())


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
            blocks=build_mentor_blocks(safe_snapshot()),
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
    onboard_member(event["user"], client)


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


def dashboard_button_blocks(founder_id: str | None = None) -> list:
    url = integrations.dashboard_url(DASHBOARD_URL, STATE_SECRET, founder_id)
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


def build_home_view(context: dict | None, latest: dict | None, tasks: list | None = None, milestones: list | None = None, conns: list | None = None, gcal_rows: list | None = None) -> dict:
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
    blocks.append({"type": "divider"})
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "Chat with me any time in the *Messages* tab: updates, blockers, goals or questions. You confirm before anything is saved."}]})
    blocks += dashboard_button_blocks(context["founder_id"])
    return {"type": "home", "blocks": blocks}


def publish_home(slack_user_id: str, client=None):
    """Renders the Home tab for a user. Safe to call after any state change."""
    client = client or app.client
    try:
        role = get_role(slack_user_id)
        if role == "mentor":
            mine = [t for t in memory.open_tasks() if t.get("owner_slack_id") == slack_user_id]
            blocks = build_mentor_blocks(safe_snapshot(), title="Mentor view", tasks=mine) + studio_connect_blocks(slack_user_id)
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
                                               integrations.google_connections(supabase, context["startup_id"]) if context else []))
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


def process_inbound_message(user_id: str, text: str, files: list, say):
    """
    Core pipeline: resolve role, then hand the message to the conversational agent
    (answers, notes, tasks, memory, check-in proposals). Falls back to plain extraction
    when no LLM or database is configured.
    """
    role = get_role(user_id)
    if role is None:
        if not onboard_member(user_id):
            return
        role = get_role(user_id)
        # Linked just now by email; welcome DM already sent, carry on.

    # Read attached files if present (transcripts, voice memo exports)
    if files:
        for f in files:
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
    begin = datetime.fromisoformat(m["begin"])
    end = datetime.fromisoformat(m["end"])
    nl = chr(10)
    names = ", ".join(a["name"] for a in m["attendees"][:12]) + (f" and {len(m['attendees']) - 12} more" if len(m["attendees"]) > 12 else "")
    where = "Online (a Google Meet link will be added)" if meetings.is_virtual(m["where"]) else m["where"]
    repeat = {"weekly": "every week", "fortnightly": "every two weeks", "monthly": "every month"}.get(m.get("repeat") or "", "")
    lines = [f"*{m['title']}*", f"🗓 {meetings.format_when(begin, end)}" + (f" · repeats {repeat}" if repeat else ""),
             f"📍 {where}", f"👥 {len(m['attendees'])} invited: {names}"]
    if m.get("missing"):
        lines.append("⚠️ Not invited (no match or no email on file): " + ", ".join(m["missing"]))
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
        finish("⚠️ The studio calendar isn't connected, so I couldn't create the meeting.")
        return
    try:
        begin, end = datetime.fromisoformat(m["begin"]), datetime.fromisoformat(m["end"])
        description = f"Requested by {m['requester']} through VentureOS."
        event = gcal.create_event(studio["refresh_token"], meetings.build_event_body(
            m["title"], begin, end, m["where"], m["attendees"], description, m.get("repeat")))
        memory.delete_meeting(row["id"])
        link = event.get("htmlLink")
        meet = event.get("hangoutLink")
        finish(f"✅ *{m['title']}* is on the calendar for {meetings.format_when(begin, end)}. Invitations went to "
               f"{len(m['attendees'])} people." + (f" <{meet}|Google Meet link>" if meet else f" 📍 {m['where']}")
               + (f" · <{link}|Open in Google Calendar>" if link else ""))
    except Exception as e:
        print(f"[Meeting Create Error] {e}")
        finish("⚠️ Google wouldn't create that meeting. The studio calendar connection may need renewing; a mentor can reconnect it.")


@app.action("cancel_meeting")
def handle_cancel_meeting(ack, body, client):
    ack()
    memory.delete_meeting(body["actions"][0]["value"])
    client.chat_update(channel=body["channel"]["id"], ts=body["message"]["ts"], text="Meeting cancelled.",
                       blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": "Meeting cancelled. Nothing was sent."}}])


def studio_connect_blocks(slack_id: str) -> list:
    """Mentor Home: one-time connect of the shared studio calendar."""
    url = studio_link(slack_id)
    if not url or studio_connected():
        return []
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


# Initialize scheduler if available (all times Singapore time)
DAILY_CHECKIN = os.environ.get("DAILY_CHECKIN", "on").lower() != "off"
DAILY_CHECKIN_HOUR = int(os.environ.get("DAILY_CHECKIN_HOUR", "17"))


def run_daily_prompts():
    if supabase and SLACK_BOT_TOKEN:
        print(f"[Daily] prompts sent: {len(send_daily_prompts(app.client, supabase, memory))}")


def run_daily_nudges():
    if supabase and SLACK_BOT_TOKEN:
        print(f"[Daily] nudges sent: {len(send_nudges(app.client, supabase, memory))}")


if BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="Asia/Singapore")
    scheduler.add_job(audit_deadlines_and_blockers, "cron", hour=9, minute=0)
    scheduler.add_job(poll_new_connections, "interval", seconds=10, max_instances=1)
    scheduler.add_job(refresh_changed_homes, "interval", seconds=15, max_instances=1)
    scheduler.add_job(beat, "interval", seconds=30, max_instances=1)
    scheduler.add_job(process_google_pending, "interval", seconds=10, max_instances=1)
    scheduler.add_job(sync_all_calendars, "interval", minutes=60, max_instances=1)
    scheduler.add_job(link_org_claims, "interval", seconds=60, max_instances=1)
    if DAILY_CHECKIN:
        scheduler.add_job(run_daily_prompts, "cron", day_of_week="mon-fri", hour=DAILY_CHECKIN_HOUR, minute=0)
        scheduler.add_job(run_daily_nudges, "cron", day_of_week="mon-fri", hour=9, minute=30)
    scheduler.start()


# --- CLI SIMULATOR / ENTRY POINT ---

if __name__ == "__main__":
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
        _socket_handler = SocketModeHandler(app, SLACK_APP_TOKEN)
        _socket_handler.start()
    else:
        print(
            "SLACK_BOT_TOKEN or SLACK_APP_TOKEN not provided in .env.\n"
            "Run with 'python slack_bot.py --simulate' to test extraction and card generation in dry-run mode."
        )
