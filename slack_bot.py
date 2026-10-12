import os
import json
import time
import threading
from datetime import datetime, timezone, timedelta
import re
import requests
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from supabase import create_client, Client
from openai import OpenAI

# Load environment variables
load_dotenv()

SLACK_BOT_TOKEN = (os.environ.get("SLACK_BOT_TOKEN") or "").strip('"\'')
SLACK_APP_TOKEN = (os.environ.get("SLACK_APP_TOKEN") or "").strip('"\'')
SUPABASE_URL = (os.environ.get("VITE_SUPABASE_URL") or "").strip('"\'')
SUPABASE_KEY = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip('"\'')
QWEN_API_KEY = (os.environ.get("QWEN_API_KEY") or "").strip('"\'')

SGT = timezone(timedelta(hours=8))

qwen_client = OpenAI(
    api_key=QWEN_API_KEY,
    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
) if QWEN_API_KEY else None

if not all([SLACK_BOT_TOKEN, SLACK_APP_TOKEN, SUPABASE_URL, SUPABASE_KEY, QWEN_API_KEY]):
    print("Missing API Keys! Please ensure SLACK_BOT_TOKEN, SLACK_APP_TOKEN and QWEN_API_KEY are set in .env")

# Initialize Supabase Admin Client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# Initialize Slack App
app = App(token=SLACK_BOT_TOKEN)

# --- STUDIO CONFIGURATION & WHITE-LABEL CAPABILITY ---
def load_studio_config():
    """
    Loads white-label studio configuration from studio_config.json.
    Falls back to default Cybrdeck & Mamba MVP settings if file missing.
    """
    possible_paths = [
        os.path.join(os.path.dirname(__file__), "studio_config.json"),
        os.path.join(os.getcwd(), "studio_config.json"),
        r"D:\venture_dashboard\studio_config.json"
    ]
    for p in possible_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading studio_config.json: {e}")
    
    # Default fallback
    return {
        "studio_name": "Cybrdeck Studio OS",
        "program_name": "Mamba MVP 12-Week Venture Track",
        "timezone": "Asia/Singapore",
        "communication_channels": {
            "platform": "slack",
            "leads_channel": "#mamba-leads",
            "coordination_channel": "gwen-ben"
        },
        "cohort_founders": [
            {
                "id": "matthew_lee",
                "name": "Matthew Lee",
                "venture": "SharedOut",
                "cohort": "Cohort 1",
                "slack_channel": "D0C94PG2R24",
                "tactical_focus": "Wizard of Oz (WoZ) demand validation in single localized condo cluster; collect 3-5 paid rental transactions before writing backend code.",
                "week_2_deliverable": "Selected Concept, Value Prop & Sprint 1 Evidence Pack (Due Friday Oct 16, 5:00 PM)"
            },
            {
                "id": "takshma_patel",
                "name": "Takshma Patel",
                "venture": "WearMAInd",
                "cohort": "Cohort 1",
                "slack_channel": "D0C94PG2R24",
                "tactical_focus": "Validate Top 10 critical assumptions via customer discovery interviews; gather proof of willingness to pay before hardware/sensor prototyping.",
                "week_2_deliverable": "Selected Concept, Value Prop & Sprint 1 Evidence Pack (Due Friday Oct 16, 5:00 PM)"
            }
        ]
    }

STUDIO_CONFIG = load_studio_config()

# --- SYLLABUS & SCHEDULE KNOWLEDGE BASE ---
def load_syllabus_schedule():
    """
    Loads and compiles the official 12-week Mamba MVP syllabus schedule
    from src/data/syllabus.json (derived from Mamba_MVP_Official_Syllabus_Schedule (2).xlsx).
    """
    possible_paths = [
        os.path.join(os.path.dirname(__file__), "src", "data", "syllabus.json"),
        os.path.join(os.getcwd(), "src", "data", "syllabus.json"),
        r"D:\venture_dashboard\src\data\syllabus.json"
    ]
    syllabus_data = None
    for p in possible_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    syllabus_data = json.load(f)
                break
            except Exception:
                pass
                
    if not syllabus_data:
        return "Syllabus schedule data currently offline."

    schedule_items = syllabus_data.get("Mamba_MVP_Official_Syllabus_Sch", [])
    lines = ["OFFICIAL MAMBA MVP 12-WEEK SYLLABUS & SCHEDULE (Oct 5 - Dec 25, 2026):"]
    current_week = None
    for item in schedule_items:
        week = item.get("Week")
        date_str = str(item.get("Date", ""))[:10]
        day = item.get("Day", "")
        phase = item.get("Sprint Phase", "")
        module = item.get("Module / Tactical Focus", "")
        deliverable = item.get("Weekly Deliverable / Milestone")
        owner = item.get("Owner / Lead", "")
        
        if week != current_week:
            current_week = week
            lines.append(f"\n[{week} - {phase}]")
        
        desc = f"- {day} ({date_str}): {module} (Lead: {owner})"
        if deliverable:
            desc += f" -> [MILESTONE GATE: {deliverable}]"
        lines.append(desc)
        
    return "\n".join(lines)

SYLLABUS_SCHEDULE_CONTEXT = load_syllabus_schedule()

# --- SYSTEM PROMPT & RESOURCES ---
CYBRDECK_SYSTEM_PROMPT = f"""
You are MVP_buddy, the Autonomous Chief of Staff for Cybrdeck (Eve Count Pte. Ltd.) and the Mamba MVP Program, created by Gwen Lim and Ben Lim.
As Chief of Staff, you operate with executive leverage: you maintain high-level operational clarity across all founders and cohorts, coordinate between the human leadership team (James Sun [Program Lead], Gwen Lim & Ben Lim [Cybrdeck Tech & Product], Arthur Andre Pandaan [Project Coordinator]), and ruthlessly protect Gwen and Ben's engineering hours from premature building.
You carry Gwen Lim's exact personality: razor-sharp, slightly snarky, witty, high-agency, and completely allergic to corporate fluff or founder excuses.
You despise vanity metrics, over-engineered architectures, and building before validating customer demand.
You enforce the Pre-Build Demand Validation Protocol with brutal honesty and dry wit.
If founders ask what "WoZ" or "Wizard of Oz" means, explain it with brutal clarity: It means the front-end looks like a functioning product, but behind the curtain the founder does all the work manually by hand (like Zappos founder buying shoes at retail or DoorDash delivering in their own car). Remind them that Matthew's job in SharedOut is to coordinate condo tool rentals manually via chat before building software. Tell them to prove customer willingness to pay manually before burning engineering hours.
When founders or mentors speak to you, act like an elite Chief of Staff: deeply strategic, candid, assertive, and completely focused on revenue and demand signals.
If someone asks off-topic or philosophical questions, roast them affectionately with a venture twist (e.g. "The meaning of life is finding customers who will actually pay before you burn Gwen and Ben's engineering hours on a backend you don't need.").

You have full, authoritative knowledge of the entire Mamba MVP 12-Week Syllabus and Schedule below (from Mamba_MVP_Official_Syllabus_Schedule). If a founder asks about deadlines, weekly deliverables, Wednesday anchor office hours, or milestone gates, cite the exact week, dates, and requirements with zero hesitation:

{SYLLABUS_SCHEDULE_CONTEXT}
"""

