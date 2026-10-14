# AGENT CONTEXT & DEVELOPER HANDOVER MANUAL
**VentureOS (repo: `venture_dashboard`) · Slack-first progress tracking for a venture studio program**

> **Audience:** any AI agent or engineer picking up this codebase. Read this before changing architecture. Last revised 2026-10-14.

---

## 1. What this is

A progress tracker for a venture studio cohort. **Founders never fill in forms.** They talk to the Slack assistant (**Venture Buddy**), connect GitHub and Google Calendar once, and the system builds a live picture of each startup. **Mentors** see that picture in Slack (Home tab, cohort pulse) and on a read-only dashboard, and can ask the bot questions, leave notes, assign follow-ups, issue milestones and schedule meetings.

It is a lightweight CRM + product-management tool for a program: contact records (startups and people), an activity timeline, health status, tasks, notes and milestones.

```
Founder/Mentor in Slack ──► Venture Buddy (Python, Socket Mode, always on)
                              │  role comes from the DB, never from the LLM
                              │  tool-calling agent + persistent memory
                              ▼
                         Supabase (Postgres + Realtime)  ◄── Cloudflare Worker (site + webhooks)
                              ▲                                   ▲
   GitHub App webhooks ───────┘            Google Calendar / GitHub OAuth callbacks
   Google Calendar sync (hourly)
                              ▼
        Read-only dashboard (live data only) · Slack Home tabs (refresh every ~15s on change)
```

---

## 2. Hard rules (do not violate)

1. **Lovable sync.** The repo syncs with Lovable. Never force-push, rebase, amend or squash pushed commits. Keep `main` buildable.
2. **Live data only.** There is no simulation or demo data in the dashboard or the database. Do not reintroduce fixtures, "Simulate" buttons or fictional placeholders. `src/test/demo-privacy.test.ts` enforces this.
3. **Roles come from the database.** `get_role()` reads `mentors`/`founders`. The LLM never decides who someone is. Tool availability is gated by role in code, and tool arguments are re-validated server-side (a founder is pinned to their own startup).
4. **Proposals before outward actions.** Anything that changes shared state or contacts people is shown as a card the requester confirms: check-ins, startup renames, meetings (Google invitations). No silent writes.
5. **Secrets.** `.env`, `*.pem`, tokens and the service-role key never go in git. The browser only ever gets the Supabase *publishable* key. Sensitive tables have RLS enabled with **no** policies (service role only).
6. **Privacy by design.** Calendar data is stored as per-day counts only (never titles/invitees). Mentor notes and `audience='mentors'` memories are never shown to founders. Refresh tokens are Fernet-encrypted.
7. **Migrations are run by the user** in the Supabase SQL editor (`supabase/migrations/*.sql`). Agents write them, tell the user, and never assume they were run (code degrades gracefully when a table is missing).
8. **Working alongside other agents.** Another agent edits the dashboard (`src/components/dashboard/*`, `src/hooks/use-dash-data.ts`, etc.) in the same folder. Commit only the files you changed, never `git add -A`, `git pull` before pushing, re-read a file before editing it, and say so before deploying (a deploy builds the whole working tree).
9. **One bot instance.** Slack Socket Mode splits events across connections. Never run the bot locally while the VM runs it.

---

## 3. Repository map

