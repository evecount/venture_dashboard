-- Run once in the Supabase SQL editor.
-- Mentors' own Google Calendars (read-only), separate from the shared studio calendar. The bot copies the next two
-- weeks of each connected mentor's events into mentor_events every 10 minutes (mentor_calendars.py), to suggest
-- meeting times, flag clashes, and show mentors' schedules to other mentors on the dashboard. Founders never see
-- them. Events marked private in Google are stored as "Busy". No public policies: service role only.

create table if not exists public.mentor_calendars (
  slack_user_id text primary key,
  account text,
  refresh_token text not null,  -- Fernet-encrypted by the bot
  connected_at timestamptz default now()
);
alter table public.mentor_calendars enable row level security;

create table if not exists public.mentor_events (
  id text primary key,          -- slack_user_id:google_event_id
  event_id text not null,       -- Google event id (matches studio_events.id for studio meetings)
  slack_user_id text not null,
  title text not null,
  busy_only boolean not null default false,
  all_day boolean not null default false,
  starts_at timestamptz not null,
  ends_at timestamptz,
  synced_at timestamptz default now()
);
create index if not exists mentor_events_user_starts_idx on public.mentor_events (slack_user_id, starts_at);
alter table public.mentor_events enable row level security;
