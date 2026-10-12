import os
import json
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.environ.get("VITE_SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Supabase credentials missing!")
    exit(1)

client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 1. Load Syllabus Data
syllabus_path = os.path.join(os.path.dirname(__file__), "..", "src", "data", "syllabus.json")
with open(syllabus_path, "r", encoding="utf-8") as f:
    syllabus_raw = json.load(f)

schedule_items = syllabus_raw.get("Mamba_MVP_Official_Syllabus_Sch", [])

# Build documents to insert
docs = []

# Doc 1: The Official 12-Week Syllabus
sprint_summary = []
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
        sprint_summary.append(f"\n### {week}: {phase}")
    line = f"- {day} ({date_str}): {module} [Lead: {owner}]"
    if deliverable:
        line += f" -> **FRIDAY DELIVERABLE: {deliverable}**"
    sprint_summary.append(line)

docs.append({
    "title": "Mamba MVP Official 12-Week Syllabus & Schedule",
    "category": "syllabus",
    "source": "Mamba_MVP_Official_Syllabus_Schedule (2).xlsx",
    "content": "\n".join(sprint_summary),
    "metadata": {
        "weeks": 12,
        "sprints": 6,
        "date_range": "2026-10-05 to 2026-12-25"
    }
})

# Doc 2: Cybrdeck Pre-Build Demand Validation Protocol
docs.append({
    "title": "Cybrdeck Pre-Build Demand Validation Protocol",
    "category": "methodology",
    "source": "cybrdeck_core",
    "content": """# Cybrdeck Pre-Build Demand Validation Protocol
1. Assumption Ranking: Before writing a single line of backend infrastructure or microservices, founders must rank their Top 10 critical venture assumptions.
2. Demand Signals: A valid customer demand signal is NOT a friend saying 'that sounds cool.' It is anLOI (Letter of Intent), pre-payment, deposit, or signed design partnership.
3. Protected Build Time: Deep work hours (5-7 hrs daily) are strictly reserved for rapid prototyping and user tests, NOT over-architecting premature databases.
4. Friday Milestone Gates: Deliverables are locked every Friday. Incomplete gates trigger mentor intervention with James Sun, Gwen Lim, and Ben Lim.
5. Office Hours Anchor: Wednesday Office Hours are mandatory for clearing blockers, adjusting technical scopes, and eliminating vanity metrics.""",
    "metadata": {"author": "Gwen Lim & Ben Lim", "version": "1.0"}
})

# Doc 3: Studio Team Directory & Roles
docs.append({
    "title": "Mamba MVP Studio Team & Mentor Directory",
    "category": "team",
    "source": "slack_workspace",
    "content": """# Studio Team Directory
- Gwen Lim (Cybrdeck Co-Founder, Tech & Product Lead): Direct Slack DM D0C94PG2R24. Enforces technical architecture discipline, rapid prototyping, and zero-fluff validation.
- Ben Lim (Cybrdeck Co-Founder, Systems & Engineering): Direct Slack DM D0C74JVR813. Cloud infrastructure, performance, and automation.
- James Sun (Mamba MVP Program Lead): Direct Slack DM D0C77UV5GT0. Venture milestones, commercial evaluation, and investment gates.
- Arthur Andre Pandaan (Project Coordinator): Direct Slack DM D0C8AC5G2SX. Program logistics, cohort coordination, scheduling, and submissions.
- MVP_buddy (@MVP_botprototype): Studio autonomous mentor AI running on Cybrdeck stack.""",
    "metadata": {"workspace": "Mamba MVP", "slack_team": "T0C74J99S69"}
})

print(f"Upserting {len(docs)} foundational documents into Supabase public.knowledge_documents...")

for doc in docs:
    # Delete existing doc with same title if present
    client.table("knowledge_documents").delete().eq("title", doc["title"]).execute()
    res = client.table("knowledge_documents").insert(doc).execute()
    print(f"Inserted: {doc['title']} (ID: {res.data[0]['id']})")

print("Seeding complete!")
