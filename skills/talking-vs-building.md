---
name: talking-vs-building
description: Spot startups whose check-ins and actual work don't match (talking but not building, or building but not checking in).
roles: mentor
tools: startup_detail, github_activity
triggers: \b(talking|not building|all talk|actually (building|shipping|working)|who('s| is) (building|shipping|coding)|mismatch|gap between|walk the talk)\b
effort: low
---
Compare what each startup says (check-ins, progress %) with what it does (GitHub work signals, meetings).
- *Talking, not building*: check-ins in the last 7 days that claim progress, while GitHub is connected but shows no commits or PRs in 7 days. Only judge code for startups whose deliverable is technical; GTM or marketing work shows up in meetings, not commits.
- *Building, not telling*: code activity in the last 7 days but no check-in for 5+ days.
- *Can't tell*: GitHub not connected or no repository tracked. Say so; it's a setup gap, not a verdict.
- Call github_activity for any startup you flag, and quote one or two real headlines as evidence.
- Be fair and specific. This is a prompt for a conversation, not a judgement. End with the one startup you'd check on first and why.
