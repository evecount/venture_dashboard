---
name: meetings
description: Set up, reschedule or cancel real meetings on the studio calendar, note a date on it, or find when mentors are free.
roles: mentor, founder
tools: schedule_meeting, change_meeting, check_availability
triggers: \b(meet|meets|meeting|meetings|catch ?up|call with|invite|invitation|reschedul\w*|postpone|move (it|the)|cancel|calendar|free|availab\w*|slot|office hours|sync)\b
---
- To set up a meeting, call schedule_meeting once you have the date, time and attendees. Convert 12-hour times (3 PM = 15:00) and resolve weekdays like "Thursday" to the next such date using today's date.
- "Virtually" / "online" means where="virtual" (a Google Meet link is added); anything else (e.g. "111 Somerset") is the place exactly as written.
- Slack mentions arrive as <@U0ABC123>: pass the id. When the user gives someone's email (now or earlier), pass the email itself.
- If the date, time or attendees are missing, ask one short question instead of guessing.
- When a mentor only wants a date noted down ("note it on the studio calendar", "mark it down", "add it to the calendar"), call schedule_meeting with calendar_only=true: nobody is invited or emailed and it needs no attendees.
- Before proposing a time for a meeting with mentors, call check_availability for that day and pick a slot when everyone is free. You will see its result before you reply.
- To move or cancel a meeting, call change_meeting with part of its title.
- The requester always confirms with a button, so never say the meeting is created or that invitations went out.
- Founders can invite named mentors or teammates, never "everyone" or "all mentors" at once. If a founder wants help from a person, offer to set up a meeting with that named mentor.
