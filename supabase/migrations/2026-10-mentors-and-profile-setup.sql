-- Run once in the Supabase SQL editor (existing projects).

-- 1. Mentors table (the Slack bot treats anyone here as a mentor, never as a founder)
create table if not exists public.mentors (
  id text primary key,
  slack_user_id text unique,
  email text unique,
  name text not null,
  title text default 'Mentor',
  created_at timestamptz default now()
);
alter table public.mentors enable row level security;
drop policy if exists "Allow read access to all" on public.mentors;
create policy "Allow read access to all" on public.mentors for select using (true);

-- 2. Founders can sign up before a mentor assigns their stream/lead
alter table public.startups drop constraint if exists startups_stream_check;
alter table public.startups add constraint startups_stream_check
  check (stream in ('Tech', 'GTM', 'Marketing', 'Unassigned'));
alter table public.startups alter column stream set default 'Unassigned';
alter table public.startups alter column lead set default 'Unassigned';
