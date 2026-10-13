-- Run once in the Supabase SQL editor.
-- A founder whose code lives in a GitHub organisation may need an organisation owner to approve the install first.
-- They tell the bot the organisation's name; the bot links the installation as soon as it appears. Service role only.
create table if not exists public.github_claims (
  id uuid primary key default gen_random_uuid(),
  startup_id text not null references public.startups(id) on delete cascade,
  founder_id text not null references public.founders(id) on delete cascade,
  org_login text not null,
  created_at timestamptz default now(),
  resolved_at timestamptz
);
create index if not exists github_claims_open_idx on public.github_claims (resolved_at, created_at);
alter table public.github_claims enable row level security;  -- no policies: only the bot (service role) can use it
