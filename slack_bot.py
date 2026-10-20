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
from timeparse import parse_ts

# Under a test runner the real .env is never loaded: tests must not reach the live database, Slack or the AI.
# Launched as a program (the bot, or a dry run) it never counts as a test, whatever a library imported.
UNDER_TEST = __name__ != "__main__" and ("unittest" in sys.modules or "pytest" in sys.modules)
try:
    from dotenv import load_dotenv
    if UNDER_TEST:
        load_dotenv = None
    else:
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
    if not UNDER_TEST and "load_dotenv" in globals() and callable(load_dotenv):
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

import announce
import digest
import transcribe
import github_app
import syllabus
import syllabus_import
import custom_schedule
import google_calendar
import meetings
import time
import voice_compare
import milestone_notify
import studio_events
import mentor_calendars
import progress_estimator
import integrations
from profile_rules import match_person, looks_like_email, norm_name
import daily_checkin
from daily_checkin import send_daily_prompts, send_nudges
from bot_agent import Agent
from bot_memory import Memory
from channel_memory import ChannelMemory, NEEDED_SCOPES
import dev_controls
import dev_home
import cohorts
import founder_nudges
import routines

# Console output is also kept in bot_logs for the dashboard's Developer page.
log_tee = dev_controls.install_log_tee() if "--simulate" not in sys.argv else None
# Persistent memory + conversational agent (needs both an LLM and the database)
memory = Memory(supabase)
routine_store = routines.RoutineStore(supabase)  # standing routines mentors set up in chat
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
    except Exception as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status != 404:  # a blip: keep what we have
            print(f"[GitHub Refresh Warning] {e}")
            return row
        repos, account = [], row.get("account")  # the app was uninstalled: nothing is shared any more
    try:
        patch = {"repos": repos, "account": account}
        kept = [r for r in (row.get("selected_repos") or []) if r in repos]  # a repo that was renamed or removed can't stay chosen
        if kept != list(row.get("selected_repos") or []):
            patch["selected_repos"] = kept or None
        supabase.table("integrations").update(patch).eq("id", row["id"]).execute()
        return {**row, **patch}
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


def studio_events_fn(days: int, strict: bool = False):
    """Upcoming events on the studio calendar, or None when it isn't connected. On a Google error: [] (None when strict)."""
    studio = studio_row()
    if not (gcal and studio):
        return None
    now = datetime.now(timezone.utc)
    try:
        return gcal.events(studio["refresh_token"], now, now + timedelta(days=days), only_ours=True)
    except Exception as e:
        print(f"[Studio Events Warning] {e}")
        return None if strict else []


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
                studio_link=lambda sid: studio_link(sid) if is_developer(sid) else None,  # dev-only
                studio_connected=studio_connected, studio_events=studio_events_fn,
                settings=settings, channel_context=channels.context_for,
                awareness=lambda ident: awareness_text(ident), routines=routine_store,
                repos_changed=lambda row, slack_id: (backfill_soon(row, slack_id), publish_home(slack_id, app.client)))
         if (ai_client and supabase) else None)

# Initialize Slack Bolt App
app = None
if App:
    if UNDER_TEST:  # no call to Slack's auth.test from a test run
        app = App(token="xoxb-placeholder", token_verification_enabled=False)
    else:
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

def startup_cohort(startup_id: str | None) -> dict | None:
    """{id, name, start, ...} of the startup's cohort (cohorts.py), or None."""
    if not (startup_id and supabase):
        return None
    return cohorts.for_startup(cohorts.load(supabase), startup_id)


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
                today_sgt = datetime.now(timezone(timedelta(hours=8))).date()
                cohort = startup_cohort(startup.get("id"))
                if cohort:  # each cohort runs the syllabus from its own start Monday (MVP#2 is two weeks behind MVP#1)
                    active_del = syllabus.current_deliverable(today_sgt, cohort["start"]) or active_del
                weeks = custom_schedule.fetch(supabase, startup.get("id")) if startup.get("id") else []
                if weeks:  # a participant with an uploaded syllabus follows their own weeks
                    active_del = custom_schedule.deliverable(weeks, today_sgt, active_del) or active_del
                return {
                    "schedule": custom_schedule.progress(weeks, today_sgt) if weeks else None,
                    "founder_id": founder.get("id"),
                    "name": founder.get("name"),
                    "startup_id": startup.get("id"),
                    "startup_name": startup.get("name"),
                    "stream": startup.get("stream", "General"),
                    "lead": startup.get("lead", "Studio Lead"),
                    "deliverable": active_del,
                    "cohort": {"id": cohort["id"], "name": cohort["name"], "start": cohort["start"]} if cohort else None,
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

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "📝 Your check-in", "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"Here's what I'll save for *{context['startup_name']}*. Look right?"}},
        *checkin_summary_blocks(payload_to_store, deliverable),
        {"type": "actions", "block_id": "confirmation_actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "✅ Save check-in", "emoji": True}, "style": "primary",
             "action_id": "confirm_checkin", "value": json.dumps(payload_to_store, ensure_ascii=False)},
            {"type": "button", "text": {"type": "plain_text", "text": "✏️ Edit", "emoji": True},
             "action_id": "edit_checkin", "value": json.dumps(payload_to_store, ensure_ascii=False)},
        ]},
        {"type": "context", "elements": [{"type": "mrkdwn", "text":
            "Nothing is saved until you press *Save*. Saved check-ins are what your mentors see on the program dashboard."}]},
    ]
    return blocks


def _has_blocker(blocker) -> bool:
    return bool(blocker) and str(blocker).strip().lower() not in ("none", "no", "n/a", "-", "")


def checkin_summary_blocks(value: dict, deliverable: dict | None = None) -> list:
    """The founder's words first, then status, blocker and what it counts toward. Shared by the preview and the saved card."""
    nl = chr(10)
    status = value.get("status", "In progress")
    progress = value.get("progress")
    status_text = f"{STATUS_EMOJI.get(status, '🟡')} {status}"
    if isinstance(progress, int) and status not in ("Completed",):
        status_text += f" · about {progress}% of this week's deliverable"
    fields = [{"type": "mrkdwn", "text": f"*Status*{nl}{status_text}"},
              {"type": "mrkdwn", "text": f"*Blocker*{nl}" + (value["blocker"] if _has_blocker(value.get("blocker")) else "None")}]
    if deliverable and deliverable.get("title"):
        num = re.sub(r"\D", "", str(deliverable.get("week", "")))
        week = f"Week {int(num)}" if num else ""
        fields.append({"type": "mrkdwn", "text": f"*Counts toward*{nl}{(week + ': ') if week else ''}{deliverable['title']}"})
    return [{"type": "section", "text": {"type": "mrkdwn", "text": f"*What you did*{nl}> _{value.get('digest', '')}_"}},
            {"type": "section", "fields": fields}]


def saved_checkin_blocks(value: dict) -> list:
    """What the check-in card turns into once saved (no buttons, so it can't be saved twice)."""
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "✅ *Check-in saved.* Your mentors can see it now."}},
              *checkin_summary_blocks(value)]
    if value.get("status") == "Blocked":
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text":
            "Stuck? Tell me more, or name a mentor and a time (e.g. _\"set up a call with Mo tomorrow at 2 PM\"_) and I'll set it up."}]})
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
                        slack_user_id: str | None = None, footer_button: bool = True) -> list:
    # Pass slack_user_id only where the blocks go to that mentor alone (Home tab, DM): it makes a personal sign-in link.
    return mentor_blocks(summaries, tasks=tasks, title=title, footer=dashboard_button_blocks(slack_user_id=slack_user_id) if footer_button else [],
                         meetings=upcoming_meeting_items(), cohort_list=cohorts.load(supabase) if supabase else [])


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


def where_we_are_text(today=None, start=None) -> str:
    """'Week 3 of 12 · this week's deliverable ... due Fri Oct 16', or '' outside the program."""
    today = today or datetime.now(timezone(timedelta(hours=8))).date()
    cur = syllabus.current(today, start)
    if not cur:
        return ""
    due = syllabus.week_deliverable(cur["week"], start)
    text = f"We're in *week {int(cur['week'].split()[-1])} of 12* ({cur['phase']})."
    if due:
        text += f" This week's deliverable is *{due['deliverable']}*, due {syllabus.fmt_date(due['date'])}."
    return text


def founder_welcome_text(name: str, startup_name: str, intro: str | None = None, start=None) -> str:
    nl = chr(10)
    first = (name or "there").split()[0]
    lines = [intro or f"👋 Welcome, {first}! You're set up with *{startup_name}*.", "",
             "I'm *Venture Buddy*, the program's assistant. There are no forms here. This is how it works:",
             "• *Tell me what you're working on*, in a line or two or as a voice note. I write it up as a short check-in "
             "and show it to you first. Nothing is saved until you press *Save*.",
             "• *On program days at 5 PM* I'll ask how your day went.",
             "• *Your mentors see* the check-ins you save, your milestones and, if you connect it, your GitHub activity.",
             "• *Ask me anything* about the program: what's due, who the mentors are, or to set up a meeting."]
    where = where_we_are_text(start=start)
    if where:
        lines += ["", where]
    lines += ["", "*Try it now:* tell me what you're working on this week.",
              "_Your *Home* tab has your checklist and milestones. Type *help* any time to see everything I can do._"]
    return nl.join(lines)


