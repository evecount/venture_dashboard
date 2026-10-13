-- Run once in the Supabase SQL editor (after 2026-10-integrations.sql).
-- Lets the founder choose which of the repositories they granted the bot should monitor,
-- and lets the bot confirm in Slack once GitHub is connected.

alter table public.integrations add column if not exists selected_repos text[];   -- null/empty = monitor everything granted
alter table public.integrations add column if not exists notified_at timestamptz;  -- set once the Slack confirmation was sent

-- GitHub tells us which repos were granted BEFORE the founder's browser returns to us, so park that here.
create table if not exists public.github_installations (
  installation_id text primary key,
  account text,
  repos text[] default '{}',
  updated_at timestamptz default now()
);
alter table public.github_installations enable row level security;  -- no policies: service role only
