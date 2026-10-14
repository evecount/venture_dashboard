-- Run once in the Supabase SQL editor.
-- Remembers which proactive mentor nudges were already sent, so each episode (a blocked run, a quiet stretch,
-- a week of "checking in without code activity") is announced once. Service role only.
create table if not exists public.mentor_alerts (
  key text primary key,
  sent_at timestamptz not null default now()
);
alter table public.mentor_alerts enable row level security;