def founder_welcome_blocks(name: str, startup_name: str, founder_id: str, startup_id: str, intro: str | None = None) -> list:
    cohort = startup_cohort(startup_id)
    text = founder_welcome_text(name, startup_name, intro, start=cohort["start"] if cohort else None)
    return [{"type": "section", "text": {"type": "mrkdwn", "text": text}}, *connect_blocks(founder_id, startup_id)]


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
        client.chat_postMessage(
            channel=slack_user_id,
            text=f"Welcome, {founder['name']}! You're set up with {startup}.",
            blocks=founder_welcome_blocks(founder["name"], startup, founder["id"], founder["startup_id"]),
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
            name, ids = row["name"], (row["id"], row["startup_id"])
            intro = f"✅ Welcome, {name.split()[0]}! I found your invite and linked you to *{st_name}*."
        else:
            if not startup:
                startup = create_startup(new_name or "Untitled startup")
            register_founder(user_id, name, startup["id"], email)
            st_name, ids = startup["name"], (f"founder-{user_id.lower()}", startup["id"])
            intro = (f"✅ You're in, {name.split()[0]}! You're set up with *{st_name}*"
                     + (" (no name yet? just say _\"rename my startup to ...\"_ when you have one)." if not new_name and not picked else "."))
        msg = f"Welcome, {name}! You're set up with {st_name}."
        blocks = founder_welcome_blocks(name, st_name, *ids, intro=intro)
    except Exception as e:
        print(f"[Onboarding Error] {e}")
        msg = "Something went wrong saving your profile. Please ask a mentor."
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": msg}}]
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


def dashboard_button_element(founder_id: str | None = None, slack_user_id: str | None = None) -> dict | None:
    url = integrations.dashboard_url(DASHBOARD_URL, STATE_SECRET, founder_id, slack_user_id)
    if not url:
        return None
    return {"type": "button", "text": {"type": "plain_text", "text": "🟣 Open dashboard", "emoji": True}, "url": url, "action_id": "open_dashboard"}


def dashboard_button_blocks(founder_id: str | None = None, slack_user_id: str | None = None) -> list:
    el = dashboard_button_element(founder_id, slack_user_id)
    return [{"type": "actions", "elements": [el]}] if el else []


def add_to_top_row(blocks: list, element: dict | None) -> list:
    """Puts the Open dashboard button on the top row of a Home tab: beside the Mentor view / Developer switch if there is one."""
    if not element:
        return blocks
    for bl in blocks:
        if bl.get("block_id") == "home_mode":
            if all(e.get("action_id") != "open_dashboard" for e in bl["elements"]):
                bl["elements"].append(element)
            return blocks
    blocks.insert(1, {"type": "actions", "elements": [element]})
    return blocks


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
            "*Optional: connect your GitHub* 🔌" + chr(10) +
            "I'll see your commits and pull requests, so your work shows up without you typing it. "
            "Read-only, and you choose which repositories. Code in a GitHub organisation you don't own? "
            "Use the second button and I'll link it once an owner approves.")}},
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
        own = row.get("founder_id") == founder_id and github_link(founder_id, startup_id)
        if own and len(row.get("repos") or []) < 2:
            head += (chr(10) + "_Want a different repository? Press *Change repositories*, tick it on GitHub, then pick it here "
                     "or tell me which one to track._")
        blocks += integrations.build_repo_selector(row, head, compact=True)
        if own:
            blocks.append({"type": "actions", "elements": [{"type": "button", "text": {"type": "plain_text", "text": "Change repositories"},
                                                          "url": github_link(founder_id, startup_id), "action_id": "connect_github_home"}]})
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


def _goal_suffix(g: dict) -> str:
    pct, est = progress_estimator.goal_value(g)
    if g.get("done") or not pct:
        return ""
    return f" · _~{pct}% estimated_" if est else f" · {pct}%"


friendly_date = syllabus.friendly_date


def _milestone_lines(items: list) -> list:
    lines = []
    for m in items[:4]:
        goals = m.get("goals") or []
        done = sum(1 for g in goals if g.get("done"))
        due = f" · due {friendly_date(m['due_date'])}" if m.get("due_date") else ""
        pct, est = progress_estimator.milestone_value(goals, m)
        overall = f" · {'~' if est else ''}{pct}%" + (" _estimated_" if est and not goals else "") if pct else ""
        count = f"{done}/{len(goals)} goals" if goals else "no goals yet"
        lines.append(f"🎯 *{m['title']}*{due} · {count}{overall}")
        lines += [("      ✅ " if g.get("done") else "      ⬜ ") + g["title"] + _goal_suffix(g) for g in goals[:6]]
    return lines


HOW_TO = {
    "founder": [
        ("📝 Check in: just tell me what you did", [
            "_\"Finished 3 customer interviews, but I'm stuck on pricing\"_, or send a voice note",
            "I write it up as a short check-in and show it to you. Press *Save*, or *Edit* to change the wording, status or blocker",
            "Nothing is saved until you press Save. Saved check-ins are what your mentors see"]),
        ("❓ Ask me anything", [
            "_\"What's due this week?\"_  ·  _\"What does the program look like?\"_  ·  _\"Who are the mentors?\"_",
            "_\"Who sees my updates?\"_  ·  _\"What did I report last time?\"_  ·  _\"What's on my calendar tomorrow?\"_",
            "If your mentors gave you a *custom schedule*, \"this week\", your daily prompts and your Home tab all follow it instead of the standard 12 weeks"]),
        ("🎯 Milestones & to-dos", [
            "_\"Set a milestone: 10 customer interviews by Oct 30. Goals: draft script, book 10 calls\"_",
            "_\"I finished the script\"_ (I tick the goal off)  ·  _\"Remind me to send the deck on Friday\"_",
            "Milestones set by mentors: you can tick their goals off; ask a mentor to change them",
            "A custom schedule shows up as one milestone per week. If you add your own milestone that covers one of its items, yours replaces that item"]),
        ("🙋 Stuck? Get a mentor", [
            "Tell me what's blocking you; mentors see blockers on their side",
            "_\"Set up a call with Mo tomorrow at 2 PM, virtually\"_ (name the people; I show a card before inviting anyone)",
            "_\"Move our Thursday meeting to 4 PM\"_  ·  _\"Cancel it\"_ (meetings you set up)"]),
        ("🔌 Connect your work (optional)", [
            "_\"Connect my GitHub\"_ so your commits and pull requests count without typing them",
            "_\"Connect my Google Calendar\"_ so customer meetings count (only counts are stored)",
            "_\"Rename my startup to Acme\"_"]),
        ("🤖 What I do on my own", [
            "5:00 PM on program days: I ask how your day went. No reply? One reminder the next morning",
            "If your last check-in says you're blocked, I follow up once after two days",
            "A reminder an hour before meetings on the studio calendar"]),
    ],
    "mentor": [
        ("🔎 Ask me about the cohort", [
            "_\"How is Auvira doing?\"_  ·  _\"What is Takshma working on?\"_",
            "_\"Who's blocked?\"_  ·  _\"Who hasn't checked in?\"_  ·  _\"What's due tomorrow?\"_  ·  _pulse_"]),
        ("📌 Notes, tasks & milestones", [
            "_\"Note on SharedOut: needs a technical review\"_ (private to mentors)",
            "_\"Add a task for Auvira: send the deck by Friday\"_  ·  _\"Mark the deck task done\"_",
            "_\"Set a milestone for Auvira: Landing page live by Oct 20. Goals: copy approved, page published\"_ "
            "(add _\"by Arthur\"_ to credit another mentor; founders can only tick its goals)",
            "_\"Assign Auvira to the GTM stream\"_  ·  _\"Rename SharedOut to Acme\"_ (I show a card first)"]),
        ("📄 Custom syllabus for a participant", [
            "*1.* Attach the syllabus PDF in a DM to me. The file name or your message should say _syllabus_ or _curriculum_",
            "*2.* I read it, work out whose it is (or ask you to pick the startup) and show a preview of what I'd add",
            "*3.* Press *Add N milestones*: one per week, due on the week's last day, with the weekly deliverables as goals",
            "*4.* From then on that person's Home tab, daily prompts and my answers follow their schedule (pause weeks are skipped)",
            "Nothing already set is overwritten: if they already have a milestone that covers a syllabus item, theirs is kept and the item is left out. "
            "A milestone you add later replaces the syllabus item it overlaps",
            "Add _\"replace\"_ to your message to refresh an earlier import (only untouched syllabus weeks are removed, never milestones people set)"]),
        ("🗓 Meetings", [
            "_\"Set up a meet with everyone at 3 PM on Thursday at 111 Somerset\"_ or _\"...virtually\"_ (I show a card first)",
            "_\"Set up a fortnightly sprint with Takshma and Matthew, Thursdays at 3 PM\"_",
            "_\"Move Thursday's sprint to 4 PM\"_  ·  _\"Cancel the sprint\"_  ·  _\"What meetings are coming up?\"_"]),
        ("📣 Announcements", [
            "_\"Tell everyone office hours moved to 4 PM\"_  ·  _\"Tell the founders to send their pitch decks by Friday\"_  ·  _\"Tell Auvira the sprint is face to face\"_ (I show who gets it first)"]),
        ("🤖 Automatic", [
            "Monday 9:00 AM digest, and a 9:15 AM nudge when a startup is blocked, quiet, or checking in without code activity",
            "Founders: a 5:00 PM daily prompt, a morning reminder, and one follow-up when they stay blocked",
            "Reminders an hour before meetings"]),
    ],
}


def how_to_blocks(role: str, compact: bool = False) -> list:
    """A short, copy-able 'how to use Venture Buddy' section, different for founders and mentors. `compact` is the
    one-line reminder for people who already know their way around."""
    nl = chr(10)
    if compact:
        return [{"type": "divider"}, {"type": "context", "elements": [{"type": "mrkdwn", "text":
                "💡 Need a reminder of what I can do? Type *help* in the *Messages* tab."}]}]
    blocks = [{"type": "divider"}, {"type": "header", "text": {"type": "plain_text", "text": "How to use Venture Buddy"}},
              {"type": "context", "elements": [{"type": "mrkdwn", "text": "Message me in the *Messages* tab, or @mention me in a channel. "
                                                "Write the way you'd talk; these are just examples. Type *help* any time to see this again."}]}]
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
    lines = [f"• {t['title']}" + (f" (due {friendly_date(t['due_date'])})" if t.get("due_date") else "") for t in tasks[:8]]
    return [{"type": "section", "text": {"type": "mrkdwn", "text": "*Follow-ups*" + nl + nl.join(lines)}}]


