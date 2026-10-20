---
name: routines
description: Standing routines, messages the bot sends by itself on a repeating schedule (every Wednesday, each week, until they do); list or stop them.
roles: mentor
tools: create_routine, list_routines, cancel_routine
triggers: \b(every|each) (day|morning|evening|week|weekday|monday|tuesday|wednesday|thursday|friday|saturday|sunday|fortnight|month)\b|\b(weekly|fortnightly|daily|monthly|routine|routines|recurring|repeat\w*|until they)\b
---
- For anything RECURRING ("every Wednesday", "each week", "until they do"), call create_routine, never announce or remember: a remembered fact does nothing by itself.
- Before creating one, check AUTOMATIC MESSAGES: if a built-in message or an existing routine already does it, say so and offer to adjust it instead.
- If the request also wants something sent right now, do both: announce now and create_routine.
- Times are Singapore time in 24-hour HH:MM, converted from 12-hour (2 PM = 14:00). every_weeks is 1 (weekly), 2 (fortnightly) or 4.
- Keep tailored=true when the message depends on the person ("until they connect GitHub"), so each message is written for them and people it doesn't apply to are skipped.
- The mentor confirms a card before the routine starts, so don't say it is set up yet. To stop one, cancel_routine with its ref from AUTOMATIC MESSAGES (list_routines shows them all).
