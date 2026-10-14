-- Run once in the Supabase SQL editor.
-- Lets the Slack bot create meetings on one shared studio Google Calendar (connected once by a mentor),
-- after the requester confirms. Service role only (RLS on, no policies).

create table if not exists public.studio_calendar (
  id text primary key default 'primary',
  account text,                 -- the Google account that owns the studio calendar
  refresh_token text not null,  -- Fernet-encrypted by the bot
  connected_by text,            -- Slack id of the mentor who connected it
  created_at timestamptz default now()
);
alter table public.studio_calendar enable row level security;

-- Meeting proposals waiting for the requester's "Create" click
create table if not exists public.pending_meetings (
  id uuid primary key default gen_random_uuid(),
  requested_by text not null,   -- Slack id
  payload jsonb not null,
  created_at timestamptz default now()
);
alter table public.pending_meetings enable row level security;

-- The Google connect inbox also carries the mentor "studio calendar" connection (no founder/startup)
alter table public.google_pending add column if not exists kind text not null default 'calendar';
alter table public.google_pending add column if not exists slack_user_id text;
alter table public.google_pending alter column founder_id drop not null;
alter table public.google_pending alter column startup_id drop not null;