def getting_started_blocks(founder_id: str, latest: dict | None, milestones: list, conns: list, gcal_rows: list,
                           github_ready: bool = True) -> list:
    """A short checklist at the top of a new founder's Home tab. Disappears once the steps that matter are done."""
    mine = [r for r in conns if r.get("founder_id") == founder_id]
    steps = [("Set up your profile", True, ""),
             ("Send your first update", bool(latest), "message me what you're working on, a line or two is enough")]
    if github_ready:
        steps.append(("Connect GitHub and pick your repository", any(integrations.monitored_repos(r) for r in mine),
                      "buttons further down" if not mine else "pick the repository further down"))
    steps.append(("Set your first milestone", bool(milestones),
                  "e.g. _\"Set a milestone: 10 customer interviews by Oct 30\"_"))
    done = sum(1 for _, ok, _ in steps if ok)
    if done == len(steps):
        return []
    nl = chr(10)
    lines = [("✅ ~" + t + "~") if ok else (f"⬜ *{t}*" + (f" · {how}" if how else "")) for t, ok, how in steps]
    if not any(r.get("founder_id") == founder_id for r in gcal_rows):
        lines.append("➕ _Optional:_ share your Google Calendar so customer meetings count too")
    return [{"type": "section", "text": {"type": "mrkdwn", "text": f"*Getting started* · {done} of {len(steps)} done{nl}" + nl.join(lines)}},
            {"type": "divider"}]


def setup_checklist_blocks(context: dict, latest, milestones: list, conns: list, gcal_rows: list) -> list:
    """'Get set up' progress for a founder, shown until every step is done."""
    me = context["founder_id"]
    steps = [
        (True, "Profile", ""),
        (bool(latest), "Send your first check-in", "message me what you worked on; a line or a voice note is fine"),
        (any(c.get("founder_id") == me and integrations.monitored_repos(c) for c in conns), "Connect GitHub and choose your repo", "see *GitHub* below"),
        (any(g.get("founder_id") == me for g in gcal_rows), "Connect Google Calendar", "see *Google Calendar* below"),
        (any(m.get("created_by_role") != "mentor" for m in milestones), "Set your first milestone", "for example, tell me: Set a milestone: 10 customer interviews by Oct 23"),
    ]
    done = sum(1 for ok, _, _ in steps if ok)
    if done == len(steps):
        return []
    nl = chr(10)
    lines = [("✅ " if ok else "⬜ ") + label + (f": {hint}" if hint and not ok else "") for ok, label, hint in steps]
    return [{"type": "section", "text": {"type": "mrkdwn", "text": f"*Get set up* ({done} of {len(steps)} done){nl}" + nl.join(lines)}}]


def build_home_view(context: dict | None, latest: dict | None, tasks: list | None = None, milestones: list | None = None, conns: list | None = None, gcal_rows: list | None = None,
                    meeting_lines: list | None = None) -> dict:
    """Founder's personal sprint radar. context=None means the user isn't on the roster yet."""
    if context is None:
        return {"type": "home", "blocks": [{"type": "header", "text": {"type": "plain_text", "text": "Your sprint radar"}}] + build_onboarding_card()}
    nl = chr(10)
    blocks = [{"type": "header", "text": {"type": "plain_text", "text": f"Your sprint radar – {context['startup_name']}"[:150]}}]

    today = datetime.now(timezone(timedelta(hours=8))).date()
    cur = syllabus.current(today, (context.get("cohort") or {}).get("start"))
    bits = []
    mine = context.get("schedule")
    if mine:
        bits.append(f"Week {mine['week']} of {mine['total']} · {mine['phase']}" + (" · pause week" if mine["paused"] else "") + " · your custom schedule")
    elif cur:
        bits.append(f"Week {int(cur['week'].split()[-1])} of 12 · {cur['phase']}")
    if context.get("stream") not in (None, "", "Unassigned", "General"):
        bits.append(f"{context['stream']} stream")
    if bits:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": " · ".join(bits)}]})
    blocks += getting_started_blocks(context["founder_id"], latest, milestones or [], conns or [], gcal_rows or [],
                                     github_ready=bool(github_link(context["founder_id"], context["startup_id"])))

    d = context["deliverable"]
    due_text = friendly_date(d.get("due_date", ""))
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
    # After their first week (and once they've checked in) founders know the basics: keep the Home tab short.
    week_no = mine["week"] if mine else (int(cur["week"].split()[-1]) if cur else 1)
    blocks += how_to_blocks("founder", compact=bool(latest) and week_no >= 2)
    return {"type": "home", "blocks": add_to_top_row(blocks, dashboard_button_element(context["founder_id"]))}


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
            blocks = (build_mentor_blocks(safe_snapshot(), title="Mentor view", tasks=mine, slack_user_id=slack_user_id,
                                          footer_button=False)
                      + studio_connect_blocks(slack_user_id) + my_calendar_blocks(slack_user_id) + how_to_blocks("mentor"))
            if developer:
                blocks.insert(1, dev_home.mode_switch("mentor"))
            blocks = add_to_top_row(blocks, dashboard_button_element(slack_user_id=slack_user_id))
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
        client.views_publish(user_id=slack_user_id, view=build_home_view(context, latest, memory.founder_tasks(context["startup_id"]) if context else [], memory.milestones(context["startup_id"]) if context else [], integrations.github_connections(supabase, context["startup_id"]) if context else [],
                                               integrations.google_connections(supabase, context["startup_id"]) if context else [],
                                               meeting_lines=founder_meeting_lines(slack_user_id) if context else []))
    except Exception as e:
        print(f"[Home Tab Error] {e}")


@app.event("app_home_opened")
def handle_app_home_opened(event, client):
    if event.get("tab", "home") == "home":
        publish_home(event["user"], client)


# --- SLACK HANDLERS ---

# Only a bare greeting: Bolt runs just the first matching listener, so "Hired a designer" or
# "Help, stuck on pricing" must fall through to the agent instead of getting the welcome text.
GREETING_RE = re.compile(r"^\s*(help|onboard|hi|hii+|hello|hey|heya|yo|start|get started)( there)?\s*[!.?👋]*\s*$", re.IGNORECASE)


def is_direct_message(message) -> bool:
    """People talk to each other in channels. Only a DM with the bot (or an @mention, handled elsewhere) is addressed to it."""
    return message.get("channel_type") == "im"


def greeting_reply(role: str | None, name: str = "", text: str = "") -> tuple:
    """(text, blocks) for a bare greeting or 'help'. 'help' always shows the real how-to; a greeting gets one next step."""
    if role and text.strip().lower().startswith("help"):
        return "How to use Venture Buddy", how_to_blocks(role)[1:]  # no leading divider in a message
    if role == "mentor":
        return "Cohort pulse", build_mentor_blocks(safe_snapshot())
    if role == "founder":
        first = (name or "there").split()[0]
        msg = (f"Hey {first} 👋 What are you working on? Tell me in a line or two and I'll write it up as a check-in for you to look over."
               + chr(10) + "_Type *help* to see everything I can do._")
    else:
        msg = ("Hi! 👋 I'm *Venture Buddy*, the program's assistant. Founders tell me what they're working on and I keep "
               "the mentors up to date, so there are no forms to fill in. First, let's get you set up.")
    return msg, [{"type": "section", "text": {"type": "mrkdwn", "text": msg}}]


@app.message(GREETING_RE, matchers=[is_direct_message])
def handle_greeting(message, say):
    user_id = message.get("user")
    role = get_role(user_id) if user_id else None
    name = (resolve_founder_context(user_id) or {}).get("name") or "" if role == "founder" else ""
    text, blocks = greeting_reply(role, name, message.get("text", ""))
    say(text=text, blocks=blocks)
    if user_id and role is None:
        onboard_member(user_id)


@app.event("app_mention")
def handle_app_mention(event, say):
    text = event.get("text", "")
    user_id = event.get("user")
    thread = event.get("thread_ts") or event.get("ts")
    process_inbound_message(user_id, text, event.get("files", []),
                            lambda *a, **k: say(*a, thread_ts=thread, **k) if event.get("channel_type") != "im" else say(*a, **k))


@app.message(re.compile(r".+"))
def handle_direct_or_channel_message(message, say):
    # Only process if direct message (channel type 'im') or explicitly in checkin context
    channel_type = message.get("channel_type")
    if channel_type != "im":
        channels.ingest(message)  # remembered for 7 days only if the channel is switched on in the Developer page
    if channel_type != "im":
        return  # silent in channels: people talk to each other there. I only reply to an @mention (handled separately)

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
             "action_id": "confirm_rename", "value": json.dumps(proposal, ensure_ascii=False)},
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


# Side-by-side trial of Gemini's dedicated speech model (see voice_compare.py). VOICE_COMPARE_MODEL=off stops it.
VOICE_COMPARE_MODEL = "" if os.environ.get("VOICE_COMPARE_MODEL", "").lower() == "off" else (
    os.environ.get("VOICE_COMPARE_MODEL") or ("gemini-3.5-transcribe" if GEMINI_API_KEY else ""))


def transcribe_voice(audio_files: list, say) -> str:
    """Transcribes Slack voice notes with Gemini and replies with what was heard so mistakes can be spotted. '' on failure."""
    if not (GEMINI_API_KEY and SLACK_BOT_TOKEN):
        say("I can't transcribe voice notes yet (the transcription key isn't set up). Type it out for now?")
        return ""
    parts, hints = [], voice_hints()
    for f in audio_files[:transcribe.MAX_FILES]:
        try:
            data = transcribe.download(f, SLACK_BOT_TOKEN)
            mime, started = transcribe.gemini_mime(f), time.monotonic()
            parts.append(transcribe.transcribe_audio(data, mime, GEMINI_API_KEY, AI_MODEL, hints=hints))
            if VOICE_COMPARE_MODEL and supabase:  # trial only: founders never see the candidate's text
                voice_compare.compare_in_background(
                    supabase, data, mime, parts[-1], int((time.monotonic() - started) * 1000),
                    lambda d, m: transcribe.transcribe_dedicated(d, m, GEMINI_API_KEY, VOICE_COMPARE_MODEL, vocab=hints),
                    VOICE_COMPARE_MODEL)
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
    # A mentor attaching a participant's syllabus: turn it into milestones (after a preview card)
    if role == "mentor":
        docs = [f for f in files or [] if syllabus_import.looks_like_syllabus(f, text)]
        if docs:
            handle_syllabus_upload(user_id, docs[0], text, say)
            return
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
            if result.get("announce_now"):
                say(send_announcement(app.client, result["announce_now"]))
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
        return False
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
        return True
    except Exception as e:
        print(f"[Supabase Commit Error]: {e}")
        return False


