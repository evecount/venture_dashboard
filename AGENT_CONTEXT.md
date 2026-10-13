# AGENT CONTEXT & DEVELOPER HANDOVER MANUAL
**Venture Studio OS (VentureDash) · Zero-Click Operations Command Center**

> **Target Audience:** Any AI agent (Claude, Gemini, GPT, Cursor, Lovable) or human engineer picking up this codebase. Read this document before making architectural changes or refactoring existing code.

---

## 1. Executive Summary & North Star

### The Problem
Traditional venture accelerators, studios, and incubation programs force busy founders to fill out weekly status reports in Jira, Asana, Airtable, or rigid Notion templates. This creates massive administrative friction. Founders either submit half-baked reports late or drop off entirely, forcing venture leads to waste hours chasing status updates.

### The Solution: Zero-Click Ambient Operations
**Venture Studio OS** eliminates founder-side forms and clicking.
Founders work where they already communicate: **Slack (text, DMs, threads, and voice note transcripts)**.
The dashboard is a **Read-Only Live Control Ledger** for Studio Leads (Program Coordinators, GTM Advisors, Technical Leads) and Founders.

```
Founder speaks in Slack ──► Autonomous AI Bot ──► Interactive Card Confirmation
                                                              │
                                                              ▼
Living Dashboard ◄── WebSockets / PubSub ◄── Supabase Realtime Ledger
        │
        └──► Background Cron Worker ──► Proactive Slack Nudges (T-48h, Blocked >48h)
```

---

## 2. The 4-Stage Operating Pipeline

Every feature in this repository belongs to one of four pipeline layers. Do not break the boundaries between these layers:

### Layer 1: Ingestion & Identity Resolution ([slack_bot.py](file:///c:/Users/SIT%20EUC/Documents/Builds/VentureDash/slack_bot.py))
- Ingests text, file attachments, and voice note transcripts via Slack Socket Mode (`@slack/bolt`).
- **Identity Resolution**: Maps the raw `slack_user_id` (e.g. `U05ABCD`) to their startup record in `founders` ➔ `startups`.
- **Milestone Grounding**: Looks up the current sprint week and target deliverable from the 12-week syllabus (`src/data/syllabus.json` or Supabase `deliverables`).

### Layer 2: Syllabus-Grounded AI Extraction
- Passes the unstructured text and active milestone to an LLM (Qwen / OpenAI-compatible endpoint).
- Strict JSON Schema output:
  ```json
  {
    "status": "In progress" | "Blocked" | "On Track" | "Completed",
    "progress": 0 to 100,
    "stream": "Tech" | "GTM",
    "blocker": "1-sentence blocker description or 'None'",
    "digest": "1-2 sentence executive summary for mentors"
  }
  ```

### Layer 3: The Interactive Feedback Loop (Block Kit Confirmation)
- **Zero Silent Writes**: The bot **never** writes unverified AI extractions directly to the database.
- It responds in Slack with an interactive **Block Kit card**:
  - Displays: Target deliverable, extracted status, workstream, blocker flag, and summary.
  - Interactive Buttons: `[ ✅ Confirm & Sync Dashboard ]` (`action_id: confirm_checkin`) and `[ ✏️ Adjust Details ]` (`action_id: edit_checkin`).
- Only when the founder clicks **Confirm** is the mutation committed to the database. This guarantees founder ownership and eliminates AI hallucinations.

### Layer 4: Real-Time Replication & Proactive Chasing
- **Living Dashboard**: Supabase Realtime broadcast (`postgres_changes`) pushes mutations to the frontend via WebSockets. The dashboard updates instantaneously with a pulsing glow—**requiring zero page reloads or clicks**.
- **Proactive Nudge Engine**: A background cron worker (`APScheduler`) audits deadlines every morning at 09:00 SGT:
  - If a deliverable is due in <48 hours without a submission ➔ alerts the team channel.
  - If a status remains "Blocked" for >48 hours ➔ sends a proactive DM to the founder offering an unblocking sync with their stream lead.

