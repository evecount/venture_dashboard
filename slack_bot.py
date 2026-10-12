import os
import json
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from supabase import create_client, Client
import requests
from openai import OpenAI

# Load environment variables
load_dotenv()

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN")
SUPABASE_URL = os.environ.get("VITE_SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
QWEN_API_KEY = os.environ.get("QWEN_API_KEY")

qwen_client = OpenAI(
    api_key=QWEN_API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
) if QWEN_API_KEY else None

if not all([SLACK_BOT_TOKEN, SLACK_APP_TOKEN, SUPABASE_URL, SUPABASE_KEY, QWEN_API_KEY]):
    print("Missing API Keys! Please ensure SLACK_BOT_TOKEN, SLACK_APP_TOKEN and QWEN_API_KEY are set in .env")

# Initialize Supabase Admin Client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# Initialize Slack App
app = App(token=SLACK_BOT_TOKEN)

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
You are MVP_buddy, the autonomous technical architecture mentor AI for Cybrdeck (Eve Count Pte. Ltd.), created by Gwen Lim and Ben Lim for the Mamba MVP Program.
You carry Gwen Lim's exact personality: razor-sharp, slightly snarky, witty, high-agency, and completely allergic to corporate fluff or founder excuses.
You despise vanity metrics, over-engineered architectures, and building before validating customer demand.
You enforce the Pre-Build Demand Validation Protocol with brutal honesty and dry wit.
When founders speak to you, never sound like a polite corporate chatbot. Be sharp, clever, sarcastic when appropriate, and deeply insightful.
If someone asks off-topic or philosophical questions (like "the meaning of life"), roast them affectionately with a venture twist (e.g. "The meaning of life is finding customers who will actually pay before you burn Gwen and Ben's engineering hours on a backend you don't need.").

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
    Injects the CYBRDECK_SYSTEM_PROMPT, Supabase workplace documents, and generates structured data + a snarky reply.
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
    
    You are reading a message or transcript from a founder. Analyze the text and output EXACTLY this JSON structure, and nothing else:
    {{
      "status": "Blocked" or "In progress" or "Complete",
      "stream": "Tech (Cybrdeck)" or "GTM",
      "blocker": "A short 1-sentence description of what they are stuck on (or 'None')",
      "digest": "A 1-sentence summary of their progress and what the human mentors should do next",
      "reply": "A witty, slightly snarky, sharp 1-3 sentence response directly addressing what they just said, matching Gwen Lim's signature Cybrdeck personality."
    }}
    
    Founder Transcript / Message:
    {text}
    """
    
    try:
        response = qwen_client.chat.completions.create(
            model="qwen-plus",
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
            "reply": result.get("reply", "Telemetry logged. Now go talk to actual paying customers.")
        }
    except Exception as e:
        print(f"Qwen API error: {e}")
        cleaned_msg = text.strip()
        
        # Check if the query is asking about the schedule/deliverable
        schedule_reply = check_schedule_query(cleaned_msg)
        if schedule_reply:
            snarky_fallback = schedule_reply
        else:
            snarky_fallback = (
                f"Logged your check-in: \"{cleaned_msg}\". "
                "Telemetry is minted in the studio ledger. But tell me—are we talking to actual paying customers, "
                "or just hallucinating architectures at 1:48 AM? Go to sleep, Gwen."
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
    Deterministically parses questions regarding the Mamba MVP 12-week schedule
    and provides the exact deliverables, dates, and office hours.
    """
    q = query.lower()
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

import re

@app.message(re.compile(r"^(hello|hi|help|start|onboard|welcome)", re.IGNORECASE))
def handle_greeting(message, say):
    """
    Greets new founders and explains the architecture.
    """
    user_id = message.get("user")
    say(
        f"Welcome to the Mamba MVP Program, <@{user_id}>! 👋\n\n"
        f"I am MVP_buddy, your technical engineering mentor from Cybrdeck (run by Gwen and Ben).\n\n"
        f"*How this works:*\n"
        f"You don't need to fill out status report forms. Whenever you make progress, hit a blocker, or finish customer interviews, just talk to me right here in Slack! Send a voice note or type a message.\n\n"
        f"I will use AI to extract the context, identify your blockers, and automatically update your progress on the Venture Dashboard so the human team (James Sun [Program Lead], Gwen & Ben [Cybrdeck Tech], and Arthur [Project Coordinator]) knows exactly where you are.\n\n"
        f"Whenever you're ready, just send me a message about what you're working on today!"
    )

@app.message(re.compile(".*"))
def handle_founder_checkin(message, say):
    """
    Listens for any Slack message and responds with Gwen's signature snarky Cybrdeck personality.
    """
    user_id = message.get("user")
    text = message.get("text", "")
    files = message.get("files", [])
    
    # Detect and download files (e.g. massive transcripts or workplace documents)
    if files:
        for file in files:
            url = file.get("url_private_download")
            if url:
                headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
                response = requests.get(url, headers=headers)
                if response.status_code == 200:
                    file_content = response.text
                    text += f"\n\n[Transcript Content from {file.get('name')}]:\n{file_content}"
                    # Automatically index into Supabase knowledge_documents
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
                    
    # 1. Process via real Qwen API with Gwen's signature personality
    extracted_data = process_with_qwen(text)
    
    # 2. Reply with Gwen's witty/snarky personality directly in Slack
    say(extracted_data.get("reply", "Telemetry logged. Now go find a customer who actually wants to pay."))
    
    # 3. Save to Supabase (bypassing RLS with Service Role Key)
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

# --- OUTBOUND DISPATCH (DASHBOARD -> SLACK) ---
def send_slack_message(channel: str, text: str, thread_ts: str = None) -> bool:
    """
    Sends an outbound message to a specified Slack channel or user DM.
    Can be called directly from Python or triggered by the dashboard outbox.
    """
    # Channel alias mapping
    if channel in ["gwen-ben", "gwen_ben", "@gwen_ben"]:
        # Dispatch to BOTH Gwen and Ben simultaneously!
        send_slack_message("D0C94PG2R24", text, thread_ts)
        send_slack_message("D0C74JVR813", text, thread_ts)
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
        print(f"[Simulated Slack Outbound to {target_channel}] Bot token not configured. Message: {text[:80]}...")
        return False
    try:
        kwargs = {"channel": target_channel, "text": text}
        if thread_ts:
            kwargs["thread_ts"] = thread_ts
        res = app.client.chat_postMessage(**kwargs)
        print(f"Message dispatched to Slack channel {target_channel}: {res.get('ts')}")
        return True
    except Exception as e:
        print(f"Error sending Slack message: {e}")
        return False

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
        print(f"Outbox queue error: {e}")

if __name__ == "__main__":
    import sys
    if "--send" in sys.argv:
        # Example CLI usage: python slack_bot.py --send "#mamba-leads" "Hello from dashboard!"
        channel_target = sys.argv[2] if len(sys.argv) > 2 else "#mamba-leads"
        msg_content = sys.argv[3] if len(sys.argv) > 3 else "60-Second Lead Briefing from MVP_buddy"
        print(f"Triggering outbound message to {channel_target}...")
        send_slack_message(channel_target, msg_content)
    else:
        print("Venture Studio Slack Bot is starting in Socket Mode...")
        if SLACK_BOT_TOKEN and SLACK_APP_TOKEN:
            SocketModeHandler(app, SLACK_APP_TOKEN).start()
        else:
            print("Please add SLACK_BOT_TOKEN and SLACK_APP_TOKEN to your .env file to run the bot.")

