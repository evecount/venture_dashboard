---
name: investor-update
description: Draft an investor or stakeholder update (monthly/fortnightly) from the startup's real check-ins, milestones and GitHub work.
roles: founder, mentor
tools: startup_detail, github_activity
triggers: \b(investor|investors|stakeholder|update email|monthly update|progress report|newsletter|board update)\b
effort: low
---
Draft the update from real records only. Call startup_detail (30 days, or the period asked) and github_activity first.
- Format it as a Slack message the founder can copy: a short subject line, then *Highlights*, *Progress vs goals* (milestones and how many goals are done), *Product* (what shipped, from GitHub headlines), *Challenges* (blockers in their own words and what's being done), *Asks* (only if they mentioned any, otherwise a placeholder).
- Put anything you don't have in [square brackets] for them to fill in, e.g. [revenue this month], [number of users]. Never make up numbers, customers or quotes.
- Keep it under 200 words unless they ask for more. Offer one tweak at the end ("Want it more formal, or shorter?").
- A mentor asking for one drafts it for the named startup, and never includes mentor notes.
