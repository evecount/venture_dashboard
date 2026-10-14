# VentureOS

**A progress tracker for venture studio founders that asks them to fill in nothing.**

Live site: https://venturedash.benlim631.workers.dev (founders and mentors get a personal link from Slack)

## The problem
Accelerators ask founders to report progress in Jira, Notion or weekly forms. Founders are busy building, so the reports are late, thin or missing, and mentors waste time chasing them.

## How it works
Founders talk to **Venture Buddy**, a Slack assistant, in plain language. It turns what they say into check-ins, milestones, goals and tasks, and **connects to the work itself**:

- **GitHub:** commits, pull requests and issues for the repositories the founder chooses (read-only).
- **Google Calendar:** how many meetings they had, and how many were with people outside the team (counts only, never titles).
- **Slack:** a daily "what did you get done today?" prompt, and a Home tab showing their sprint, milestones and connections.

Mentors get a live picture: which startups are on track, blocked or quiet, with the evidence. They can ask Venture Buddy about any startup or founder, leave private notes, assign follow-ups, issue milestones, and **schedule meetings** with the cohort ("set up a meet with everyone at 3 PM on Thursday at 111 Somerset"). The bot always proposes first; nothing is sent until the requester confirms.

The dashboard is a read-only view of the same live data. No simulated data anywhere.

## Stack
Slack (Bolt, Socket Mode) · Python bot with a tool-calling LLM (Gemini) · Supabase (Postgres + Realtime) · TanStack Start on a Cloudflare Worker · GitHub App · Google Calendar API.

## Getting started
```bash
npm install
npm test                           # site tests
python -m unittest discover tests  # bot tests
npm run dev                        # dashboard on http://localhost:8080
python slack_bot.py                # the Slack bot (needs .env)
```
Setup of Slack, Supabase, the GitHub App and Google OAuth is in [supabase/README.md](supabase/README.md); running the bot 24/7 on a VM is in [deploy/README.md](deploy/README.md). **Developers and AI agents: read [AGENT_CONTEXT.md](AGENT_CONTEXT.md) first.**

## Privacy
What is stored and who can see it: https://venturedash.benlim631.workers.dev/privacy
