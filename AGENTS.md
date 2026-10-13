<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.
<!-- LOVABLE:END -->

## 🤖 AI Agent Orientation & Architecture Guidelines

> **CRITICAL:** Before making structural changes, read [AGENT_CONTEXT.md](./AGENT_CONTEXT.md) for the complete 4-stage pipeline, file index, and development invariants.

### Core Principles
- **Zero-Click Operations**: Founders do NOT fill out forms or click around Jira/Notion. They talk to the Slack bot (`@MVP_buddy` in `slack_bot.py`). The React dashboard is a read-only live control ledger.
- **The 4-Stage Loop**: Slack Inbound ➔ Identity & Milestone Resolution ➔ Structured LLM Extraction ➔ Slack Block Kit Interactive Confirmation Card (`[Confirm]` button) ➔ Supabase Realtime DB ➔ Zero-Click Dashboard & 48h Blocker Cron Scheduler.
- **Privacy & Fixture Invariants**: Keep dashboard demo records in a browser-safe data module (`src/components/dashboard/data.ts`) with IDs matching `demo-founder-` and names matching `Demo Founder A/B`. Never leak real personal names into demo fixtures (verified by `npm test`).
- **Clear Simulation Labeling**: Keep this command center frontend-only and browser-runnable by default; label simulated connection and data clearly with the `"Slack simulation · Not connected"` badge.
- **Presentation-Only Perspectives**: Model studio responsibilities (`coordinator`, `gtm`, `marketing`, `technical`) and demo perspectives (`demo-founder-01`, `demo-founder-02`) in browser-safe fixtures; perspective switching is presentation only, never an authorization mechanism.

### Quick Commands for Agents
- `npm test` : Runs Vitest unit and privacy tests. (Must pass before committing).
- `npm run build` : Builds client and SSR Nitro bundle.
- `python slack_bot.py --simulate` : Tests the Slack bot parsing and Block Kit card generation in offline dry-run mode.