def estimate_after_checkin(action_value: dict):
    """In the background: credit the goals this check-in reports progress on (same rules as GitHub estimates)."""
    if ai_client and supabase and action_value.get("startup_id"):
        threading.Thread(target=progress_estimator.from_checkin, daemon=True,
                         args=(supabase, ai_client, AI_MODEL, action_value["startup_id"], action_value.get("digest", "")),
                         kwargs={"notify": notify_founders}).start()


CHECKIN_FAILED = "⚠️ I couldn't save that check-in just now, so nothing was recorded. Please try again in a minute."


CHECKIN_STATUSES = ["In progress", "On Track", "Blocked", "Completed"]


@app.view("modal_edit_checkin")
def handle_edit_checkin_submit(ack, body, client, view):
    """Founder saved the Edit modal: commit the edited values and turn the original card into the saved state."""
    ack()
    meta = json.loads(view["private_metadata"])
    action_value, where = meta.get("value", meta), meta.get("card")
    values = view["state"]["values"]
    action_value["digest"] = values["digest_input"]["digest_text"]["value"] or action_value["digest"]
    action_value["blocker"] = (values["blocker_input"]["blocker_text"].get("value") or "").strip() or "None"
    picked = (values.get("status_input", {}).get("status_select", {}).get("selected_option") or {}).get("value")
    if picked in CHECKIN_STATUSES:
        action_value["status"] = picked
    user_id = body["user"]["id"]
    if not commit_checkin(action_value, body["user"]["name"]):
        client.chat_postMessage(channel=user_id, text=CHECKIN_FAILED)
        return
    estimate_after_checkin(action_value)
    blocks = saved_checkin_blocks(action_value)
    try:
        client.chat_update(channel=where["channel"], ts=where["ts"], text="Check-in saved", blocks=blocks)
    except Exception:  # card location unknown (older card): post the saved state instead
        client.chat_postMessage(channel=user_id, text="Check-in saved", blocks=blocks)
    publish_home(user_id, client)


@app.action("confirm_checkin")
def handle_confirm_checkin(ack, body, client):
    """Founder pressed Save: write the check-in and lock the card so it can't be saved twice."""
    ack()
    action_value = json.loads(body["actions"][0]["value"])
    user_id = body["user"]["id"]
    if not commit_checkin(action_value, body["user"]["name"]):
        client.chat_postMessage(channel=user_id, text=CHECKIN_FAILED)
        return
    estimate_after_checkin(action_value)
    client.chat_update(channel=body["channel"]["id"], ts=body["message"]["ts"], text="Check-in saved",
                       blocks=saved_checkin_blocks(action_value))
    publish_home(user_id, client)


