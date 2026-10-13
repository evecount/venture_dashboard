-- Run once in the Supabase SQL editor.
-- "Mark handled" on the mentor dashboard: one row per startup, cleared again by any newer check-in
-- (the dashboard compares handled_at with the latest confirmed submission).
-- Public read like check-ins; only the dashboard's server route (service-role key) writes.

create table if not exists public.blocker_reviews (
  startup_id text primary key references public.startups(id) on delete cascade,
  handled_at timestamptz not null default now()
);

alter table public.blocker_reviews enable row level security;
drop policy if exists "Allow read access to all" on public.blocker_reviews;
create policy "Allow read access to all" on public.blocker_reviews for select using (true);

-- Live dashboard updates
alter publication supabase_realtime add table public.blocker_reviews;
