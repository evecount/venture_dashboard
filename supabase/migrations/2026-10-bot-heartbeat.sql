-- Run once in the Supabase SQL editor.
-- The Slack bot writes a heartbeat every 30 seconds; the site's /api/health reports whether it is fresh,
-- and a Google Cloud uptime check emails you when it isn't. Service role only.
create table if not exists public.bot_heartbeat (
  id text primary key default 'main',
  beat_at timestamptz not null default now(),
  slack_connected boolean not null default false,
  version text
);
alter table public.bot_heartbeat enable row level security;