@app.action("edit_checkin")
def handle_edit_checkin(ack, body, client):
    """Founder pressed Edit: change the summary, status or blocker before saving."""
    ack()
    action_value = json.loads(body["actions"][0]["value"])
    meta = {"value": action_value, "card": {"channel": body["channel"]["id"], "ts": body["message"]["ts"]}}
    while len(json.dumps(meta, ensure_ascii=False)) > 3000 and action_value.get("raw_transcript"):  # Slack's private_metadata limit
        action_value["raw_transcript"] = action_value["raw_transcript"][:len(action_value["raw_transcript"]) // 2]
    status = action_value.get("status") if action_value.get("status") in CHECKIN_STATUSES else "In progress"
    option = lambda v: {"text": {"type": "plain_text", "text": f"{STATUS_EMOJI.get(v, '')} {v}".strip()}, "value": v}
    blocker = action_value.get("blocker", "")
    client.views_open(trigger_id=body["trigger_id"], view={
        "type": "modal", "callback_id": "modal_edit_checkin", "private_metadata": json.dumps(meta, ensure_ascii=False),
        "title": {"type": "plain_text", "text": "Edit check-in"},
        "submit": {"type": "plain_text", "text": "Save check-in"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {"type": "input", "block_id": "digest_input", "label": {"type": "plain_text", "text": "What you did"},
             "element": {"type": "plain_text_input", "action_id": "digest_text", "multiline": True,
                         "initial_value": action_value.get("digest", "")}},
            {"type": "input", "block_id": "status_input", "label": {"type": "plain_text", "text": "Status"},
             "element": {"type": "static_select", "action_id": "status_select",
                         "options": [option(v) for v in CHECKIN_STATUSES], "initial_option": option(status)}},
            {"type": "input", "block_id": "blocker_input", "optional": True,
             "label": {"type": "plain_text", "text": "Anything blocking you?"},
             "hint": {"type": "plain_text", "text": "Leave empty if nothing is."},
             "element": {"type": "plain_text_input", "action_id": "blocker_text",
                         **({"initial_value": blocker} if _has_blocker(blocker) else {})}},
        ],
    })


# --- BACKGROUND PROACTIVE CHASER & NUDGE WORKER ---

def audit_deadlines_and_blockers(dry_run: bool = False) -> list:
    """
    Daily 09:00 on program days: a founder whose LATEST check-in is still Blocked after 48h gets one follow-up
    per blocker (never repeated, never for a blocker a newer check-in replaced). The message goes into their
    conversation history so a reply ("sorted now", "yes, set up a call") is understood.
    """
    if not (supabase and syllabus.has_session(_today_sgt())):
        return []
    try:
        subs = (supabase.table("submissions").select("id,founder_id,status,blocker,created_at")
                .eq("confirmed", True).order("created_at", desc=True).limit(500).execute().data or [])
        founders = {f["id"]: f for f in daily_checkin.linked_founders(supabase)}
    except Exception as e:
        print(f"[Audit Error]: {e}")
        return []
    sent = []
    for item in daily_checkin.stale_blockers(subs, datetime.now(timezone.utc)):
        founder, key = founders.get(item["founder_id"]), f"blocker-dm:{item['id']}"
        if not founder or alert_seen(key):
            continue
        text = daily_checkin.build_blocker_followup(daily_checkin._first_name(founder["name"]), item.get("blocker"))
        sent.append((founder["slack_user_id"], text))
        if dry_run:
            continue
        try:
            app.client.chat_postMessage(channel=founder["slack_user_id"], text=text)
            memory.log(founder["slack_user_id"], "assistant", text)
            alert_mark(key)
        except Exception as e:
            print(f"[Audit Error] {founder['slack_user_id']}: {e}")
    return sent


# --- SCHEDULING MEETINGS ---

def send_announcement(client, m: dict) -> str:
    """DMs an announcement to its recipients and returns the outcome line for the sender."""
    text, sent, failed = announce.format_announcement(m["requester"], m["message"]), [], []
    for person in m["recipients"]:
        try:
            client.chat_postMessage(channel=person["slack"], text=text)
            sent.append(person["name"])
        except Exception as e:
            print(f"[Announcement Error] {person['slack']}: {e}")
            failed.append(person["name"])
    print(f"[Announcement] sent to {len(sent)}, failed {len(failed)}")
    line = (f"✅ Sent to {', '.join(sent)}." if len(sent) <= 5 else f"✅ Announcement sent to {announce.people_word(len(sent))}.") if sent else ""
    if failed:
        line += f" ⚠️ Couldn't reach: {', '.join(failed)}."
    if m.get("unreachable"):
        line += f" ⚠️ Not on Slack yet: {', '.join(m['unreachable'])}."
    if m.get("unknown"):
        line += f" ⚠️ No match for: {', '.join(m['unknown'])}."
    return line.strip() or "⚠️ Nobody could be reached."


def syllabus_plan(m: dict):
    """(existing milestones, plan, ids replaceable) for a pending syllabus, computed fresh from the database."""
    existing = syllabus_import.load_existing(supabase, m["startup_id"])
    gone = [x["id"] for x in syllabus_import.removable(existing)] if m.get("replace") else []
    keep = [x for x in existing if x["id"] not in gone]  # replaced weeks must not block re-adding themselves
    return existing, syllabus_import.plan_import(m["weeks"], keep), gone


def handle_syllabus_upload(user_id: str, f: dict, text: str, say):
    if not (GEMINI_API_KEY and SLACK_BOT_TOKEN and supabase):
        say("I can't read syllabi yet (the AI key or database isn't set up).")
        return
    say(f"📄 Reading *{f.get('name', 'the syllabus')}*… this takes a few seconds.")
    try:
        data = transcribe.download(f, SLACK_BOT_TOKEN)
        spec = syllabus_import.extract(data, f, GEMINI_API_KEY, AI_MODEL, datetime.now(meetings.SGT).date(), transcribe._default_http)
    except ValueError as e:
        say(f"⚠️ {e}. Is it a week-by-week syllabus?")
        return
    except Exception as e:
        print(f"[Syllabus Error] {e}")
        say("⚠️ I couldn't read that file. Try again, or send it as a PDF.")
        return
    founders = supabase.table("founders").select("name,startup_id").execute().data or []
    startups = supabase.table("startups").select("id,name").execute().data or []
    found = syllabus_import.match_startups(spec, text, founders, startups)
    me = build_identity(user_id, "mentor")
    payload = {"kind": "syllabus", "requester_slack": user_id, "requester": me["name"], "participant": spec["participant"],
               "weeks": spec["weeks"], "replace": syllabus_import.wants_replace(text),
               "startup_id": found[0] if len(found) == 1 else None, "candidates": found or [s["id"] for s in startups],
               "startup_names": {s["id"]: s["name"] for s in startups}}
    meeting_id = memory.save_meeting(user_id, payload)
    if not meeting_id:
        say("⚠️ I couldn't prepare that (is the pending_meetings table created?).")
        return
    say(blocks=build_meeting_card({"id": meeting_id, **payload}), text="Confirm syllabus import")


def build_syllabus_card(m: dict) -> list:
    nl = chr(10)
    first, last = m["weeks"][0]["start"], m["weeks"][-1]["end"]
    who = m["participant"] or "this participant"
    if not m.get("startup_id"):
        options = [{"text": {"type": "plain_text", "text": m["startup_names"].get(i, i)[:75]}, "value": f"{m['id']}|{i}"}
                   for i in m["candidates"][:100]]
        return [
            {"type": "section", "text": {"type": "mrkdwn", "text": f"I read *{who}'s* syllabus ({len(m['weeks'])} weeks, {first} to {last}). *Which startup is it for?*"},
             "accessory": {"type": "static_select", "action_id": "syllabus_pick", "placeholder": {"type": "plain_text", "text": "Choose a startup"}, "options": options}},
            {"type": "actions", "elements": [{"type": "button", "text": {"type": "plain_text", "text": "Cancel"}, "action_id": "cancel_meeting", "value": m["id"]}]},
        ]
    existing, plan, gone = syllabus_plan(m)
    goals = sum(len(a["goals"]) for a in plan["add"])
    lines = [f"*Syllabus for {who}* ({m['startup_names'].get(m['startup_id'], m['startup_id'])}) · {len(m['weeks'])} weeks, {first} to {last}"]
    if plan["add"]:
        lines.append(f"➕ I'll add *{len(plan['add'])} milestones* ({goals} goals), one per week, each due on the week's last day.")
    else:
        lines.append("Nothing new to add: everything in this syllabus is already on their milestones.")
    if plan["covered"]:
        shown = [f"• {c['item']} ← _{c['by']}_" for c in plan["covered"][:5]]
        more = f"{nl}…and {len(plan['covered']) - 5} more" if len(plan["covered"]) > 5 else ""
        lines.append(f"🔁 Their own milestones already cover these, so I'll keep theirs and leave these out:{nl}" + nl.join(shown) + more)
    if plan["have"]:
        lines.append(f"✔️ {len(plan['have'])} weeks are already imported.")
    if gone:
        lines.append(f"♻️ First I'll remove {len(gone)} earlier syllabus milestones that have no finished goals.")
    lines.append("Milestones people set themselves are never changed or removed.")
    buttons = ([{"type": "button", "style": "primary", "text": {"type": "plain_text", "text": f"Add {len(plan['add'])} milestones"},
                 "action_id": "confirm_meeting", "value": m["id"]}] if plan["add"] else [])
    buttons.append({"type": "button", "text": {"type": "plain_text", "text": "Cancel" if plan["add"] else "Close"},
                    "action_id": "cancel_meeting", "value": m["id"]})
    return [{"type": "section", "text": {"type": "mrkdwn", "text": nl.join(lines)}}, {"type": "actions", "elements": buttons}]


@app.action("syllabus_pick")
def handle_syllabus_pick(ack, body, client):
    ack()
    meeting_id, startup_id = body["actions"][0]["selected_option"]["value"].split("|", 1)
    row = memory.get_meeting(meeting_id)
    if not row or row["requested_by"] != body["user"]["id"]:
        return
    payload = {**row["payload"], "startup_id": startup_id}
    memory.set_meeting_payload(meeting_id, payload)
    client.chat_update(channel=body["channel"]["id"], ts=body["message"]["ts"], text="Confirm syllabus import",
                       blocks=build_meeting_card({"id": meeting_id, **payload}))


def build_meeting_card(m: dict) -> list:
    nl = chr(10)
    if m.get("kind") == "routine":
        return build_routine_card(m)
    if m.get("kind") == "syllabus":
        return build_syllabus_card(m)
    if m.get("kind") == "announce":
        names = ", ".join(p["name"] for p in m["recipients"][:15]) + (f" and {len(m['recipients']) - 15} more" if len(m["recipients"]) > 15 else "")
        quoted = nl.join("> " + line for line in m["message"].splitlines() if line.strip())
        lines = [f"I'll send this as a direct message to *{announce.people_word(len(m['recipients']))}*: {names}", quoted]
        if m.get("unreachable"):
            lines.append("⚠️ Not on Slack yet, so they won't get it: " + ", ".join(m["unreachable"]))
        if m.get("unknown"):
            lines.append("⚠️ No match for: " + ", ".join(m["unknown"]))
        return [
            {"type": "section", "text": {"type": "mrkdwn", "text": "*Announcement preview*" + nl + nl.join(lines)}},
            {"type": "actions", "elements": [
                {"type": "button", "style": "primary", "text": {"type": "plain_text", "text": f"Send to {announce.people_word(len(m['recipients']))}"},
                 "action_id": "confirm_meeting", "value": m["id"]},
                {"type": "button", "text": {"type": "plain_text", "text": "Don't send"}, "action_id": "cancel_meeting", "value": m["id"]}]},
        ]
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
    begin = parse_ts(m["begin"])
    end = parse_ts(m["end"])
    if m.get("calendar_only"):
        where = "Online" if meetings.is_virtual(m["where"]) else m["where"]
        lines = [f"*{m['title']}*", f"🗓 {meetings.format_when(begin, end)}", f"📍 {where}"]
        return [
            {"type": "section", "text": {"type": "mrkdwn", "text": "I'll add this to the studio calendar. *No invitations or emails will be sent.*" + nl + nl.join(lines)}},
            {"type": "actions", "elements": [
                {"type": "button", "style": "primary", "text": {"type": "plain_text", "text": "Add to calendar"},
                 "action_id": "confirm_meeting", "value": m["id"]},
                {"type": "button", "text": {"type": "plain_text", "text": "Cancel"}, "action_id": "cancel_meeting", "value": m["id"]}]},
        ]
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
    print(f"[Confirm] {user_id} pressed confirm on {body['actions'][0]['value'][:8]}: {'found' if row else 'no pending row'}")
    if not row:
        finish("That meeting request has expired or was already handled.")
        return
    if row["requested_by"] != user_id:
        client.chat_postEphemeral(channel=channel, user=user_id, text="Only the person who asked for this meeting can confirm it.")
        return
    if row["payload"].get("kind") == "announce":
        m = row["payload"]
        if not (get_role(user_id) == "mentor" and m.get("requester_slack") == user_id):
            client.chat_postEphemeral(channel=channel, user=user_id, text="Only the mentor who wrote this announcement can send it.")
            return
        if not memory.claim_meeting(row["id"]):
            print("[Confirm] announcement already claimed by an earlier click")
            return  # a second click on the same card
        finish(send_announcement(client, m))
        return
    if row["payload"].get("kind") == "routine":
        outcome = confirm_routine(row, user_id)
        if outcome:
            finish(outcome)
        else:
            client.chat_postEphemeral(channel=channel, user=user_id, text="Only the mentor who asked for this routine can start it.")
        return
    if row["payload"].get("kind") == "syllabus":
        m = row["payload"]
        if not (get_role(user_id) == "mentor" and m.get("requester_slack") == user_id and m.get("startup_id")):
            client.chat_postEphemeral(channel=channel, user=user_id, text="Only the mentor who uploaded this syllabus can confirm it.")
            return
        if not memory.claim_meeting(row["id"]):
            return  # a second click on the same card
        try:
            _, plan, gone = syllabus_plan(m)
            added = syllabus_import.apply_import(supabase, m["startup_id"], user_id, plan["add"], gone)
            finish(f"✅ Added *{added} milestones* for {m['startup_names'].get(m['startup_id'], 'the startup')} from the syllabus."
                   + (f" Replaced {len(gone)} earlier syllabus milestones." if gone else "") + " Their own milestones were left as they were.")
        except Exception as e:
            print(f"[Syllabus Import Error] {e}")
            finish("⚠️ I couldn't save the syllabus milestones. Please try again.")
        return
    m, studio = row["payload"], studio_row()
    if not (gcal and studio):
        finish("⚠️ The studio calendar isn't connected, so I couldn't do that.")
        return
    if m.get("kind") == "change" and not (get_role(user_id) == "mentor" or m.get("requester_slack") == user_id):
        client.chat_postEphemeral(channel=channel, user=user_id, text="Only a mentor or the person who set this meeting up can change it.")
        return
    if not memory.claim_meeting(row["id"]):
        return  # a second click on the same card
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
        begin, end = parse_ts(m["begin"]), parse_ts(m["end"])
        description = (f"Requested by {m['requester']} through VentureOS. Join with the Google account this invitation was sent to.")
        only = bool(m.get("calendar_only"))
        open_link = gcal.create_open_meet(studio["refresh_token"]) if meetings.is_virtual(m["where"]) and not only else None
        event = gcal.create_event(studio["refresh_token"], meetings.build_event_body(
            m["title"], begin, end, m["where"], m["attendees"], description, m.get("repeat"), m.get("requester_slack"),
            meet_link=open_link, studio_wide=only))
        memory.delete_meeting(row["id"])
        _studio_cache["at"] = 0.0
        link, meet = event.get("htmlLink"), open_link or event.get("hangoutLink")
        note = ""
        if open_link:
            note = " Anyone with the link can join without being admitted."
        elif meet:
            note = (" ⚠️ Guests may need to be admitted by the host: a mentor needs to reconnect the studio calendar once "
                    "to allow open Meet rooms.")
        finish(f"✅ *{m['title']}* is on the studio calendar for {meetings.format_when(begin, end)}. No invitations were sent." if only else
               f"✅ *{m['title']}* is on the calendar for {meetings.format_when(begin, end)}. Invitations went to "
               f"{len(m['attendees'])} people." + (f" <{meet}|Google Meet link>" if meet else f" 📍 {m['where']}")
               + (f" · <{link}|Open in Google Calendar>" if link else "") + note)
    except Exception as e:
        print(f"[Meeting Create Error] {e}")
        finish("⚠️ Google wouldn't do that. The studio calendar connection may need renewing; a mentor can reconnect it.")


@app.action("cancel_meeting")
def handle_cancel_meeting(ack, body, client):
    ack()
    row = memory.get_meeting(body["actions"][0]["value"])
    if row and row["requested_by"] != body["user"]["id"]:
        client.chat_postEphemeral(channel=body["channel"]["id"], user=body["user"]["id"],
                                  text="Only the person who asked for this can cancel it.")
        return
    memory.delete_meeting(body["actions"][0]["value"])
    if row and (row.get("payload") or {}).get("kind") == "syllabus":
        note = "Syllabus import cancelled. Nothing was changed."
    else:
        note = "Meeting cancelled. Nothing was sent."
    client.chat_update(channel=body["channel"]["id"], ts=body["message"]["ts"], text=note,
                       blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": note}}])


def studio_connect_blocks(slack_id: str) -> list:
    """Mentor Home: connect the shared studio calendar once, or reconnect it (e.g. to grant a new permission)."""
    url = studio_link(slack_id)
    if not url:
        return []
    row = studio_row()
    if row:
        section = {"type": "section", "text": {"type": "mrkdwn", "text": "*Meetings* 🗓" + chr(10) + f"Studio calendar: *{row.get('account', 'connected')}*. "
                                                "Ask me to set up, move or cancel a meeting."}}
        # Locked to one account: only the developer can reconnect, and only with that same account.
        if not studio_events.can_reconnect_studio(row, slack_id, is_developer(slack_id)):
            return [section]
        return [
            section,
            {"type": "actions", "elements": [{"type": "button", "text": {"type": "plain_text", "text": "Reconnect studio calendar"},
                                              "url": url, "action_id": "connect_studio"}]},
        ]
    if not studio_events.can_reconnect_studio(None, slack_id, is_developer(slack_id)):
        return [{"type": "section", "text": {"type": "mrkdwn", "text": (
            "*Meetings* 🗓" + chr(10) + "The studio calendar isn't connected yet. The developer sets it up; then you can ask me to "
            "set up, move or cancel meetings.")}}]
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": (
            "*Meetings* 🗓" + chr(10) + "Connect the studio Google Calendar once and I can set up meetings with the cohort when you ask "
            "(\"set up a meet with everyone at 3 PM on Thursday at 111 Somerset\"). You confirm each one before invitations go out.")}},
        {"type": "actions", "elements": [{"type": "button", "style": "primary", "text": {"type": "plain_text", "text": "Connect studio calendar"},
                                          "url": url, "action_id": "connect_studio"}]},
    ]


