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

# --- SYSTEM PROMPT & RESOURCES ---
# The bot's identity and knowledge base. 
# We strictly exclude Takshma and Matthew to protect public IP.
CYBRDECK_SYSTEM_PROMPT = """
You are MVP_buddy, the primary technical architecture and engineering mentor for Cybrdeck.
Cybrdeck (Eve Count Pte. Ltd.) is the technical execution arm of the Mamba MVP Program.
Your creators and engineering leads are Gwen Lim and Ben Lim. 
Your role is to enforce the 'Wizard of Oz' (WoZ) methodology — ensuring founders manually validate customer demand BEFORE Cybrdeck writes any custom backend code. You protect Cybrdeck's engineering hours and ensure clean IP boundaries.
"""

def process_with_qwen(text):
    """
    Real API Call to Qwen (via OpenAI compatible endpoint).
    Injects the CYBRDECK_SYSTEM_PROMPT and parses the user's text/transcript.
    """
    if not qwen_client:
        print("No QWEN_API_KEY found, falling back to simulated logic...")
        return {
            "status": "In progress",
            "stream": "Tech (Cybrdeck)",
            "progress": 50,
            "digest": f"Simulated digest (No API Key): {text[:60]}...",
            "blocker": "Missing Qwen API Key."
        }
        
    print(f"Sending context to Qwen LLM...")
    
    prompt = f"""
    {CYBRDECK_SYSTEM_PROMPT}
    
    You are reading a message or transcript from a founder. Analyze the text and output EXACTLY this JSON structure, and nothing else:
    {{
      "status": "Blocked" or "In progress" or "Complete",
      "stream": "Tech (Cybrdeck)" or "GTM",
      "blocker": "A short 1-sentence description of what they are stuck on (or 'None')",
      "digest": "A 1-sentence summary of their progress and what the human mentors should do next"
    }}
    
    Founder Transcript:
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
            "blocker": result.get("blocker", "None")
        }
    except Exception as e:
        print(f"Qwen API error: {e}")
        return {
            "status": "In progress",
            "stream": "Tech (Cybrdeck)",
            "progress": 50,
            "digest": f"Error parsing with Qwen: {str(e)}",
            "blocker": "API Error"
        }

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
        f"I will use AI to extract the context, identify your blockers, and automatically update your progress on the Venture Dashboard so the human mentors (James, Gwen, Ben) know exactly where you are.\n\n"
        f"Whenever you're ready, just send me a message about what you're working on today!"
    )

@app.message(re.compile(".*"))
def handle_founder_checkin(message, say):
    """
    Listens for any Slack message.
    """
    user_id = message.get("user")
    text = message.get("text", "")
    files = message.get("files", [])
    
    say(f"Received your check-in, <@{user_id}>! Running it through the Studio AI...")
    
    # Detect and download files (e.g. massive transcripts)
    if files:
        say(f"Detected {len(files)} file attachment(s). Reading transcript data...")
        for file in files:
            url = file.get("url_private_download")
            if url:
                headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
                response = requests.get(url, headers=headers)
                if response.status_code == 200:
                    text += f"\n\n[Transcript Content from {file.get('name')}]:\n{response.text}"
                else:
                    say(f"Failed to download {file.get('name')}.")
                    
    # 1. Process via real Qwen API
    extracted_data = process_with_qwen(text)
    
    # 2. Save to Supabase (bypassing RLS with Service Role Key)
    try:
        if supabase:
            # Note: You'll need to create a 'founder_checkins' table in Supabase
            supabase.table("founder_checkins").insert({
                "slack_user_id": user_id,
                "raw_transcript": text,
                "status": extracted_data["status"],
                "stream": extracted_data["stream"],
                "blocker": extracted_data["blocker"],
                "digest": extracted_data["digest"]
            }).execute()
            say("Check-in parsed and saved to the Venture Dashboard! 🚀")
        else:
            say("Warning: Database not connected.")
    except Exception as e:
        say(f"Oops, failed to save to database: {str(e)}")
        print(f"Database Error: {e}")

if __name__ == "__main__":
    print("Venture Studio Slack Bot is starting in Socket Mode...")
    if SLACK_BOT_TOKEN and SLACK_APP_TOKEN:
        SocketModeHandler(app, SLACK_APP_TOKEN).start()
    else:
        print("Please add SLACK_BOT_TOKEN and SLACK_APP_TOKEN to your .env file to run the bot.")
