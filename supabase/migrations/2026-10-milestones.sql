-- Run once in the Supabase SQL editor.
-- Milestones (with goals) that founders set and mentors can create or edit.
-- Public read like check-ins (the dashboard shows them); only the Slack bot (service-role key) can write.

create table if not exists public.milestones (
  id uuid primary key default gen_random_uuid(),
  startup_id text not null references public.startups(id) on delete cascade,
  title text not null,
  due_date date,
  status text not null default 'open' check (status in ('open', 'done', 'dropped')),
  created_by text,
  created_by_role text check (created_by_role in ('founder', 'mentor')),
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
create index if not exists milestones_startup_idx on public.milestones (startup_id, status, due_date);

create table if not exists public.goals (
  id uuid primary key default gen_random_uuid(),
  milestone_id uuid not null references public.milestones(id) on delete cascade,
  title text not null,
  done boolean not null default false,
  done_at timestamptz,
  created_by text,
  created_at timestamptz default now()
);
create index if not exists goals_milestone_idx on public.goals (milestone_id);

alter table public.milestones enable row level security;
alter table public.goals enable row level security;
drop policy if exists "Allow read access to all" on public.milestones;
drop policy if exists "Allow read access to all" on public.goals;
create policy "Allow read access to all" on public.milestones for select using (true);
create policy "Allow read access to all" on public.goals for select using (true);

-- Live dashboard updates
alter publication supabase_realtime add table public.milestones;
alter publication supabase_realtime add table public.goals;