| Path | Purpose |
|---|---|
| `slack_bot.py` | Slack Bolt app: message routing, profile setup modals, Home tab, confirmation cards, schedulers (daily prompts, Home refresh, heartbeat, GitHub/Google pollers), CLI (`--simulate`, `--daily-dry-run`). |
| `bot_agent.py` | The brain: one tool-calling LLM turn per message, role-gated tools, context building, server-side validation. |
| `bot_memory.py` | Persistent memory and CRM data access (history, facts, notes, tasks, milestones, goals, pending meetings). Never raises. |
| `mentor_home.py` | Per-startup health rules and the mentor Slack view (pure functions). |
| `profile_rules.py` | Double-entry rules for profile setup (name+email matching, claiming invited records). |
| `daily_checkin.py` | 17:00 SGT prompts and the next-morning nudge. |
| `syllabus.py` | The 12-week schedule (`src/data/syllabus.json`): current week, deliverables, `has_session`. |
| `integrations.py` | Signed state/links, activity summaries, GitHub repo picker blocks, dashboard "Slack pass" links. |
| `github_app.py` | GitHub App API (installation tokens from the private key): repo listing, 14-day backfill, org lookups. |
| `google_calendar.py` | Google OAuth, encrypted tokens, read-only event sync into counts, live "my calendar", studio-calendar event creation. |
| `meetings.py` | Meeting requests: time parsing, 12-hour formatting, attendee resolution, event bodies. |
| `channel_memory.py` | Reads only the Slack channels switched on in the Developer page, keeps 7 days of their messages, builds the per-person channel context (only channels that person is a member of). |
| `dev_home.py` | Developer view on the Slack Home tab (Mentor view / Developer switch, developers only): channel toggles, settings, test-as-someone, tools, recent warnings. |
| `dev_controls.py` | Developer-page settings (`bot_settings`), command queue (`bot_commands`) and console copy (`bot_logs`). |
| `src/routes/dev.tsx`, `src/routes/api/dev/*`, `src/lib/dev-auth.ts` | Developer page (channels, test console, controls, logs). Only for `DEV_EMAILS` (default ben@evecount.com) matched against `mentors.email`; everyone else gets 404. |
| `src/routes/` | TanStack Start site: `index.tsx` (dashboard), `about.tsx`/`privacy.tsx` (public, needed for Google OAuth), `api/github/{callback,webhook}.ts`, `api/google/callback.ts`, `api/dash/*`, `api/health.ts`. |
| `src/components/dashboard/`, `src/hooks/` | Dashboard UI and data hooks (live Supabase data; owned partly by another agent). |
| `src/lib/integrations.ts`, `supabase-admin.ts` | Webhook signature checks, signed state, GitHub event mapping, server-side Supabase REST. |
| `supabase/schema.sql`, `supabase/migrations/` | Base schema and incremental migrations (apply in filename order). |
| `deploy/` | VM setup (`setup.sh`, systemd unit) for the always-on bot. |
| `tests/` | Python `unittest` suites for the bot. `src/test/` holds Vitest suites for the site. |

---

## 4. Data model (Supabase)

Public-read (dashboard): `cohorts`, `startups`, `founders`, `deliverables`, `submissions` (confirmed check-ins), `signals` (activity feed: check-ins, commits, PRs, issues, meetings), `milestones`, `goals`.
Service-role only: `mentors`, `notes`, `tasks`, `bot_messages`, `memories`, `integrations` (GitHub/Google, encrypted tokens), `github_installations`, `github_claims`, `google_pending`, `studio_calendar`, `pending_meetings`, `bot_heartbeat`, `bot_channels`, `channel_messages` (7-day window, pruned hourly), `bot_settings`, `bot_commands`, `bot_logs`, and any tables added by other agents' migrations.

Health rules (Slack and dashboard must stay in sync): **blocked** = latest check-in is Blocked; **quiet** = no check-in for 7+ days; otherwise **on track**.

---

## 5. How the bot behaves

- **Roles.** Mentors are verified with a mentor code (or pre-registered by email); founders are matched by Slack email or set up via the founder profile form. Duplicate/double entry is blocked by `profile_rules.py`.
- **Founder messages** become answers, tasks, milestones/goals or a **check-in proposal** (confirm card). Founders cannot edit mentor-issued milestones (they can tick goals).
- **Mentor messages** get cohort answers, notes, tasks, milestone issuing, stream/lead assignment, renames, meeting scheduling. `pulse` shows the cohort card.
- **Memory.** Short-term: last 12 messages per user (`bot_messages`). Long-term: `memories` facts (`audience` all/mentors). Channels: the last 7 days of channels enabled in the Developer page, shown to the agent only for channels the asker is a member of in Slack. Needs bot scopes `channels:read`, `channels:history`, `groups:read`, `groups:history`, `users:read` (+ `channels:join`) and bot events `message.channels`, `message.groups`.
- **Daily rhythm.** 17:00 SGT on program days it asks each linked founder what they did (mentioning open goals); 09:30 next day one nudge if no reply; 09:00 blocker audit.
- **Home tab.** Founder: "Your sprint radar – <startup>", due this week, last check-in, two milestone groups (mentor-issued vs own), connections (GitHub repo picker inline, calendar). Mentor: cohort view with attention items. Republished within ~15 s of relevant changes.
- **Meetings.** "Set up a meet with everyone at 3 PM on Thursday at 111 Somerset" -> a proposal card -> on confirm, an event is created on the shared **studio Google Calendar** (connected once by a mentor) with a Meet link for virtual meetings and invitations emailed. Times are SGT, shown in 12-hour format. Founders cannot invite "everyone".