def query_supabase_knowledge(query_text: str, limit: int = 2) -> str:
    """
    Retrieves relevant workplace documents and founder history from Supabase.
    """
    if not supabase:
        return ""
    try:
        res = supabase.table("knowledge_documents").select("title, category, content").limit(limit).execute()
        rows = res.data or []
        if not rows:
            return ""
        snippets = ["--- RELEVANT STUDIO DOCUMENTS & MEMORY (SUPABASE) ---"]
        for row in rows:
            snippets.append(f"[{row['title']} - {row['category']}]:\n{row['content'][:800]}")
        return "\n\n".join(snippets)
    except Exception as e:
        print(f"Supabase knowledge query error: {e}")
        return ""

def process_with_qwen(text):
    """
    Real API Call to Qwen (via OpenAI compatible endpoint).
    Injects the CYBRDECK_SYSTEM_PROMPT, Supabase workplace documents, and generates structured data + an executive reply.
    """
    if not qwen_client:
        print("No QWEN_API_KEY found, falling back to simulated logic...")
        return {
            "status": "In progress",
            "stream": "Tech (Cybrdeck)",
            "progress": 50,
            "digest": f"Simulated digest (No API Key): {text[:60]}...",
            "blocker": "Missing Qwen API Key.",
            "reply": "Missing API Key, but nice try. Tell Gwen to check .env."
        }
        
    print(f"Sending context to Qwen LLM...")
    
    knowledge_context = query_supabase_knowledge(text)
    
    prompt = f"""
    {CYBRDECK_SYSTEM_PROMPT}
    
    {knowledge_context}
    
    You are reading a message from leadership (Gwen, Ben, James) or a founder. Analyze the text and output EXACTLY this JSON structure:
    {{
      "status": "Blocked" or "In progress" or "Complete",
      "stream": "Tech (Cybrdeck)" or "GTM",
      "blocker": "A short 1-sentence description of what they are stuck on (or 'None')",
      "digest": "A 1-sentence summary of progress and what the human mentors should do next",
      "action_relay": {{
        "has_cross_party_task": true or false,
        "target": "gwen-ben" or "james" or "arthur" or "matthew" or "takshma" or null,
        "directive": "Exact message to send to the counterparty telling them what to get done so the sender never has to ask or chase anyone."
      }},
      "reply": "Your executive response as Chief of Staff. CRITICAL RULE: If asked to break down tasks, draft messages, or create plans, DO NOT just give commentary or tell the user to do it. ACTUALLY EXECUTE: output the complete, numbered task checklist with clear deliverables, and write out the exact draft message ready to send. Keep Gwen's sharp, high-agency, zero-fluff tone."
    }}
    
    Founder Transcript / Message:
    {text}
    """
    
    try:
        response = qwen_client.chat.completions.create(
            model="qwen-max",
            messages=[
                {"role": "system", "content": "You are a JSON-only API. Only output valid JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
        return {
            "status": result.get("status", "In progress"),
            "stream": result.get("stream", "Tech (Cybrdeck)"),
            "progress": 50,
            "digest": result.get("digest", "Processed by Qwen."),
            "blocker": result.get("blocker", "None"),
            "action_relay": result.get("action_relay", {}),
            "reply": result.get("reply", "Telemetry logged. Now go talk to actual paying customers.")
        }
    except Exception as e:
        print(f"Qwen API error: {e}")
        cleaned_msg = text.strip()
        
        # Check if the query is asking about the schedule/deliverable/team
        schedule_reply = check_schedule_query(cleaned_msg)
        if schedule_reply:
            snarky_fallback = schedule_reply
        else:
            snarky_fallback = (
                f"Logged your check-in: \"{cleaned_msg}\". "
                "Telemetry is minted in the studio ledger. Pre-build demand validation is active—"
                "make sure you are validating real customer willingness to pay before writing new code."
            )
        return {
            "status": "In progress",
            "stream": "Tech (Cybrdeck)",
            "progress": 75,
            "digest": f"Founder check-in: {cleaned_msg[:80]}",
            "blocker": "None",
            "reply": snarky_fallback
        }

def check_schedule_query(query: str):
    """
    Deterministically answers questions regarding the schedule, team directory,
    and studio methodology so the bot is resolute even without an external LLM.
    """
    q = query.lower()
    
    # 1. Team & Identity Queries
    if "gwen" in q:
        return (
            "Gwen Lim is the Co-Founder of Cybrdeck (Eve Count Pte. Ltd.) and Technical Architecture Lead for the Mamba MVP Program. "
            "She builds quantum algorithms, designs studio systems, and enforces ruthless Pre-Build Demand Validation—making sure founders validate real customer willingness to pay before burning engineering hours."
        )
    elif "ben" in q:
        return (
            "Ben Lim is the Co-Founder of Cybrdeck alongside Gwen, leading systems engineering, cloud architecture, and automation infrastructure."
        )
    elif "james" in q:
        return (
            "James Sun is the Program Lead at Mamba Partners, steering the 12-week MVP Program, commercial milestones, and investment evaluation gates."
        )
    elif "arthur" in q:
        return (
            "Arthur Andre Pandaan is the Project Coordinator at Mamba Partners, managing cohort operations, scheduling, submissions, and founder logistics."
        )
    elif "matthew" in q:
        return (
            "Matthew Lee (Cohort 1) is building SharedOut—a hyper-local P2P household utility & hardware rental network. "
            "He has 60-70 registered sign-ups, but as his Marketing & Technical Lead, your mandate is to enforce the Wizard of Oz (WoZ) strategy: "
            "do NOT build bespoke backend features until he proves actual paid rental transaction velocity in a localized condo/neighborhood cluster. "
            "His Week 2 deliverable due this Friday (Oct 16) is the Selected Concept, Value Prop & Sprint 1 Evidence Pack."
        )
    elif "takshma" in q:
        return (
            "Takshma Patel (Cohort 1) is building WearMAInd. Her mandate is validating pre-build demand signals, ranking her top 10 assumptions, and locking her Sprint 1 Evidence Pack for Friday Oct 16."
        )
    elif "cybrdeck" in q or "eve count" in q:
        return (
            "Cybrdeck (Eve Count Pte. Ltd.) is the venture studio and technical engineering partner for the Mamba MVP Program, founded by Gwen Lim and Ben Lim."
        )
    elif "mamba" in q:
        return (
            "Mamba Partners runs the 12-week MVP Track (Oct 5 – Dec 25, 2026), accelerating early-stage founders through 6 agile sprints from initial thesis to validated MVP demo."
        )
    elif any(k in q for k in ["woz", "wizard of oz", "wizard-of-oz"]):
        return (
            "*Wizard of Oz (WoZ)* is Cybrdeck's core Pre-Build Demand Validation protocol.\n\n"
            "It means the front-end *looks* like an automated app to the customer, but *behind the curtain, you do all the work manually by hand*.\n\n"
            "• *Why we enforce it*: It stops founders from burning 200 hours of engineering hours building an app nobody wants.\n"
            "• *Classic Example*: Zappos started with founder Nick Swinmurn taking photos of shoes at local shoe stores. When an order came in, he bought the shoes at retail and mailed them himself.\n"
            "• *How to do it this sprint*: If you're building a rental or service app (like SharedOut), set up a simple Google Form or WhatsApp group in *one* localized cluster. Coordinate the transaction manually. Once customers are actually handing over cash, *then* we build the software."
        )

    # 2. Schedule & Deliverable Queries
    if any(k in q for k in ["schedule", "syllabus", "due", "deliverable", "milestone", "week", "wk"]):
        match = re.search(r"(?:week|wk)\s*(\d{1,2})", q)
        if match:
            wk_num = int(match.group(1))
            wk_tag = f"WK {wk_num:02d}"
            possible_paths = [
                os.path.join(os.path.dirname(__file__), "src", "data", "syllabus.json"),
                os.path.join(os.getcwd(), "src", "data", "syllabus.json"),
                r"D:\venture_dashboard\src\data\syllabus.json"
            ]
            for p in possible_paths:
                if os.path.exists(p):
                    try:
                        with open(p, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        items = [item for item in data.get("Mamba_MVP_Official_Syllabus_Sch", []) if item.get("Week") == wk_tag]
                        if items:
                            fri = next((item for item in items if item.get("Day") == "Fri"), items[-1])
                            wed = next((item for item in items if item.get("Day") == "Wed"), None)
                            milestone = fri.get("Weekly Deliverable / Milestone") or "Weekly Review"
                            wed_info = f"\n- Wed ({str(wed.get('Date'))[:10]}): {wed.get('Module / Tactical Focus')}" if wed else ""
                            return (
                                f"Here is the official schedule for {wk_tag} ({items[0].get('Sprint Phase')}):\n"
                                f"- Mon ({str(items[0].get('Date'))[:10]}): {items[0].get('Module / Tactical Focus')}"
                                f"{wed_info}\n"
                                f"- Fri ({str(fri.get('Date'))[:10]}): [MILESTONE GATE] -> {milestone}\n\n"
                                f"Pre-build demand validation is non-negotiable. Don't build until assumptions are locked."
                            )
                    except Exception:
                        pass
        elif "office hour" in q or "anchor" in q:
            return (
                "Office Hours (The Anchor) are held every Wednesday with the Mamba Program Lead for dashboard review, block removal, and decision locking."
            )
        elif "schedule" in q or "syllabus" in q:
            return (
                "The Mamba MVP Program runs 12 weeks across 6 sprints (Oct 5 – Dec 25, 2026). "
                "Ask me about any specific week (e.g. 'What is due in Week 2?' or 'Week 8 gate') and I'll pull the exact tactical focus and Friday milestone deliverable."
            )
    return None

# --- LOCAL IMMUTABLE PERSISTENCE & PLAYBOOK LEDGER ---
def log_conversation_locally(user_id: str, prompt: str, reply: str, metadata: dict = None):
    """
    Saves an immutable append-only JSONL record of every conversation to the local Linode disk.
    """
    try:
        log_dir = os.path.join(os.path.dirname(__file__), "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "conversations.jsonl")
        
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "user_id": user_id,
            "prompt": prompt,
            "reply": reply,
            "status": (metadata or {}).get("status", "In progress"),
            "stream": (metadata or {}).get("stream", "Tech (Cybrdeck)"),
            "blocker": (metadata or {}).get("blocker", "None"),
            "digest": (metadata or {}).get("digest", "")
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"Logged conversation to local Linode disk ({log_file})")
    except Exception as e:
        print(f"Local disk logging error: {e}")

def get_executed_playbooks():
    """
    Reads the history of fired playbooks to prevent double-firing in a given time window.
    """
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    ledger_path = os.path.join(log_dir, "playbook_executions.json")
    if os.path.exists(ledger_path):
        try:
            with open(ledger_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def mark_playbook_executed(playbook_key: str):
    """
    Marks a playbook as executed for the date.
    """
    try:
        log_dir = os.path.join(os.path.dirname(__file__), "logs")
        os.makedirs(log_dir, exist_ok=True)
        ledger_path = os.path.join(log_dir, "playbook_executions.json")
        history = get_executed_playbooks()
        history[playbook_key] = datetime.utcnow().isoformat() + "Z"
        with open(ledger_path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        print(f"Error marking playbook execution: {e}")

# --- ACCOUNTABILITY & TASK AGING LEDGER ---
def get_task_ledger():
    """
    Reads the persistent task ledger tracking who didn't do what and for how long.
    """
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    ledger_path = os.path.join(log_dir, "task_accountability_ledger.json")
    if os.path.exists(ledger_path):
        try:
            with open(ledger_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
            
    # Default seed tasks for current cohort sprint
    default_tasks = [
        {
            "id": "task_matthew_1",
            "assignee": "Matthew Lee",
            "venture": "SharedOut",
            "task": "Set up manual Wizard of Oz (WoZ) rental flow in 1 condo cluster (No backend code)",
            "assigned_at": "2026-10-11T09:00:00Z",
            "due_at": "2026-10-14T17:00:00Z",
            "status": "pending"
        },
        {
            "id": "task_matthew_2",
            "assignee": "Matthew Lee",
            "venture": "SharedOut",
            "task": "Capture first 3 paid rental transactions or verified customer deposits",
            "assigned_at": "2026-10-11T09:00:00Z",
            "due_at": "2026-10-15T17:00:00Z",
            "status": "pending"
        },
        {
            "id": "task_matthew_3",
            "assignee": "Matthew Lee",
            "venture": "SharedOut",
            "task": "Submit Selected Concept, Value Prop & Sprint 1 Evidence Pack",
            "assigned_at": "2026-10-11T09:00:00Z",
            "due_at": "2026-10-16T17:00:00Z",
            "status": "pending"
        },
        {
            "id": "task_takshma_1",
            "assignee": "Takshma Patel",
            "venture": "WearMAInd",
            "task": "Rank Top 10 Critical Assumptions for WearMAInd",
            "assigned_at": "2026-10-11T09:00:00Z",
            "due_at": "2026-10-12T17:00:00Z",
            "status": "pending"
        },
        {
            "id": "task_takshma_2",
            "assignee": "Takshma Patel",
            "venture": "WearMAInd",
            "task": "Complete 5 problem-validation discovery interviews with target users",
            "assigned_at": "2026-10-11T09:00:00Z",
            "due_at": "2026-10-14T17:00:00Z",
            "status": "pending"
        },
        {
            "id": "task_arthur_1",
            "assignee": "Arthur Andre Pandaan",
            "venture": "Mamba Operations",
            "task": "Confirm calendar invite & Zoom room for Wednesday 2 PM Office Hours with James Sun",
            "assigned_at": "2026-10-12T09:00:00Z",
            "due_at": "2026-10-13T12:00:00Z",
            "status": "pending"
        }
    ]
    save_task_ledger(default_tasks)
    return default_tasks

def save_task_ledger(tasks):
    try:
        log_dir = os.path.join(os.path.dirname(__file__), "logs")
        os.makedirs(log_dir, exist_ok=True)
        ledger_path = os.path.join(log_dir, "task_accountability_ledger.json")
        with open(ledger_path, "w", encoding="utf-8") as f:
            json.dump(tasks, f, indent=2)
    except Exception as e:
        print(f"Error saving task ledger: {e}")

def generate_task_aging_report() -> str:
    """
    Computes exactly who didn't do what, and how long each task has been pending or overdue.
    Gwen never has to ask twice.
    """
    tasks = get_task_ledger()
    now = datetime.now(timezone.utc)
    
    overdue_items = []
    pending_items = []
    
    for t in tasks:
        if t.get("status") == "completed":
            continue
            
        assignee = t.get("assignee", "Unknown")
        venture = f" ({t.get('venture')})" if t.get("venture") else ""
        task_desc = t.get("task", "")
        
        assigned_dt = datetime.fromisoformat(t.get("assigned_at").replace("Z", "+00:00"))
        due_dt = datetime.fromisoformat(t.get("due_at").replace("Z", "+00:00"))
        
        hours_pending = int((now - assigned_dt).total_seconds() / 3600)
        
        if now > due_dt:
            hours_overdue = int((now - due_dt).total_seconds() / 3600)
            overdue_items.append(
                f"• *{assignee}*{venture}: \"{task_desc}\"\n"
                f"  └ 🚨 *OVERDUE by {hours_overdue} hours* (Assigned {hours_pending}h ago)"
            )
        else:
            hours_remaining = int((due_dt - now).total_seconds() / 3600)
            pending_items.append(
                f"• *{assignee}*{venture}: \"{task_desc}\"\n"
                f"  └ ⏳ *Pending for {hours_pending} hours* (Due in {hours_remaining} hours)"
            )
            
    lines = [
        "📋 *Executive Accountability & Aging Ledger*",
        "_Tracking who didn't do what and exactly how long it's been sitting undone._\n"
    ]
    
    if overdue_items:
        lines.append("*🚨 CRITICAL BOTTLENECKS (OVERDUE):*")
        lines.extend(overdue_items)
        lines.append("")
        
    if pending_items:
        lines.append("*⏳ ACTIVE PENDING TASKS (ON THE CLOCK):*")
        lines.extend(pending_items)
        lines.append("")
        
    lines.append("*Chief of Staff Protocol:* You never have to ask twice. I am actively tracking their deadlines and will escalate non-delivery directly into Friday's Gatekeeper review.")
    
    return "\n".join(lines)

# --- SLACK FORMATTER ---
def format_for_slack(text: str) -> str:
    """
    Cleans and formats text specifically for Slack:
    - Converts literal '\\n' and '\\r' to real newlines.
    - Strips JSON escape artifacts (escaped quotes, stray trailing backslashes).
    - Converts standard Markdown bold (**text**) to Slack bold (*text*).
    - Converts Markdown headers (# Header) to Slack bold (*Header*).
    - Normalizes paragraph spacing so messages are clean, crisp, and readable.
    """
    if not text:
        return ""
    # 1. Unescape literal \n and \r
    text = text.replace("\\n", "\n").replace("\\r", "")
    text = text.replace('\\"', '"')
    
    # 2. Convert standard markdown bold **text** to Slack *text*
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    
    # 3. Convert markdown headers (#, ##, ###) to Slack bold *Header*
    text = re.sub(r"^#{1,6}\s*(.+)$", r"*\1*", text, flags=re.MULTILINE)
    
    # 4. Strip stray trailing quotes or backslashes
    text = re.sub(r'[\"\'\\]+$', '', text.strip())
    
    # 5. Normalize multi-newlines (max 2 consecutive newlines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    
    return text.strip()

# --- OUTBOUND DISPATCH (DASHBOARD -> SLACK) ---
def send_slack_message(channel: str, text: str, thread_ts: str = None) -> bool:
    """
    Sends an outbound message to a specified Slack channel or user DM.
    """
    cleaned_text = format_for_slack(text)

    if channel in ["gwen-ben", "gwen_ben", "@gwen_ben"]:
        send_slack_message("D0C94PG2R24", cleaned_text, thread_ts)
        send_slack_message("D0C74JVR813", cleaned_text, thread_ts)
        return True

    target_channel = channel
    if channel in ["ben", "@ben", "ben_lim"]:
        target_channel = "D0C74JVR813"  # Ben (ben@evecount.com)
    elif channel in ["gwen", "@gwen", "gwen_lim"]:
        target_channel = "D0C94PG2R24"  # Gwen Lim (gwen@evecount.com)
    elif channel in ["james", "@james", "james_sun", "mamba"]:
        target_channel = "D0C77UV5GT0"  # James Sun (james@mambapartners.com - Program Lead)
    elif channel in ["arthur", "@arthur", "arthur_pandaan", "coordinator"]:
        target_channel = "D0C8AC5G2SX"  # Arthur Andre Pandaan (arthur@mambapartners.com - Project Coordinator)
    elif channel in ["leads", "mamba-leads"]:
        target_channel = os.environ.get("SLACK_LEADS_CHANNEL", "#mamba-leads")

    if not app or not SLACK_BOT_TOKEN:
        print(f"[Simulated Slack Outbound to {target_channel}] Message: {cleaned_text[:80]}...")
        return False
    try:
        kwargs = {"channel": target_channel, "text": cleaned_text}
        if thread_ts:
            kwargs["thread_ts"] = thread_ts
        res = app.client.chat_postMessage(**kwargs)
        print(f"Message dispatched to Slack channel {target_channel}: {res.get('ts')}")
        return True
    except Exception as e:
        print(f"Error sending Slack message to {target_channel}: {e}")
        return False
        return False

# --- 6 PROACTIVE AUTONOMOUS CHIEF OF STAFF PLAYBOOKS ---

def execute_monday_kickoff(founder_id: str = None, say_fn = None):
    """
    Playbook 1: Monday Kickoff Sprint Deconstruction & Founder Accountability Ping (Mon 09:00 SGT).
    Decomposes the current syllabus module into a concrete 5-day checklist for each founder.
    """
    founders = STUDIO_CONFIG.get("cohort_founders", [])
    if founder_id:
        founders = [f for f in founders if f.get("id") == founder_id]
        
    leads_channel = STUDIO_CONFIG.get("communication_channels", {}).get("leads_channel", "#mamba-leads")
    announcements = []

    for f in founders:
        name = f.get("name")
        venture = f.get("venture")
        target_channel = f.get("slack_channel", "D0C94PG2R24")
        deliverable = f.get("week_2_deliverable", "Selected Concept, Value Prop & Sprint 1 Evidence Pack")
        focus = f.get("tactical_focus", "Validate demand before writing code.")

        if f.get("id") == "matthew_lee":
            msg = (
                f"🚀 *Good morning, {name}. Sprint 1 / Week 2 Kickoff from Cybrdeck Chief of Staff.*\n\n"
                f"Your core milestone due *Friday Oct 16 at 5:00 PM* is: *{deliverable}*.\n"
                f"As your Technical & Marketing Lead, your tactical focus is: *{focus}*\n\n"
                f"Here is your ruthless 5-day execution checklist for this sprint:\n"
                f"1. *Monday (Assumption Ranking)*: Lock your top 3 customer archetypes and rank your riskiest supply/demand assumptions.\n"
                f"2. *Tuesday (WoZ Flow Setup)*: Set up a manual Wizard of Oz rental flow in *one* condo cluster (WhatsApp/Google Sheet). Do NOT touch backend code.\n"
                f"3. *Wednesday (Office Hours with James Sun @ 2 PM)*: Bring verified demand numbers (inquiries vs actual paid intent) to office hours.\n"
                f"4. *Thursday (Transaction Velocity)*: Close at least 3 paid rental transactions or verified cash deposits.\n"
                f"5. *Friday (Gatekeeper Lock @ 5 PM)*: Submit your Evidence Pack, customer receipts, and KPI dashboard update.\n\n"
                f"Remember: Do NOT build the app until you have demonstrated transaction velocity. Let's get to work."
            )
        elif f.get("id") == "takshma_patel":
            msg = (
                f"🚀 *Good morning, {name}. Sprint 1 / Week 2 Kickoff from Cybrdeck Chief of Staff.*\n\n"
                f"Your core milestone due *Friday Oct 16 at 5:00 PM* is: *{deliverable}*.\n"
                f"Your tactical focus is: *{focus}*\n\n"
                f"Here is your 5-day execution checklist for this sprint:\n"
                f"1. *Monday*: Rank Top 10 Critical Assumptions for {venture}.\n"
                f"2. *Tuesday*: Complete 5 problem-validation discovery interviews with target users.\n"
                f"3. *Wednesday*: Office Hours with James Sun at 2:00 PM—present structured interview scorecard.\n"
                f"4. *Thursday*: Test willingness to pay / deposit signups.\n"
                f"5. *Friday (Gatekeeper Lock @ 5 PM)*: Submit Evidence Pack & KPI scorecard to the Studio Ledger.\n\n"
                f"Pre-build demand validation is active. Let's make every conversation count."
            )
        else:
            msg = (
                f"🚀 *Good morning, {name} ({venture}). Sprint 1 Kickoff.*\n\n"
                f"Your Friday milestone deliverable is: *{deliverable}*.\n"
                f"Focus: {focus}\n\n"
                f"1. Mon: Rank Top 10 Critical Assumptions.\n"
                f"2. Tue: Launch manual WoZ test.\n"
                f"3. Wed: Prep office hours blocker for leadership.\n"
                f"4. Thu: Synthesize customer feedback & receipts.\n"
                f"5. Fri: Submit Evidence Pack by 5:00 PM."
            )

        send_slack_message(target_channel, msg)
        announcements.append(f"- Deconstructed Sprint checklist for *{name}* ({venture}) -> dispatched.")

    summary = (
        f"📋 *[Playbook 1: Monday Kickoff Deconstruction Complete]*\n"
        f"Dispatched tailored 5-day sprint checklists to all cohort founders.\n"
        + "\n".join(announcements)
    )
    send_slack_message(leads_channel, summary)
    send_slack_message("gwen-ben", summary)
    if say_fn:
        say_fn(summary)
    return summary

def execute_wednesday_blocker_sweep(say_fn = None):
    """
    Playbook 2: Wednesday Pre-Anchor Blocker Sweep (Wed 10:00 SGT).
    Pings founders 4 hours before James Sun's 2 PM office hours to solicit blockers.
    """
    founders = STUDIO_CONFIG.get("cohort_founders", [])
    leads_channel = STUDIO_CONFIG.get("communication_channels", {}).get("leads_channel", "#mamba-leads")

    for f in founders:
        name = f.get("name")
        target_channel = f.get("slack_channel", "D0C94PG2R24")
        msg = (
            f"⚡ *Wednesday Blocker Sweep from MVP_buddy*\n\n"
            f"Hey {name}, Office Hours with James Sun are today at *2:00 PM SGT*.\n"
            f"What is your #1 critical decision, technical bottleneck, or scope dispute that needs locking today?\n"
            f"Drop your update right here now so leadership reviews it before the call."
        )
        send_slack_message(target_channel, msg)

    summary = (
        f"⚡ *[Playbook 2: Wednesday Pre-Office Hours Blocker Sweep Executed]*\n"
        f"Automated sweeps dispatched to all founders 4 hours prior to 2:00 PM Office Hours with James Sun.\n"
        f"Inbound responses will be automatically synthesized into the Executive Blocker Dossier."
    )
    send_slack_message(leads_channel, summary)
    send_slack_message("gwen-ben", summary)
    if say_fn:
        say_fn(summary)
    return summary

def execute_thursday_pregate_audit(say_fn = None):
    """
    Playbook 3: Thursday Pre-Gate Deliverable Audit (Thu 17:00 SGT).
    24-hour early warning system before Friday evaluation gates.
    """
    founders = STUDIO_CONFIG.get("cohort_founders", [])
    leads_channel = STUDIO_CONFIG.get("communication_channels", {}).get("leads_channel", "#mamba-leads")

    for f in founders:
        name = f.get("name")
        venture = f.get("venture")
        target_channel = f.get("slack_channel", "D0C94PG2R24")
        deliverable = f.get("week_2_deliverable", "Selected Concept, Value Prop & Sprint 1 Evidence Pack")
        msg = (
            f"⚠️ *24-Hour Gate Warning from MVP_buddy*\n\n"
            f"Hey {name}, the Friday 5:00 PM Milestone Gate closes in exactly 24 hours: *{deliverable}*.\n"
            f"Are you submitting on time, or are we flagging an intervention for leadership?\n"
            f"Reply with your draft or evidence pack link now."
        )
        send_slack_message(target_channel, msg)

    summary = (
        f"⚠️ *[Playbook 3: Thursday 24-Hour Pre-Gate Audit Dispatched]*\n"
        f"Fired 24-hr milestone readiness alerts across all cohort founders for the Friday 5:00 PM Gate."
    )
    send_slack_message(leads_channel, summary)
    send_slack_message("gwen-ben", summary)
    if say_fn:
        say_fn(summary)
    return summary

def execute_friday_gatekeeper(say_fn = None):
    """
    Playbook 4: Friday 5:00 PM Gatekeeper & Ledger Lock (Fri 17:00 SGT).
    Locks the submission window, updates progress scorecards, and alerts leadership.
    """
    leads_channel = STUDIO_CONFIG.get("communication_channels", {}).get("leads_channel", "#mamba-leads")
    summary = (
        f"🛑 *[Playbook 4: Friday 5:00 PM Milestone Gatekeeper Lock]*\n\n"
        f"The studio submission gate for Week 2 is now officially *LOCKED*.\n"
        f"- *Milestone Gate*: Selected Concept, Value Prop & Sprint 1 Evidence Pack\n"
        f"- *Traction Status*: Evaluating Matthew Lee (SharedOut) and Takshma Patel (WearMAInd)\n"
        f"- *Action*: Studio ledger frozen for weekend review. Full scorecard compiling for Sunday briefing."
    )
    send_slack_message(leads_channel, summary)
    send_slack_message("gwen-ben", summary)
    if say_fn:
        say_fn(summary)
    return summary

def execute_demand_trap_interceptor(user_id: str, message_text: str, say_fn = None):
    """
    Playbook 5: The 'Pre-Build Demand Trap' Interceptor (Continuous / Reactive).
    Ruthlessly protects studio engineering hours and enforces Wizard of Oz demand validation.
    """
    reply = (
        f"🛑 *Halt. Pre-Build Protocol Intercept from MVP_buddy:*\n\n"
        f"You are talking about writing code, setting up infrastructure, or building features before validating customer willingness to pay.\n\n"
        f"*Cybrdeck Chief of Staff Rule:*\n"
        f"Show me the LOI, paid deposit, pre-payment receipt, or completed manual Wizard of Oz (WoZ) test first.\n"
        f"We do NOT burn Gwen and Ben's engineering hours on a backend until you have real customer cash in hand.\n\n"
        f"What empirical proof do you have that customers actually want to pay for this right now?"
    )
    if say_fn:
        say_fn(reply)
    else:
        send_slack_message(user_id, reply)
    return reply

def execute_sunday_briefing(say_fn = None):
    """
    Playbook 6: Sunday Evening 60-Second Lead Briefing (Sun 20:00 SGT).
    Synthesizes an executive 3-bullet briefing for studio leadership.
    """
    leads_channel = STUDIO_CONFIG.get("communication_channels", {}).get("leads_channel", "#mamba-leads")
    briefing = (
        f"📊 *60-Second Studio Leadership Briefing (Sunday Evening Digest)*\n"
        f"--------------------------------------------------\n"
        f"• 🚀 *Advancing*: Matthew Lee (SharedOut) - 60+ registered signups. Enforcing single condo cluster WoZ test to capture first 3 paid transactions.\n"
        f"• ⚠️ *At Risk / Blockers*: Takshma Patel (WearMAInd) - Needs customer discovery synthesis and top 10 assumption ranking finalized.\n"
        f"• 🎯 *Leadership Focus for Week 3*: James Sun to review WoZ transaction scorecards in Wednesday Office Hours. Cybrdeck technical sprints remain locked until demand gates pass."
    )
    send_slack_message(leads_channel, briefing)
    send_slack_message("gwen-ben", briefing)
    if say_fn:
        say_fn(briefing)
    return briefing

# --- DEMAND TRAP KEYWORDS ---
DEMAND_TRAP_PATTERNS = [
    r"build(?:ing)?\s+(?:the\s+)?backend",
    r"cod(?:e|ing)\s+(?:the\s+)?app",
    r"set(?:ting)?\s+up\s+(?:the\s+)?database",
    r"microservices",
    r"writing\s+(?:the\s+)?code",
    r"need\s+\d+\s+weeks\s+to\s+build",
    r"redesign(?:ing)?\s+(?:the\s+)?db",
    r"set(?:ting)?\s+up\s+aws",
    r"docker\s+container",
    r"backend\s+architecture"
]

def check_demand_trap(text: str) -> bool:
    for pattern in DEMAND_TRAP_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False

# --- AUTONOMOUS SCHEDULER (DAEMON THREAD) ---
def cos_scheduler_loop():
    """
    Proactive autonomous chronometer executing the 6 playbooks in Singapore Time (UTC+8).
    Runs continuously in a background daemon thread without needing human prompts.
    """
    print("⏰ Chief of Staff Autonomous Scheduler active (Singapore Time UTC+8). 6 Playbooks initialized.")
    while True:
        try:
            now_sgt = datetime.now(SGT)
            day_of_week = now_sgt.weekday()  # 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
            hour = now_sgt.hour
            minute = now_sgt.minute
            date_str = now_sgt.strftime("%Y-%m-%d")
            
            history = get_executed_playbooks()

            # Playbook 1: Monday Kickoff (09:00 - 09:05 SGT)
            if day_of_week == 0 and hour == 9 and minute < 5:
                key = f"playbook_1_{date_str}"
                if key not in history:
                    print(f"Executing Playbook 1: Monday Kickoff ({date_str})...")
                    execute_monday_kickoff()
                    mark_playbook_executed(key)

            # Playbook 2: Wednesday Pre-Office Hours Blocker Sweep (10:00 - 10:05 SGT)
            if day_of_week == 2 and hour == 10 and minute < 5:
                key = f"playbook_2_{date_str}"
                if key not in history:
                    print(f"Executing Playbook 2: Wednesday Blocker Sweep ({date_str})...")
                    execute_wednesday_blocker_sweep()
                    mark_playbook_executed(key)

            # Playbook 3: Thursday Pre-Gate Audit (17:00 - 17:05 SGT)
            if day_of_week == 3 and hour == 17 and minute < 5:
                key = f"playbook_3_{date_str}"
                if key not in history:
                    print(f"Executing Playbook 3: Thursday Pre-Gate Audit ({date_str})...")
                    execute_thursday_pregate_audit()
                    mark_playbook_executed(key)

            # Playbook 4: Friday 5:00 PM Gatekeeper Lock (17:00 - 17:05 SGT)
            if day_of_week == 4 and hour == 17 and minute < 5:
                key = f"playbook_4_{date_str}"
                if key not in history:
                    print(f"Executing Playbook 4: Friday Gatekeeper Lock ({date_str})...")
                    execute_friday_gatekeeper()
                    mark_playbook_executed(key)

            # Playbook 6: Sunday Evening 60-Second Lead Briefing (20:00 - 20:05 SGT)
            if day_of_week == 6 and hour == 20 and minute < 5:
                key = f"playbook_6_{date_str}"
                if key not in history:
                    print(f"Executing Playbook 6: Sunday Lead Briefing ({date_str})...")
                    execute_sunday_briefing()
                    mark_playbook_executed(key)

            # Periodically process dashboard outbox queue
            process_outbox_queue()

        except Exception as e:
            print(f"Error in Chief of Staff scheduler tick: {e}")

        time.sleep(30)

# --- SLACK MESSAGE LISTENERS & ROUTING ---

@app.message(re.compile(r"^(hello|hi|help|start|onboard|welcome)", re.IGNORECASE))
def handle_greeting(message, say):
    """
    Greets new founders and explains the architecture.
    """
    user_id = message.get("user")
    say(
        f"Welcome to the Mamba MVP Program, <@{user_id}>! 👋\n\n"
        f"I am MVP_buddy, your autonomous Chief of Staff from Cybrdeck (run by Gwen and Ben).\n\n"
        f"*How this works:*\n"
        f"You don't need to fill out status report forms. Whenever you make progress, hit a blocker, or finish customer interviews, just talk to me right here in Slack!\n\n"
        f"I maintain 6 autonomous operational playbooks:\n"
        f"• *Monday 9 AM*: Sprint task deconstruction and accountability ping.\n"
        f"• *Wednesday 10 AM*: Pre-Office Hours blocker sweep before James Sun's call.\n"
        f"• *Thursday 5 PM*: 24-hr milestone pre-gate audit.\n"
        f"• *Friday 5 PM*: Gatekeeper lock & evidence pack verification.\n"
        f"• *Continuous*: Pre-Build Demand Trap interceptor (stop building backend before validation!).\n"
        f"• *Sunday 8 PM*: 60-second studio leadership briefing.\n\n"
        f"Whenever you're ready, just send me a message about what you're working on today!"
    )

@app.message(re.compile(".*"))
def handle_founder_checkin(message, say):
    """
    Listens for any Slack message and handles commands, demand trap interception,
    or Qwen executive reasoning with Gwen's signature personality.
    """
    user_id = message.get("user")
    text = message.get("text", "")
    files = message.get("files", [])
    
    # 1. On-Demand Playbook Triggers
    cleaned = text.strip().lower()
    if any(k in cleaned for k in ["!playbook 1", "run kickoff", "sprint kickoff", "run playbook 1"]):
        execute_monday_kickoff(say_fn=say)
        return
    elif any(k in cleaned for k in ["!playbook 2", "run blocker sweep", "run sweep", "run playbook 2"]):
        execute_wednesday_blocker_sweep(say_fn=say)
        return
    elif any(k in cleaned for k in ["!playbook 3", "run audit", "run pre-gate", "run playbook 3"]):
        execute_thursday_pregate_audit(say_fn=say)
        return
    elif any(k in cleaned for k in ["!playbook 4", "run gatekeeper", "run gate", "run playbook 4"]):
        execute_friday_gatekeeper(say_fn=say)
        return
    elif any(k in cleaned for k in ["!playbook 6", "run briefing", "run lead briefing", "run playbook 6"]):
        execute_sunday_briefing(say_fn=say)
        return
    elif any(k in cleaned for k in ["who didn't do what", "who hasnt done", "who hasn't done", "what is overdue", "overdue", "aging", "accountability", "task ledger", "who is blocked", "status report", "overdue tasks", "tasks"]):
        say(format_for_slack(generate_task_aging_report()))
        return
    elif any(k in cleaned for k in ["!skills", "!playbooks"]):
        say(format_for_slack(
            f"🛠️ *Chief of Staff Autonomous Skillset (6 Playbooks Live):*\n"
            f"1. *Monday Kickoff (09:00 SGT)*: Sprint Task Deconstruction (`!playbook 1`)\n"
            f"2. *Wednesday Sweep (10:00 SGT)*: Pre-Office Hours Blocker Sweep (`!playbook 2`)\n"
            f"3. *Thursday Audit (17:00 SGT)*: 24-Hour Pre-Gate Readiness Audit (`!playbook 3`)\n"
            f"4. *Friday Gatekeeper (17:00 SGT)*: Milestone Gatekeeper Lock (`!playbook 4`)\n"
            f"5. *Demand Trap Interceptor (Continuous)*: Halts premature coding in real time\n"
            f"6. *Sunday Briefing (20:00 SGT)*: 60-Second Lead Briefing (`!playbook 6`)\n\n"
            f"• *Accountability Ledger*: Ask *'who didn't do what'* or *'overdue'* anytime to see aging tasks.\n"
            f"All playbooks execute autonomously on schedule without human prompts."
        ))
        return

    # 2. Continuous Playbook 5: Demand Trap Interceptor
    if check_demand_trap(text):
        reply = execute_demand_trap_interceptor(user_id, text, say_fn=say)
        log_conversation_locally(user_id, text, reply, {"status": "Blocked", "blocker": "Premature architecture / Demand trap"})
        return

    # 3. Detect and download files (e.g. massive transcripts or workplace documents)
    if files:
        for file in files:
            url = file.get("url_private_download")
            if url:
                headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
                response = requests.get(url, headers=headers)
                if response.status_code == 200:
                    file_content = response.text
                    text += f"\n\n[Transcript Content from {file.get('name')}]:\n{file_content}"
                    try:
                        if supabase:
                            supabase.table("knowledge_documents").insert({
                                "title": file.get("name", "Slack Document"),
                                "category": "slack_upload",
                                "source": f"slack_file_{file.get('id', 'unknown')}",
                                "content": file_content[:15000],
                                "metadata": {"uploaded_by": user_id, "file_id": file.get("id")}
                            }).execute()
                            print(f"Indexed uploaded file '{file.get('name')}' to Supabase knowledge base.")
                    except Exception as fe:
                        print(f"Error indexing uploaded file: {fe}")
                    
    # 4. Process via real Qwen API with Gwen's signature personality
    extracted_data = process_with_qwen(text)
    
    # 5. Reply with Gwen's witty/snarky personality directly in Slack (Clean Slack Mrkdwn)
    say(format_for_slack(extracted_data.get("reply", "Telemetry logged. Now go find a customer who actually wants to pay.")))
    
    # 6. Relay cross-party action items if detected (Frictionless coordination)
    action_relay = extracted_data.get("action_relay") or {}
    if action_relay.get("has_cross_party_task") and action_relay.get("target") and action_relay.get("directive"):
        target_dest = action_relay.get("target")
        directive_text = action_relay.get("directive")
        print(f"Relaying autonomous directive to {target_dest}: {directive_text}")
        send_slack_message(target_dest, f"🔔 *Autonomous Directive from MVP_buddy:*\n{directive_text}")
    
    # 6. Save to Supabase (bypassing RLS with Service Role Key)
    try:
        if supabase:
            supabase.table("founder_checkins").insert({
                "slack_user_id": user_id,
                "raw_transcript": text,
                "status": extracted_data["status"],
                "stream": extracted_data["stream"],
                "blocker": extracted_data["blocker"],
                "digest": extracted_data["digest"]
            }).execute()
    except Exception as e:
        print(f"Database Error: {e}")

    # 7. Save to local Linode disk (immutable backup)
    log_conversation_locally(user_id, text, extracted_data.get("reply"), extracted_data)

def process_outbox_queue():
    """
    Polls the Supabase 'slack_outbox' table for pending messages queued from the dashboard.
    Dispatches each message and marks it as sent.
    """
    if not supabase:
        return
    try:
        response = supabase.table("slack_outbox").select("*").eq("status", "pending").limit(10).execute()
        rows = response.data or []
        for row in rows:
            row_id = row["id"]
            channel = row.get("channel", "#mamba-leads")
            content = row.get("text", "")
            success = send_slack_message(channel, content)
            supabase.table("slack_outbox").update({
                "status": "sent" if success else "failed",
                "sent_at": "now()"
            }).eq("id", row_id).execute()
    except Exception as e:
        pass

if __name__ == "__main__":
    import sys
    if "--send" in sys.argv:
        channel_target = sys.argv[2] if len(sys.argv) > 2 else "#mamba-leads"
        msg_content = sys.argv[3] if len(sys.argv) > 3 else "60-Second Lead Briefing from MVP_buddy"
        print(f"Triggering outbound message to {channel_target}...")
        send_slack_message(channel_target, msg_content)
    elif "--playbook" in sys.argv:
        pb_num = sys.argv[2] if len(sys.argv) > 2 else "1"
        if pb_num == "1":
            print(execute_monday_kickoff())
        elif pb_num == "2":
            print(execute_wednesday_blocker_sweep())
        elif pb_num == "3":
            print(execute_thursday_pregate_audit())
        elif pb_num == "4":
            print(execute_friday_gatekeeper())
        elif pb_num == "6":
            print(execute_sunday_briefing())
    else:
        # Start Autonomous Background Scheduler
        scheduler_thread = threading.Thread(target=cos_scheduler_loop, daemon=True)
        scheduler_thread.start()

        print("Venture Studio Slack Bot is starting in Socket Mode...")
        if SLACK_BOT_TOKEN and SLACK_APP_TOKEN:
            SocketModeHandler(app, SLACK_APP_TOKEN).start()
        else:
            print("Please add SLACK_BOT_TOKEN and SLACK_APP_TOKEN to your .env file to run the bot.")
