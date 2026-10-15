-- Run once in the Supabase SQL editor.
-- Upcoming studio-calendar meetings, copied by the bot every 5 minutes (studio_events.py) so the dashboard can
-- show them. Only the bot's own events are copied. Attendee emails let the dashboard show founders only the
-- meetings they're invited to. No public policies: only the bot and the website's server (service role) read it.

create table if not exists public.studio_events (
  id text primary key,          -- Google Calendar event id
  title text not null,
  starts_at timestamptz not null,
  ends_at timestamptz,
  location text,
  meet_url text,
  attendees jsonb not null default '[]'::jsonb,  -- [{name, email, response}]
  synced_at timestamptz default now()
);
create index if not exists studio_events_starts_idx on public.studio_events (starts_at);

alter table public.studio_events enable row level security;
