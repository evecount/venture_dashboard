-- Run once in the Supabase SQL editor.
-- Channel memory: the bot only reads Slack channels switched on in the dashboard's Developer page, keeps the
-- last 7 days of their messages so it can answer questions about them, and forgets anything older.
-- Dev controls: settings and a command queue the Developer page writes and the bot picks up, plus recent bot logs.
-- All service role only (RLS on, no policies). The site reaches them through /api/dev/* after checking the developer.

create table if not exists public.bot_channels (
  id text primary key,                     -- Slack channel id (C... or G...)
  name text not null,
  is_private boolean not null default false,
  is_member boolean not null default false, -- the bot is in the channel (it can only read channels it is in)
  member_ids text[] not null default '{}', -- who may ask the bot about this channel (Slack's own membership)
  num_members integer,
  enabled boolean not null default false,  -- switched on in the Developer page
  status text,                             -- last sync result shown in the Developer page
  backfilled_at timestamptz,
  updated_at timestamptz not null default now()
);
alter table public.bot_channels enable row level security;

create table if not exists public.channel_messages (
  channel_id text not null references public.bot_channels(id) on delete cascade,
  ts text not null,                        -- Slack message timestamp (unique per channel)
  thread_ts text,
  user_id text,
  user_name text,
  text text not null,
  posted_at timestamptz not null,
  primary key (channel_id, ts)
);
create index if not exists channel_messages_posted_idx on public.channel_messages (posted_at desc);
alter table public.channel_messages enable row level security;

create table if not exists public.bot_settings (
  key text primary key,
  value jsonb,
  updated_at timestamptz not null default now()
);
alter table public.bot_settings enable row level security;

create table if not exists public.bot_commands (
  id uuid primary key default gen_random_uuid(),
  command text not null,
  args jsonb not null default '{}'::jsonb,
  status text not null default 'queued',   -- queued | running | done | error
  result text,
  requested_by text,
  created_at timestamptz not null default now(),
  finished_at timestamptz
);
create index if not exists bot_commands_status_idx on public.bot_commands (status, created_at);
alter table public.bot_commands enable row level security;

create table if not exists public.bot_logs (
  id bigint generated always as identity primary key,
  line text not null,
  created_at timestamptz not null default now()
);
create index if not exists bot_logs_created_idx on public.bot_logs (created_at desc);
alter table public.bot_logs enable row level security;

alter table public.bot_heartbeat add column if not exists scopes text;
