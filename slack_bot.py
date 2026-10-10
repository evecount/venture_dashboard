import os
import json
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from supabase import create_client, Client
import requests

# Load environment variables
load_dotenv()

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN")
SUPABASE_URL = os.environ.get("VITE_SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
SPEECHMATICS_API_KEY = os.environ.get("SPEECHMATICS_API_KEY")

if not all([SLACK_BOT_TOKEN, SLACK_APP_TOKEN, SUPABASE_URL, SUPABASE_KEY, SPEECHMATICS_API_KEY]):
    print("Missing API Keys! Please ensure SLACK_BOT_TOKEN and SLACK_APP_TOKEN are set in .env")

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

def process_with_speechmatics(text):
    """
    Simulated Speechmatics Logic API Call.
    Injects the CYBRDECK_SYSTEM_PROMPT and parses the user's text to return structured insights.
    """
    print(f"Sending context to Speechmatics Logic Engine: {CYBRDECK_SYSTEM_PROMPT[:50]}...")
    
    text_lower = text.lower()
    
    # Dynamic LLM intent matching simulation
    if "stuck" in text_lower or "block" in text_lower:
        status = "Blocked"
        blocker = "Founder flagged a technical or validation block."
    else:
        status = "In progress"
        blocker = "None for now."
        
    if "code" in text_lower or "app" in text_lower or "backend" in text_lower:
        stream = "Tech (Cybrdeck)"
        digest = f"Cybrdeck Review: {text[:60]}... Reminder: Validate manually before Gwen/Ben write code."
    else:
        stream = "GTM"
        digest = f"Progress update: {text[:60]}..."

    return {
        "status": status,
        "stream": stream,
        "progress": 50, # In a real LLM call, we'd extract a percentage
        "digest": digest,
        "blocker": blocker
    }

import re

@app.message(re.compile(".*"))
def handle_founder_checkin(message, say):
    """
    Listens for any Slack message.
    """
    user_id = message.get("user")
    text = message.get("text", "")
    
    say(f"Received your check-in, <@{user_id}>! Running it through the Studio AI...")
    
    # 1. Process via Speechmatics API
    extracted_data = process_with_speechmatics(text)
    
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
