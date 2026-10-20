---
name: weekly-digest
description: Catch a mentor up on the cohort or one startup, a digest of what shipped, who is stuck or quiet, what slipped and what to ask next.
roles: mentor
tools: startup_detail, github_activity
triggers: \b(digest|catch me up|brief( me)?|briefing|recap|round-?up|week in review|overview|summar\w*|what('s| has) (been )?happen\w*|how('s| is) (the )?cohort)\b
effort: low
---
Write a digest a busy mentor can read in 30 seconds. Use only real data from CONTEXT and the look-up tools, never invent progress.
- For one startup, call startup_detail first (and github_activity if they ask what was built).
- For the cohort, work from CONTEXT. Call startup_detail only for the one or two startups that need a closer look (blocked, quiet, or a claim that doesn't match their work signals).
- Shape:
  - one opening line on the cohort as a whole (how many on track / blocked / quiet);
  - *Needs you*: blocked or quiet startups, with how long and the latest blocker in their words;
  - *Moving*: startups with real progress (check-ins plus code), one line each;
  - *Watch*: mismatches, like a check-in saying "on track" with no GitHub activity in 7 days, or a milestone due within 3 days with goals still open;
  - *Ask next*: one concrete question per startup in Needs you / Watch.
- Skip a section that has nothing in it. Name founders and startups. Say "no check-in since <date>" rather than "inactive".