def my_calendar_blocks(slack_id: str) -> list:
    """Mentor Home: connect your own Google Calendar (read-only) so the bot knows when you're busy. Never the studio one."""
    url = mentor_calendars.connect_url(GOOGLE_CLIENT_ID, GOOGLE_REDIRECT_URI, STATE_SECRET, slack_id) if gcal else None
    if not (url and supabase):
        return []
    row = mentor_calendars.connection(supabase, slack_id)
    if row:
        return [
            {"type": "section", "text": {"type": "mrkdwn", "text": (
                "*Your calendar* 📆" + chr(10) + f"Connected: *{row.get('account') or 'your Google Calendar'}*. I use it to suggest meeting "
                "times and flag clashes, and other mentors see your schedule on the dashboard (private events show as Busy).")}},
            {"type": "actions", "elements": [{"type": "button", "text": {"type": "plain_text", "text": "Disconnect my calendar"},
                                              "action_id": "disconnect_my_calendar", "value": slack_id,
                                              "confirm": {"title": {"type": "plain_text", "text": "Disconnect your calendar?"},
                                                          "text": {"type": "plain_text", "text": "I'll stop reading it and remove your events from the dashboard."},
                                                          "confirm": {"type": "plain_text", "text": "Disconnect"},
                                                          "deny": {"type": "plain_text", "text": "Keep it"}}}]},
        ]
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": (
            "*Your calendar* 📆" + chr(10) + "Connect your own Google Calendar (read-only) so I can find times when the mentors are free "
            "and warn about clashes. Other mentors see your schedule on the dashboard; events you mark private show as Busy. "
            "This is separate from the studio calendar.")}},
        {"type": "actions", "elements": [{"type": "button", "text": {"type": "plain_text", "text": "Connect my calendar"},
                                          "url": url, "action_id": "connect_my_calendar"}]},
    ]


# --- PROGRESS ESTIMATES FROM GITHUB WORK ---

def notify_founders(startup_id: str, blocks: list, text: str):
    """DMs every Slack-linked founder of a startup."""
    for f in supabase.table("founders").select("slack_user_id").eq("startup_id", startup_id).execute().data or []:
        if f.get("slack_user_id"):
            try:
                sent = app.client.chat_postMessage(channel=f["slack_user_id"], text=text, blocks=blocks)
                print(f"[Progress Estimate] card sent to {f['slack_user_id']} ({startup_id}) ts={sent.get('ts')}: {text}")
            except Exception as e:
                print(f"[Progress Estimate Warning] DM {f['slack_user_id']}: {e}")


def run_progress_estimates():
    if ai_client and supabase and SLACK_BOT_TOKEN:
        progress_estimator.run(supabase, ai_client, AI_MODEL, notify=notify_founders)


def _estimate_target(ref: str) -> tuple:
    """A card's button value -> (table, id): "<goal id>" or "m:<milestone id>" for a milestone with no goals."""
    return ("milestones", ref[2:]) if ref.startswith("m:") else ("goals", ref)


def _goal_for(user_id: str, goal_id: str) -> dict | None:
    """The goal (or goal-less milestone), if this person may update it: a founder of its startup, or any mentor."""
    table, item_id = _estimate_target(goal_id)
    if table == "milestones":
        rows = supabase.table("milestones").select("id,title,est_progress,startup_id").eq("id", item_id).execute().data
        startup = rows[0].get("startup_id") if rows else None
    else:
        rows = supabase.table("goals").select("id,title,est_progress,milestone_id,milestones(startup_id)").eq("id", item_id).execute().data
        startup = (rows[0].get("milestones") or {}).get("startup_id") if rows else None
    if not rows:
        return None
    g = rows[0]
    if get_role(user_id) == "mentor":
        return g
    me = supabase.table("founders").select("startup_id").eq("slack_user_id", user_id).execute().data
    return g if me and me[0]["startup_id"] == startup else None