---

## 3. Repository Architecture & File Index

| Path | Purpose & Responsibilities |
|---|---|
| [`slack_bot.py`](file:///c:/Users/SIT%20EUC/Documents/Builds/VentureDash/slack_bot.py) | Python Slack Bolt app (Socket Mode). Handles message ingestion, entity lookup, Qwen LLM parsing, Block Kit confirmation cards, and the background 48h blocker scheduler. Supports offline dry-run testing via `--simulate`. |
| [`supabase/schema.sql`](file:///c:/Users/SIT%20EUC/Documents/Builds/VentureDash/supabase/schema.sql) | Production PostgreSQL schema. Tables: `cohorts`, `startups`, `founders`, `deliverables`, `submissions`, `signals`. Configures Row-Level Security (RLS) and `supabase_realtime` publication. |
| [`supabase/README.md`](file:///c:/Users/SIT%20EUC/Documents/Builds/VentureDash/supabase/README.md) | Step-by-step setup guide for creating the Slack App manifest, granting bot scopes, and deploying the Supabase schema. |
| [`src/components/dashboard/command-center.tsx`](file:///c:/Users/SIT%20EUC/Documents/Builds/VentureDash/src/components/dashboard/command-center.tsx) | The primary command center UI. Contains dynamic KPIs (velocity, active blockers, response rates), Blocker Triage Strip, Cohort Matrix Table, Live Signal Ticker, and the `[⚡ Simulate Slack Inbound]` ambient test trigger. |
| [`src/components/dashboard/data.ts`](file:///c:/Users/SIT%20EUC/Documents/Builds/VentureDash/src/components/dashboard/data.ts) | Privacy-compliant synthetic fixtures (`demo-founder-01`, `demo-founder-02`) and studio role models (`coordinator`, `gtm`, `marketing`, `technical`). |
| [`src/components/dashboard/studio-perspectives.tsx`](file:///c:/Users/SIT%20EUC/Documents/Builds/VentureDash/src/components/dashboard/studio-perspectives.tsx) | Dropdown switcher allowing operators to toggle between Studio Mentor views and personalized Founder Views. |
| [`src/components/dashboard/ai-chat-overlay.tsx`](file:///c:/Users/SIT%20EUC/Documents/Builds/VentureDash/src/components/dashboard/ai-chat-overlay.tsx) | Modal AI Assistant providing in-browser simulation of the Slack conversational check-in and Block Kit confirmation loop. |
| [`src/data/syllabus.json`](file:///c:/Users/SIT%20EUC/Documents/Builds/VentureDash/src/data/syllabus.json) | Structured 12-week Mamba MVP schedule extracted from the official syllabus spreadsheet. Contains dates, modules, daily exercises, leads, and Friday deliverables. |
| [`src/routes/__root.tsx`](file:///c:/Users/SIT%20EUC/Documents/Builds/VentureDash/src/routes/__root.tsx) | TanStack Start root shell. Contains the prototype access gate (`passcode: mamba2026`). |
| [`src/test/demo-privacy.test.ts`](file:///c:/Users/SIT%20EUC/Documents/Builds/VentureDash/src/test/demo-privacy.test.ts) | Privacy compliance test verifying that no real identities or sensitive names are exposed by default fixtures. |

---

## 4. Hard Constraints & Invariants (DO NOT VIOLATE)

### Rule 1: Lovable Synchronization
This repository syncs with [Lovable](https://lovable.dev). 
- **NEVER** force-push, rebase, or squash published commits on the connected branch. Doing so destroys commit history on Lovable's side.
- Keep the connected branch in a clean, buildable state at all times.

### Rule 2: Prototype Privacy & Fixture Conventions
`src/test/demo-privacy.test.ts` runs on CI and enforces strict sanitization rules:
- Founder IDs must match `^demo-founder-` (e.g. `demo-founder-01`).
- Founder names must match `^Demo Founder ` (e.g. `Demo Founder A`).
- Founder profiles must contain the word `fictional`.
- Notes must start with `Demo `.
- Studio roles must strictly match: `Program Coordinator`, `GTM Venture Advisor`, `Marketing / Rollout / User Validation`, and `Technical Advisor`.
- **FORBIDDEN STRINGS**: Do not hardcode real partner or founder names in `data.ts` or UI templates. The regex `/benjamin|\bben\b|arthur|james|gwen|logistics|enterprise studio|supabase auth|auth loop/i` will fail tests if present in the data modules.

### Rule 3: Browser-Safe Simulation with Clear Labels
Per [AGENTS.md](file:///c:/Users/SIT%20EUC/Documents/Builds/VentureDash/AGENTS.md):
- Keep the dashboard runnable in a browser-safe mode without requiring active Supabase credentials to view.
- When displaying simulated data, ensure the UI clearly carries the `"Slack simulation · Not connected"` indicator.
- Do not remove the `[⚡ Simulate Slack Inbound (Zero-Click)]` trigger—it is essential for prospective partners and studio leads to see how live updates work without setting up Slack tokens.

### Rule 4: Presentation-Only Perspectives
Perspective switching (e.g. switching between Program Coordinator and Demo Founder A) is a **presentation modeling tool**, not an authentication or authorization barrier. Do not introduce rigid auth guards that break the perspective preview dropdown.

---

## 5. Development & Testing Commands

```bash
# 1. Run Vitest Unit & Privacy Tests
npm test

# 2. Build Client & SSR Bundle (Vite + Nitro)
npm run build

# 3. Start Local Frontend Dev Server
npm run dev
# Default port: http://localhost:3000 (or Vite allocated port)
# Access Code: mamba2026

# 4. Test Slack Bot Extraction in Offline Dry-Run Mode
python slack_bot.py --simulate

# 5. Run Live Slack Bot (Requires .env tokens)
python slack_bot.py
```

---

## 6. How the Realtime Pub/Sub Connects to the Frontend

When migrating the frontend from the simulated state to live Supabase:

1. Add `@supabase/supabase-js` to `package.json`.
2. Set `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` in `.env`.
3. Subscribe to the `submissions` and `signals` tables:
   ```ts
   import { createClient } from "@supabase/supabase-js";
   
   const supabase = createClient(import.meta.env.VITE_SUPABASE_URL, import.meta.env.VITE_SUPABASE_ANON_KEY);
   
   supabase
     .channel("cohort-live")
     .on("postgres_changes", { event: "INSERT", schema: "public", table: "signals" }, (payload) => {
       // Prepend to recentSignals state
     })
     .on("postgres_changes", { event: "*", schema: "public", table: "submissions" }, (payload) => {
       // Update founderList state and trigger isPulsing: true
     })
     .subscribe();
   ```

---

## 7. High-Value Roadmap Items for Future Agents

If you are tasked with extending Venture Studio OS, prioritize these high-leverage features:

1. **Slack App Home Tab (`views.publish`)**:
   Render the founder's personal sprint radar directly inside Slack's Home tab when they open the bot's DM. This solves the "dead tab" problem completely.
2. **Ambient TV / Kiosk Display Mode**:
   Add a full-screen toggle button (`F11` / kiosk layout) that strips navigation rails and optimizes typography for wall-mounted 55" office/incubator monitors.
3. **Voice Audio Transcription Bridge**:
   Connect Telegram voice messages or Slack `.m4a`/`.mp3` voice note audio attachments to OpenAI Whisper / Alibaba DashScope Paraformer to transcribe spoken voice memos before feeding them to Qwen.
4. **Automated Monday Standup Digest**:
   Create a scheduled job sending a concise Block Kit card every Monday at 09:00 into `#general` summarizing cohort velocity and unresolved blockers.
