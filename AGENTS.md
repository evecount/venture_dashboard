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

## AI Agent Orientation

> **CRITICAL:** Read [AGENT_CONTEXT.md](./AGENT_CONTEXT.md) before making structural changes. It has the architecture, file map, data model, hard rules and deploy steps.

### Core principles
- **Slack first, zero forms.** Founders talk to Venture Buddy (`slack_bot.py`, `bot_agent.py`). The dashboard is a read-only live view of the same data.
- **Live data only.** No simulation, demo fixtures or fictional placeholders in the dashboard or the database (`npm test` checks the UI source).
- **Roles come from the database,** never the LLM; tools are role-gated and arguments are re-validated in code.
- **Proposals before outward actions** (check-ins, renames, meeting invitations): show a card, act only on the requester's confirm.
- **Secrets never in git.** `.env`, `*.pem`, tokens and the service-role key stay local or on the VM. Sensitive tables use RLS with no public policies.
- **Presentation-only perspectives.** Dashboard "view as" switching is not authorization.

### Working in this repo with other agents
- Another agent edits the dashboard in this same folder. Commit only your own files (no `git add -A`), `git pull` before pushing, re-read a file before editing it, and tell the user before deploying (a deploy builds the whole working tree).
- Schema changes are SQL files in `supabase/migrations/`; the user runs them. Code must degrade gracefully if a table is missing.
- Run only one copy of the bot (the VM). Do not start it locally while the VM is running.

### Quick commands
- `npm test` : Vitest (site, dashboard logic, webhook signing). Must pass before committing.
- `python -m unittest discover tests` : bot tests (agent rules, profiles, integrations, meetings, daily prompts).
- `npm run build` : client + SSR bundle.
- `python slack_bot.py --simulate` : offline dry run of extraction and cards.