def _settle_goal(body, client, goal_id: str, patch: dict, said: str):
    user_id = body["user"]["id"]
    g = _goal_for(user_id, goal_id)
    if not g:
        client.chat_postMessage(channel=user_id, text="⚠️ I couldn't update that goal (it may have been removed).")
        return
    table, item_id = _estimate_target(goal_id)
    if table == "milestones" and "done" in patch:  # a goal-less milestone is finished as a whole
        patch = {"status": "done", "progress": 100, "updated_at": patch.get("done_at")}
    supabase.table(table).update({**patch, "est_progress": None, "est_reason": None, "est_at": None}).eq("id", item_id).execute()
    if "done" in patch and g.get("milestone_id"):
        memory.sync_milestone(g["milestone_id"])
    try:
        client.chat_update(channel=body["channel"]["id"], ts=body["message"]["ts"], text=said,
                           blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": said.replace("{title}", g["title"])}}])
    except Exception as e:
        print(f"[Progress Estimate Warning] update card: {e}")
    publish_home(user_id, client)


@app.action("confirm_goal_estimate")
def handle_confirm_goal_estimate(ack, body, client):
    ack()
    goal_id = body["actions"][0]["value"]
    table, item_id = _estimate_target(goal_id)
    rows = supabase.table(table).select("est_progress").eq("id", item_id).execute().data
    pct = rows[0].get("est_progress") if rows else None
    if pct is None:  # already confirmed or replaced: a stale or double click must not reset the goal to 0%
        client.chat_postMessage(channel=body["user"]["id"], text="That estimate was already handled.")
        return
    _settle_goal(body, client, goal_id, {"progress": pct}, f"✅ *{{title}}*: {pct}% confirmed.")


@app.action("set_goal_progress")
def handle_set_goal_progress(ack, body, client):
    ack()
    goal_id, pct = body["actions"][0]["selected_option"]["value"].split("|")
    _settle_goal(body, client, goal_id, {"progress": int(pct)}, f"✅ *{{title}}*: set to {int(pct)}%.")


@app.action("mark_goal_done")
def handle_mark_goal_done(ack, body, client):
    ack()
    _settle_goal(body, client, body["actions"][0]["value"],
                 {"done": True, "done_at": datetime.now(timezone.utc).isoformat(), "progress": 100}, "🎉 *{title}*: marked done.")


@app.action("connect_my_calendar")
def handle_connect_my_calendar(ack):
    ack()  # link button


@app.action("disconnect_my_calendar")
def handle_disconnect_my_calendar(ack, body, client):
    ack()
    user_id = body["user"]["id"]
    try:
        mentor_calendars.disconnect(supabase, user_id)
        client.chat_postMessage(channel=user_id, text="✅ Your calendar is disconnected. I've removed your events from the dashboard.")
    except Exception as e:
        print(f"[Mentor Calendar Error] disconnect {user_id}: {e}")
    publish_home(user_id, client)


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
            if item.get("kind") == "mentor":
                sid = item.get("slack_user_id")
                if not (sid and get_role(sid) == "mentor"):
                    continue  # only mentors connect their own calendar this way
                mentor_calendars.save_connection(supabase, sid, got, STATE_SECRET)
                app.client.chat_postMessage(channel=sid, text=(
                    f"✅ *Your calendar is connected* ({got.get('email')}). I'll use it to suggest meeting times and flag clashes, "
                    "and other mentors can see your schedule on the dashboard. Events you mark private in Google show as Busy."))
                threading.Thread(target=lambda: mentor_calendars.sync_all(supabase, gcal), daemon=True).start()
                publish_home(sid, app.client)
                continue
            if item.get("kind") == "studio":
                if not got.get("refresh_token"):
                    raise RuntimeError("Google returned no refresh token")
                refusal = studio_events.studio_account_refusal(studio_row(), got.get("email"))
                if refusal:
                    if item.get("slack_user_id"):
                        app.client.chat_postMessage(channel=item["slack_user_id"], text="🔒 " + refusal)
                    continue
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
    blocks = digest.build_digest_blocks(summaries, today, upcoming_meeting_items(), memory.open_tasks(),
                                        cohort_list=cohorts.load(supabase))
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


MILESTONE_NOTIFY = os.environ.get("MILESTONE_NOTIFY", "on").lower() != "off"


def studio_mail(to: str, subject: str, body: str, from_name: str, reply_to: list):
    """Email from the studio Google account (the one connected for the studio calendar)."""
    row = studio_row()
    if not (gcal and row):
        raise RuntimeError("the studio Google account isn't connected")
    gcal.send_email(row["refresh_token"], to, subject, body, from_name=from_name, from_email=row.get("account") or "",
                    reply_to=reply_to)


def notify_new_milestones():
    """Every minute: DM and email founders about milestones and tasks a mentor just set for their startup."""
    if not (MILESTONE_NOTIFY and supabase and SLACK_BOT_TOKEN):
        return
    sent = milestone_notify.run(supabase, app.client, alert_seen, alert_mark,
                                send_email=studio_mail if gcal and studio_connected() else None, log=memory.log,
                                dashboard_url=DASHBOARD_URL or "")
    if sent:
        print(f"[Milestones] told founders: {sent}")


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
        meet_url = ev.get("hangoutLink") or (ev.get("location") if "meet.google.com" in (ev.get("location") or "") else None)
        where = f"<{meet_url}|Join the Google Meet>" if meet_url else (ev.get("location") or "")
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

def reconcile_github():
    """
    Every few minutes: re-read from GitHub what each connection can see, so a webhook that never arrived (or a renamed or
    removed repo) cannot leave the dashboard out of date. Real changes are then picked up by watch_repo_changes.
    """
    if not (supabase and SLACK_BOT_TOKEN and gh):
        return
    try:
        rows = supabase.table("integrations").select("*").eq("provider", "github").execute().data or []
    except Exception:
        return
    for row in rows:
        refresh_repos(row)


_repo_seen: dict = {}  # integration id -> (granted repos, chosen repos) as last seen; empty until the first pass


def watch_repo_changes():
    """
    A founder changing which repositories the app may see happens on GitHub, and only a webhook updates our copy.
    Notice it here: refresh their Home tab and the mentors', and pull in the recent work from what is now tracked.
    """
    if not (supabase and SLACK_BOT_TOKEN):
        return
    try:
        rows = supabase.table("integrations").select("*").eq("provider", "github").execute().data or []
    except Exception:
        return
    first = not _repo_seen
    for row in rows:
        state = (tuple(sorted(row.get("repos") or [])), tuple(sorted(row.get("selected_repos") or [])))
        before = _repo_seen.get(row["id"])
        keep = None if first else integrations.keep_implicit_choice(before, row)
        if keep:  # they shared more repos: carry on tracking the one they had
            try:
                supabase.table("integrations").update({"selected_repos": keep}).eq("id", row["id"]).execute()
                row = {**row, "selected_repos": keep}
                state = (state[0], tuple(keep))
            except Exception as e:
                print(f"[Repos Changed Warning] {e}")
        _repo_seen[row["id"]] = state
        if first or before is None or before == state:
            continue
        try:
            founder = (supabase.table("founders").select("slack_user_id").eq("id", row["founder_id"]).execute().data or [{}])[0]
            slack_id = founder.get("slack_user_id")
            print(f"[Repos Changed] {row['account']}: {before} -> {state}")
            if integrations.monitored_repos(row):
                # the recent work in the repos now tracked, up to this moment (webhooks only cover what happens from here on)
                backfill_in_background({**row, "created_at": datetime.now(timezone.utc).isoformat()}, slack_id)
            for uid in {u for u in [slack_id] + mentor_slack_ids() if u}:
                publish_home(uid, app.client)
        except Exception as e:
            print(f"[Repos Changed Error] {e}")


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
        age = (now - parse_ts(row["created_at"])).total_seconds()
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
    voice_compare.prune(supabase)


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
    if result.get("announce_now"):
        result["text"] += "\n\n(In Slack this would also send the announcement straight away.)"
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
    "nudge_preview": lambda _a, _b: run_wednesday_nudge(dry_run=True),
    "routines": lambda a, b: dev_routines(a, b),
    "voice_compare": lambda _a, _b: voice_compare.report(voice_compare.recent(supabase)),
}


# --- DEVELOPER VIEW ON THE SLACK HOME TAB (developers only; every handler re-checks) ---

_home_mode: dict = {}   # slack_id -> "dev" | "mentor"
_dev_last: dict = {}    # slack_id -> {"label", "text", "working"}: tool result shown under the Tools buttons
_channels_note: dict = {}  # slack_id -> result of the last "Refresh list", shown under the Channels heading
_scope_cache = {"at": 0.0, "scopes": []}
DEV_LABELS = {"status": "Status & scopes", "show_context": "What the bot sees", "daily_preview": "Preview daily prompts",
              "republish_homes": "Republish Home tabs", "clear_history": "Clear my chat memory",
              "refresh_channels": "Refresh channel list", "voice_compare": "Compare voice models",
              "nudge_preview": "Preview Wednesday nudge", "routines": "Routines & automatic messages"}


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
        blocks = add_to_top_row(dev_home.build_dev_home(dev_home_state(uid)), dashboard_button_element(slack_user_id=uid))
        (client or app.client).views_publish(user_id=uid, view={"type": "home", "blocks": blocks})
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
    if uid and key in ("paused", "daily_checkin", "channel_context", "wednesday_nudge"):
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


# --- AWARENESS, WEDNESDAY FOUNDER NUDGE AND STANDING ROUTINES ---

SGT_TZ = timezone(timedelta(hours=8))


def studio_event_rows() -> list:
    """Synced studio-calendar meetings (studio_events table, ~30 days ahead); [] when unavailable."""
    try:
        return supabase.table("studio_events").select("title,starts_at,location,meet_url,attendees").execute().data or []
    except Exception:
        return []


def founder_connections() -> dict:
    """{founder_id: {'github': bool, 'google': bool}}. GitHub counts if anyone on the startup connected it."""
    rows = supabase.table("integrations").select("provider,founder_id,startup_id").execute().data or []
    founders = supabase.table("founders").select("id,startup_id").execute().data or []
    gh_startups = {r["startup_id"] for r in rows if r["provider"] == "github"}
    google = {r["founder_id"] for r in rows if r["provider"] == "google"}
    return {f["id"]: {"github": f["startup_id"] in gh_startups, "google": f["id"] in google} for f in founders}


def awareness_text(ident: dict) -> str:
    """Cohorts, sprint sessions, connections and the automatic messages the bot sends, for the agent's context."""
    today = datetime.now(SGT_TZ).date()
    own = (ident.get("context") or {}).get("startup_id") if ident["role"] == "founder" else None
    lines = ["=== COHORTS (data) ===", *cohorts.summary_lines(cohorts.load(supabase), today, studio_event_rows(), own)]
    lines += ["", "=== AUTOMATIC MESSAGES YOU SEND (data) ===", routines.BUILTIN_NOTE]
    if not settings.get("wednesday_nudge"):
        lines.append("(The Wednesday founder nudge is currently switched OFF.)")
    if not settings.get("daily_checkin"):
        lines.append("(The 5 PM check-in prompts are currently switched OFF.)")
    if ident["role"] == "mentor":
        rows = routine_store.active()
        lines += [f"- [{r['id'][:6]}] routine by {r.get('created_by_name') or 'a mentor'}: {routines.describe(r)}" for r in rows] \
            or ["No standing routines set up by mentors yet."]
        try:
            conns = founder_connections()
            founders = supabase.table("founders").select("id,name,slack_user_id").execute().data or []
            lines.append("Founder connections: " + "; ".join(
                f"{f['name']}: calendar {'✓' if conns.get(f['id'], {}).get('google') else '✗'}, GitHub "
                f"{'✓' if conns.get(f['id'], {}).get('github') else '✗'}" + ("" if f.get("slack_user_id") else " (not on Slack yet)")
                for f in founders))
        except Exception as e:
            print(f"[Awareness Warning] {e}")
    return "\n".join(lines)


def nudge_buttons(f: dict, missing: list) -> list:
    blocks = calendar_connect_blocks(f["id"], f["startup_id"], with_divider=True) if "google" in missing else []
    url = github_link(f["id"], f["startup_id"]) if "github" in missing else None
    if url:
        blocks += [{"type": "divider"}, {"type": "actions", "elements": [
            {"type": "button", "style": "primary", "text": {"type": "plain_text", "text": "Connect GitHub"}, "url": url, "action_id": "connect_github"},
            {"type": "button", "text": {"type": "plain_text", "text": "My code is in an organisation"},
             "action_id": "claim_org", "value": f"{f['id']}|{f['startup_id']}"}]}]
    return blocks


def last_checkin_dates() -> dict:
    rows = (supabase.table("submissions").select("startup_id,created_at").eq("confirmed", True)
            .order("created_at", desc=True).limit(500).execute().data or [])
    out = {}
    for r in rows:
        out.setdefault(r["startup_id"], parse_ts(r["created_at"]).astimezone(SGT_TZ).date())
    return out


