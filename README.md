# Venture Studio OS (Zero-Click Operations)

**The first venture studio dashboard that requires ZERO clicking from your founders.**

[👉 View the Live Prototype](https://evecount.github.io/venture_dashboard/)

---

## The Problem
Traditional venture accelerators and studios force founders to use Jira, Asana, or rigid Notion templates to track their weekly sprints. This creates massive friction. Founders are busy building; they don't want to log in, fill out forms, and click dropdown menus to report their blockers. 

## The Solution: Ambient Orchestration
This dashboard is a **Read-Only Control Ledger**. 

It is powered by a stealth, autonomous backend tier (architected by Cybrdeck) that lives entirely where the founders already are: **Slack and Telegram**.

Instead of filling out status reports, founders simply drop unstructured voice notes, meeting transcripts, or quick text rants into their Slack channel with our `MVP_buddy` agent. 

Behind the scenes, **Qwen AI** instantly parses the unstructured context, extracts the structured payload (`Status`, `Stream`, `Current Blockers`, `Syllabus Progress`), and pushes it straight to a Supabase database.

The React dashboard updates in real-time for the Studio Mentors. 

### Proactive Chasing (No More Follow-Ups)
Because the bot has native access to the Slack API (`app.client.chat_postMessage`), it isn't just a passive listener. 
If a founder's status remains "Blocked" in the Supabase ledger for more than 48 hours, the `MVP_buddy` bot will automatically DM them: *"Hey! The ledger shows you are still blocked on [issue]. Send me a voice memo or text update. Do you need me to schedule a sync with Gwen and Ben?"*

**Zero friction. Zero clicking. Pure execution.**
