-- Run once in the Supabase SQL editor.
-- Work-signal integrations (GitHub now, Google Calendar next).

-- Which external accounts are connected to which startup.
-- RLS enabled with NO policies on purpose: only service-role code (the bot and the site's server routes) can read it.
create table if not exists public.integrations (
  id uuid primary key default gen_random_uuid(),
  startup_id text not null references public.startups(id) on delete cascade,
  founder_id text references public.founders(id) on delete set null,
  provider text not null check (provider in ('github', 'google')),
  external_id text not null,          -- GitHub installation id / Google account id
  account text,                       -- display name, e.g. the GitHub org or user
  repos text[] default '{}',          -- repositories the founder granted
  created_at timestamptz default now(),
  unique (provider, external_id)
);
alter table public.integrations enable row level security;

-- Work signals flow through the existing activity feed (and appear on the dashboard timeline).
alter table public.signals drop constraint if exists signals_type_check;
alter table public.signals add constraint signals_type_check
  check (type in ('checkin', 'blocker', 'deliverable_submitted', 'unblocked', 'ai_digest',
                  'commit', 'pull_request', 'issue', 'meeting'));
alter table public.signals add column if not exists meta jsonb;