def run_wednesday_nudge(dry_run: bool = False) -> str:
    """Wednesday 2 PM: each linked founder gets one tailored nudge; mentors hear about unscheduled sprint sessions."""
    if not supabase:
        return "No database."
    from daily_checkin import linked_founders
    today = datetime.now(SGT_TZ).date()
    cohort_list = cohorts.load(supabase)
    active = {sid for c in cohort_list if cohorts.week_of(c["start"], today, c["weeks"]) for sid in c["startup_ids"]}
    in_any = {sid for c in cohort_list for sid in c["startup_ids"]}
    founders = [f for f in linked_founders(supabase) if f["startup_id"] in active or f["startup_id"] not in in_any]
    got = founder_nudges.plan(founders, founder_connections(), last_checkin_dates(), cohort_list, studio_event_rows(), today)
    report = []
    for item in got["founders"]:
        report.append(f"→ {item['founder']['name']}" + (f" (+ connect buttons: {', '.join(item['missing'])})" if item["missing"] else "")
                      + "\n" + item["text"])
        if dry_run:
            continue
        try:
            blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": item["text"][:3000]}}] + nudge_buttons(item["founder"], item["missing"])
            app.client.chat_postMessage(channel=item["slack"], text=item["text"][:3000], blocks=blocks)
            memory.log(item["slack"], "assistant", item["text"])
        except Exception as e:
            print(f"[Wednesday Nudge Error] {item['slack']}: {e}")
    if got["mentors_note"]:
        report.append("→ Mentors\n" + got["mentors_note"])
        if not dry_run:
            for m in supabase.table("mentors").select("slack_user_id").execute().data or []:
                if m.get("slack_user_id"):
                    try:
                        app.client.chat_postMessage(channel=m["slack_user_id"], text=got["mentors_note"])
                    except Exception as e:
                        print(f"[Wednesday Nudge Error] mentor {m['slack_user_id']}: {e}")
    print(f"[Wednesday Nudge] {'previewed' if dry_run else 'sent'} {len(got['founders'])} founder message(s)")
    return "\n\n".join(report) or "No linked founders in an active cohort."


def run_scheduled_wednesday_nudge():
    if SLACK_BOT_TOKEN and settings.get("wednesday_nudge"):
        run_wednesday_nudge()


def routine_recipients(r: dict) -> list:
    """[(slack_id, role)] for a routine's audience."""
    from daily_checkin import linked_founders
    founders = linked_founders(supabase)
    if r["audience"] == "cohort":
        ids = next((c["startup_ids"] for c in cohorts.load(supabase) if c["id"] == r.get("cohort_id")), [])
        founders = [f for f in founders if f["startup_id"] in ids]
    mentors_ = [m["slack_user_id"] for m in supabase.table("mentors").select("slack_user_id").execute().data or []
                if m.get("slack_user_id")]
    if r["audience"] == "mentors":
        return [(m, "mentor") for m in mentors_]
    if r["audience"] == "everyone":
        return [(f["slack_user_id"], "founder") for f in founders] + [(m, "mentor") for m in mentors_ if m != r.get("created_by")]
    if r["audience"] == "people":
        return [(p, get_role(p)) for p in r.get("people") or [] if get_role(p)]
    return [(f["slack_user_id"], "founder") for f in founders]


def send_routine(r: dict, dry_run: bool = False) -> str:
    sent, skipped, lines = 0, 0, []
    conns = founder_connections()
    for uid, role in routine_recipients(r):
        try:
            ident = build_identity(uid, role)
            text = agent.compose(ident, r["instruction"], r.get("created_by_name") or "a mentor") if (r.get("tailored") and agent) else r["instruction"]
        except Exception as e:
            print(f"[Routine Error] compose for {uid}: {e}")
            continue
        if not text or text.strip().upper().startswith(routines.SKIP):
            skipped += 1
            lines.append(f"→ {ident.get('name', uid)}: (skipped, nothing applies)")
            continue
        lines.append(f"→ {ident.get('name', uid)}\n{text}")
        if dry_run:
            continue
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": text[:3000]}}]
        if role == "founder" and re.search(r"github|calendar|connect", r["instruction"], re.IGNORECASE):
            f = ident["context"]
            missing = [k for k in ("google", "github") if not conns.get(f["founder_id"], {}).get(k)]
            blocks += nudge_buttons({"id": f["founder_id"], "startup_id": f["startup_id"]}, missing)
        try:
            app.client.chat_postMessage(channel=uid, text=text[:3000], blocks=blocks)
            memory.log(uid, "assistant", text)
            sent += 1
        except Exception as e:
            print(f"[Routine Error] send to {uid}: {e}")
    summary = f"Sent to {sent} people" + (f", skipped {skipped} it didn't apply to" if skipped else "") + "."
    return summary + ("\n\n" + "\n\n".join(lines) if dry_run else "")


def run_routines():
    """Every minute: send any standing routine that is due (each run claimed first, so it never goes out twice)."""
    if not (supabase and SLACK_BOT_TOKEN):
        return
    now = datetime.now(SGT_TZ)
    for r in routine_store.active():
        at = routines.due(r, now)
        if not at or not routine_store.claim_run(r, at):
            continue
        summary = send_routine(r)
        print(f"[Routine] {r['title']}: {summary}")
        if r.get("created_by"):
            try:
                app.client.chat_postMessage(channel=r["created_by"], text=f"🔁 *{r['title']}* went out. {summary}")
            except Exception as e:
                print(f"[Routine Warning] report: {e}")


def build_routine_card(m: dict) -> list:
    r = m["routine"]
    cohort_name = next((c["name"] for c in cohorts.load(supabase) if c["id"] == r.get("cohort_id")), None)
    first = routines.first_run(r, datetime.now(SGT_TZ))
    text = ("*New standing routine* 🔁\n" + routines.describe({**r, "cohort_name": cohort_name}) +
            f"\nFirst run: {first.strftime('%a %d %b')}." +
            ("\nI'll write each message for the person, and skip anyone it doesn't apply to." if r.get("tailored") else ""))
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": text[:3000]}},
        {"type": "actions", "elements": [
            {"type": "button", "style": "primary", "text": {"type": "plain_text", "text": "Start routine"},
             "action_id": "confirm_meeting", "value": m["id"]},
            {"type": "button", "text": {"type": "plain_text", "text": "Cancel"}, "action_id": "cancel_meeting", "value": m["id"]}]},
    ]


def confirm_routine(row: dict, user_id: str) -> str:
    m = row["payload"]
    if not (get_role(user_id) == "mentor" and m.get("requester_slack") == user_id):
        return ""
    if not memory.claim_meeting(row["id"]):
        return ""
    r = m["routine"]
    saved = routine_store.add({**r, "anchor_date": routines.first_run(r, datetime.now(SGT_TZ)).isoformat(),
                               "created_by": user_id, "created_by_name": m.get("requester")})
    if not saved:
        return "⚠️ I couldn't save the routine (the bot_routines table may not exist yet)."
    return f"✅ Routine started: {routines.describe(saved)}\nFirst run {routines.first_run(saved, datetime.now(SGT_TZ)).strftime('%a %d %b')}. Ask me to list or stop routines any time."


def dev_routines(_args, _by) -> str:
    rows = routine_store.active()
    head = "\n".join(f"[{r['id'][:6]}] {routines.describe(r)}" for r in rows) or "No standing routines yet."
    return head + "\n\n" + routines.BUILTIN_NOTE


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
    if event.get("channel_type") == "im" and event.get("user") and any(
            transcribe.is_audio(f) or syllabus_import.looks_like_syllabus(f, "") for f in event.get("files") or []):
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
    scheduler.add_job(watch_repo_changes, "interval", seconds=20, max_instances=1)
    scheduler.add_job(reconcile_github, "interval", minutes=10, max_instances=1)
    scheduler.add_job(beat, "interval", seconds=30, max_instances=1)
    scheduler.add_job(send_meeting_reminders, "interval", minutes=5, max_instances=1)
    scheduler.add_job(notify_new_milestones, "interval", minutes=1, max_instances=1)
    # Copy upcoming studio meetings into studio_events for the dashboard (only the bot's own events).
    scheduler.add_job(lambda: studio_events.sync(supabase, studio_events_fn(studio_events.WINDOW_DAYS, strict=True)),
                      "interval", minutes=5, max_instances=1, next_run_time=datetime.now(timezone.utc) + timedelta(seconds=20))
    scheduler.add_job(run_weekly_digest, "cron", day_of_week="mon", hour=9, minute=0)
    scheduler.add_job(run_alerts, "cron", day_of_week="mon-fri", hour=9, minute=15)
    scheduler.add_job(process_google_pending, "interval", seconds=10, max_instances=1)
    scheduler.add_job(sync_all_calendars, "interval", minutes=60, max_instances=1)
    scheduler.add_job(lambda: mentor_calendars.sync_all(supabase, gcal), "interval", minutes=10, max_instances=1)
    scheduler.add_job(run_progress_estimates, "interval", minutes=10, max_instances=1)
    scheduler.add_job(link_org_claims, "interval", seconds=60, max_instances=1)
    scheduler.add_job(lambda: dev_controls.run_commands(supabase, DEV_COMMANDS), "interval", seconds=5, max_instances=1)
    scheduler.add_job(lambda: dev_controls.flush_logs(supabase, log_tee), "interval", seconds=10, max_instances=1)
    scheduler.add_job(prune_dev_data, "interval", minutes=60, max_instances=1)
    scheduler.add_job(run_scheduled_wednesday_nudge, "cron", day_of_week="wed", hour=14, minute=0)
    scheduler.add_job(run_routines, "interval", minutes=1, max_instances=1)
    scheduler.add_job(lambda: SLACK_BOT_TOKEN and channels.refresh_list(), "interval", hours=6, max_instances=1)
    if DAILY_CHECKIN:
        scheduler.add_job(run_daily_prompts, "cron", day_of_week="mon-fri", hour=DAILY_CHECKIN_HOUR, minute=0)
        scheduler.add_job(run_daily_nudges, "cron", day_of_week="mon-fri", hour=9, minute=30)
    # Not started here: importing this module (tests, dry runs, scripts) must never run the live jobs.
    # The scheduler starts in __main__, only when the bot itself is launched.


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
        print("Blocker follow-ups that would be sent now:", len(audit_deadlines_and_blockers(dry_run=True)))
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
    if BackgroundScheduler:
        scheduler.start()  # only the real bot runs the timed jobs (prompts, syncs, reminders, heartbeat...)
    if SLACK_BOT_TOKEN and SLACK_APP_TOKEN:
        threading.Thread(target=resume_channel_syncs, daemon=True).start()
        _socket_handler = SocketModeHandler(app, SLACK_APP_TOKEN)
        _socket_handler.start()
    else:
        print(
            "SLACK_BOT_TOKEN or SLACK_APP_TOKEN not provided in .env.\n"
            "Run with 'python slack_bot.py --simulate' to test extraction and card generation in dry-run mode."
        )