---

## 6. Integrations

- **GitHub (GitHub App).** Founder presses Connect GitHub -> GitHub installs the app (they choose repos) -> redirect to `/api/github/callback` (signed `state`) -> webhook events at `/api/github/webhook` (HMAC verified) become `signals`. Repos are chosen on the Home tab; only chosen repos count. The bot uses the app's private key to list repos and backfill 14 days. Organisation installs that need an owner's approval are linked via a "claim" (founder names the org; the bot links it once installed).
- **Google Calendar (read-only, per founder).** OAuth via `/api/google/callback` parks the one-time code in `google_pending`; the bot exchanges it, stores an encrypted refresh token, and syncs hourly into per-day meeting counts. Scope: `calendar.events.readonly`.
- **Studio calendar (write, shared).** A mentor connects the studio Google account once (scope `calendar.events`); only the bot reads that token.
- **Dashboard access.** Originally a client-side code gate (`mamba2026`, a deterrent, not security) plus a signed 90-day pass in the Slack "Open dashboard" link that skips it. **The dashboard agent is replacing this with real sign-in by role** (`src/lib/dash-auth.ts`, `src/routes/api/auth/`, `api/dash/session.ts`, `api/dash/snapshot.ts`); read those files for the current behaviour. `/about` and `/privacy` stay public (Google OAuth needs them).

---

## 7. Hosting, deploy and health

- **Bot:** GCP e2-micro VM `venturebot` (project `venturedash-bot-6411`, us-central1-a), systemd service, files in `/opt/venturebot`. Update: copy changed files to the VM, `sudo systemctl restart venturebot`. See `deploy/README.md`.
- **Site:** Cloudflare Worker `venturedash` -> https://venturedash.benlim631.workers.dev. After `npm run build`, set `compatibility_date` in `.output/server/wrangler.json` to today's **UTC** date and add `"html_handling": "none"` under `assets`, then `npx wrangler deploy --config .output/server/wrangler.json --name venturedash`. Worker secrets: `STATE_SECRET`, `GITHUB_WEBHOOK_SECRET`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_URL`.
- **Health:** the bot writes `bot_heartbeat` every 30 s (including whether the Slack websocket is really connected). `/api/health` returns 200 only when that is fresh, 503 otherwise. A Google Cloud uptime check on that URL emails the owner when it fails.

---

## 8. Environment variables (`.env`, never committed)

`SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `VITE_SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `GEMINI_API_KEY` (+ optional `AI_MODEL`, default `gemini-3.8-flash`), `DASHBOARD_URL`, `STATE_SECRET`, `MENTOR_CODE`, `ONBOARDING_CODE` (optional), `GITHUB_APP_SLUG`, `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY_PATH` (or `GITHUB_APP_PRIVATE_KEY`), `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `DEV_EMAILS` (optional, bot and Worker; default `ben@evecount.com`). The browser build reads `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` from `.env.local` (publishable key only).

---

## 9. Testing

```bash
npm test                          # Vitest (site, dashboard logic, webhook signing)
python -m unittest discover tests # bot: agent rules, profile rules, GitHub/Google/meetings, daily prompts
python slack_bot.py --simulate    # offline extraction/card dry run
python slack_bot.py --daily-dry-run  # prints the prompts that would be sent now
npm run build                     # client + SSR bundle
```

---

## 10. Known gaps / ideas

- Weekly Monday digest for mentors; "talking but not building" alert (check-ins but no code activity).
- Dashboard timeline showing GitHub/meeting signals prominently (coordinate with the dashboard agent).
- Dashboard role-based sign-in is in progress by the dashboard agent; keep Slack "Open dashboard" links working with whatever it ships.
- Move heavy Home queries into one RPC if the cohort grows beyond a few dozen people.
