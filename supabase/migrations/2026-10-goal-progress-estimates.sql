-- Run once in the Supabase SQL editor.
-- Partial progress on goals, and progress the bot estimates from a founder's GitHub work (progress_estimator.py).
-- `progress` is official (set or confirmed by the founder or a mentor). `est_*` is the bot's estimate, shown as
-- "estimated from GitHub" until someone confirms or adjusts it. Only people mark goals done, never the estimate.

alter table public.goals add column if not exists progress int check (progress between 0 and 100);
alter table public.goals add column if not exists est_progress int check (est_progress between 0 and 100);
alter table public.goals add column if not exists est_reason text;
alter table public.goals add column if not exists est_at timestamptz;

-- Which GitHub work each startup has already been assessed on, so nothing is counted twice.
create table if not exists public.progress_estimate_state (
  startup_id text primary key references public.startups(id) on delete cascade,
  last_signal_at timestamptz not null,
  updated_at timestamptz default now()
);
alter table public.progress_estimate_state enable row level security;
