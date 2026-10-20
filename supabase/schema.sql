-- ==============================================================================
-- Venture Studio OS: Supabase Schema & Realtime Replication Engine
-- Cohort SG#01 Architecture: Slack-driven Autonomous Command Center
-- ==============================================================================

create extension if not exists "uuid-ossp";

-- 1. Cohorts
create table if not exists public.cohorts (
  id text primary key, -- e.g. 'sg-01'
  name text not null,
  program text not null default 'Mamba MVP Program',
  start_date timestamptz not null default now(),
  current_week int not null default 1,
  total_weeks int not null default 12,
  created_at timestamptz default now()
);

-- 2. Startups
create table if not exists public.startups (
  id text primary key, -- e.g. 'startup-01'
  cohort_id text references public.cohorts(id) on delete cascade,
  name text not null,
  tagline text,
  stream text not null default 'Unassigned' check (stream in ('Tech', 'GTM', 'Marketing', 'Unassigned')),
  lead text not null default 'Unassigned',
  slack_channel_id text,
  velocity int default 80 check (velocity between 0 and 100),
  active_status text default 'In progress' check (active_status in ('In progress', 'Blocked', 'On Track', 'Completed')),
  created_at timestamptz default now()
);

-- 3. Founders (Mapped to Slack User IDs)
create table if not exists public.founders (
  id text primary key, -- e.g. 'demo-founder-01'
  startup_id text references public.startups(id) on delete cascade,
  slack_user_id text unique, -- null until the founder joins Slack and is matched by email
  email text unique, -- pre-registered by the coordinator; matched against the Slack profile email
  name text not null,
  role text default 'Founder',
  profile text,
  target_audience text,
  created_at timestamptz default now()
);

-- Migration for projects created before email onboarding:
--   alter table public.founders alter column slack_user_id drop not null;
--   alter table public.founders add column if not exists email text unique;

-- 3b. Mentors (studio team). Kept separate from founders so the Slack bot never treats a mentor as a founder.
create table if not exists public.mentors (
  id text primary key,
  slack_user_id text unique, -- null until linked by email on Slack join
  email text unique,
  name text not null,
  title text default 'Mentor',
  created_at timestamptz default now()
);
alter table public.mentors enable row level security;
create policy "Allow read access to all" on public.mentors for select using (true);

-- 4. Syllabus Deliverables (Keyed to the 12-Week Schedule)
create table if not exists public.deliverables (
  id text primary key, -- e.g. 'del-wk01'
  cohort_id text references public.cohorts(id) on delete cascade,
  week text not null, -- e.g. 'WK 01'
  sprint_phase text not null,
  title text not null,
  due_date timestamptz not null,
  stream text not null default 'General',
  owner_lead text,
  created_at timestamptz default now()
);

-- 5. Submissions & Milestone Check-Ins (Mutated by Slack Bot)
create table if not exists public.submissions (
  id uuid primary key default gen_random_uuid(),
  startup_id text references public.startups(id) on delete cascade,
  deliverable_id text references public.deliverables(id) on delete cascade,
  founder_id text references public.founders(id) on delete set null,
  status text not null check (status in ('In progress', 'Blocked', 'On Track', 'Completed')),
  progress int default 50 check (progress between 0 and 100),
  blocker text default 'None',
  digest text not null,
  raw_transcript text,
  artifact_url text,
  confirmed boolean default true,
  confirmed_at timestamptz default now(),
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- 6. Realtime Signals & Activity Feed (Powering Zero-Click Dashboard Ticker)
create table if not exists public.signals (
  id uuid primary key default gen_random_uuid(),
  startup_id text references public.startups(id) on delete cascade,
  type text not null check (type in ('checkin', 'blocker', 'deliverable_submitted', 'unblocked', 'ai_digest')),
  headline text not null,
  detail text,
  stream text default 'General',
  actor text not null,
  created_at timestamptz default now()
);

-- Enable RLS (Read allowed for authenticated/anon dashboard, Write restricted)
alter table public.cohorts enable row level security;
alter table public.startups enable row level security;
alter table public.founders enable row level security;
alter table public.deliverables enable row level security;
alter table public.submissions enable row level security;
alter table public.signals enable row level security;

-- Public read policies for dashboard view
create policy "Allow read access to all" on public.cohorts for select using (true);
create policy "Allow read access to all" on public.startups for select using (true);
create policy "Allow read access to all" on public.founders for select using (true);
create policy "Allow read access to all" on public.deliverables for select using (true);
create policy "Allow read access to all" on public.submissions for select using (true);
create policy "Allow read access to all" on public.signals for select using (true);

-- Enable Realtime Pub/Sub on tables that trigger live dashboard updates
alter publication supabase_realtime add table public.submissions;
alter publication supabase_realtime add table public.signals;
alter publication supabase_realtime add table public.startups;

-- ==============================================================================
-- Initial Seed Data (Syllabus & Cohort Roster)
-- ==============================================================================

insert into public.cohorts (id, name, current_week, total_weeks)
values ('sg-01', 'Venture Studio · SG#01', 1, 12)
on conflict (id) do nothing;

insert into public.startups (id, cohort_id, name, tagline, stream, lead, velocity, active_status)
values 
  ('startup-auvira', 'sg-01', 'Auvira', null, 'GTM', 'GTM Venture Advisor', 80, 'In progress'),
  ('startup-sharedout', 'sg-01', 'SharedOut', null, 'Tech', 'Technical Advisor', 65, 'Blocked')
on conflict (id) do nothing;

-- Founders are added by the coordinator (id, startup_id, name, email) or set themselves up through the Slack bot.

insert into public.deliverables (id, cohort_id, week, sprint_phase, title, due_date, stream, owner_lead)
values
  ('del-wk01', 'sg-01', 'WK 01', 'Sprint 1: Problem, Founder Thesis & Opportunity', '1-page venture thesis & Top 10 assumptions ranked', now() + interval '4 days', 'General', 'Founders'),
  ('del-wk02', 'sg-01', 'WK 02', 'Sprint 1: Ideation, Concept Selection & Sprint 1 Review', 'Customer Discovery Syntheses & 10 validated problem interviews', now() + interval '11 days', 'GTM', 'Founders / GTM Lead'),
  ('del-wk03', 'sg-01', 'WK 03', 'Sprint 2: Solution Architecture & WoZ Validation', 'Wizard-of-Oz Prototype & Pricing Validation Test', now() + interval '18 days', 'Tech', 'Technical Lead')
on conflict (id) do nothing;
