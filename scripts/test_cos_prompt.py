import sys, os
sys.path.append(os.path.abspath("."))
from slack_bot import qwen_client, CYBRDECK_SYSTEM_PROMPT, query_supabase_knowledge
import json

text = "Break down Matthew's tasks for this sprint into an actionable checklist and draft the accountability ping for him."
knowledge = query_supabase_knowledge(text)

prompt = f"""
{CYBRDECK_SYSTEM_PROMPT}

{knowledge}

You are reading a message from leadership (Gwen, Ben, or James) or a founder.
Analyze the request and output EXACTLY this JSON structure:
{{
  "status": "In progress",
  "stream": "Tech (Cybrdeck)",
  "blocker": "None",
  "digest": "Chief of Staff action item summary",
  "reply": "Your executive response as Chief of Staff. CRITICAL RULE: If asked to break down tasks, draft messages, or create plans, DO NOT just give commentary or tell the user to do it. ACTUALLY EXECUTE: output the complete, numbered task checklist with clear deliverables, and write out the exact draft message ready to send. Keep Gwen's sharp, high-agency, zero-fluff tone."
}}

Request:
{text}
"""

resp = qwen_client.chat.completions.create(
    model="qwen-max",
    messages=[
        {"role": "system", "content": "You are a JSON-only API. Only output valid JSON."},
        {"role": "user", "content": prompt}
    ],
    response_format={"type": "json_object"}
)
res = json.loads(resp.choices[0].message.content)
print("--- CHIEF OF STAFF OUTPUT ---")
print(res["reply"])
