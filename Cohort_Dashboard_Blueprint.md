# Venture Studio: Cohort Pulse & Deliverables Command Center

## 1. System Architecture
- **Frontend Dashboard (Lovable/v0):** A read-only, dark-mode command center for internal team members (Ben, James, Gwen) to track cohort progress without data-entry friction.
- **Data Input (Slack Bot):** Founders submit progress via async Slack text or voice notes. No clicking around forms.
- **AI Extraction (Gemini 2.5 Flash):** AI parses the raw Slack messages into structured JSON (Status, Workstream, Blockers) and saves it to the database.
- **Triage Alerts:** Automatically routes blockers to the correct Slack channels (`#cohort-tech` -> Ben, `#cohort-gtm` -> James, `#cohort-activation` -> Gwen).

## 2. Dashboard UI/UX
- **Theme:** Slate/Zinc dark mode (`#09090b`), high contrast, utilitarian.
- **Components:**
  - Header & Health Bar (velocity, blockers).
  - Blocker Triage Strip (highlighting teams needing immediate help).
  - Cohort Deliverable Matrix (Interactive Table).
  - Slide-Over Drawer (historical timeline, raw Slack check-in log, internal notes).
  - Stream Filter Tabs.

## 3. The Shadow Architecture (Your Stealth IP)
Do not build the autonomous agents for the client yet, but lay the data rails now:
- **Standardized JSON Schema:** Store `founder_intent`, `target_audience`, `current_hypothesis`, `blocker_category`.
- **Context Breadcrumbs:** Save the raw founder voice transcripts into a `context_history` table. This becomes the prompt context for future agents.
- **Decoupled Trigger Points:** Use event emitters (e.g., `emit("deliverable_updated", data)`) when saving to the dashboard. Later, you can hook background worker agents into these events to autonomously generate deliverables (decks, code, market research).

## 4. Next Steps
- Define the exact Supabase/Database schema for the JSON payloads.
- Set up the Python Slack Bot (Slack Bolt + Gemini) to ingest messages/voice notes.
- Feed the Lovable prompt to generate the read-only React dashboard.
