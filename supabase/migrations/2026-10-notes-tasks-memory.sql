-- Run once in the Supabase SQL editor.
-- Adds mentor notes, follow-up tasks and the bot's persistent memory.
-- RLS is enabled with NO public policies on purpose: only the Slack bot (service-role key)
-- can read or write these tables. Mentor notes and memories must never be readable with the anon key.

-- Mentor notes on a startup (private to mentors)
create table if not exists public.notes (
  id uuid primary key default gen_random_uuid(),
  startup_id text references public.startups(id) on delete cascade,
  author_slack_id text not null,
  author_name text,
  body text not null,
  created_at timestamptz default now()
);
create index if not exists notes_startup_idx on public.notes (startup_id, created_at desc);

-- Follow-ups. owner_slack_id null = belongs to the whole startup.
create table if not exists public.tasks (
  id uuid primary key default gen_random_uuid(),
  startup_id text references public.startups(id) on delete cascade,
  owner_slack_id text,
  title text not null,
  due_date date,
  status text not null default 'open' check (status in ('open', 'done')),
  created_by text,
  created_at timestamptz default now(),
  completed_at timestamptz
);
create index if not exists tasks_open_idx on public.tasks (status, due_date);

-- Short-term memory: recent conversation turns per Slack user
create table if not exists public.bot_messages (
  id bigint generated always as identity primary key,
  slack_user_id text not null,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  created_at timestamptz default now()
);
create index if not exists bot_messages_user_idx on public.bot_messages (slack_user_id, created_at desc);

-- Long-term memory: durable facts the bot learns (audience 'mentors' is never shown to founders)
create table if not exists public.memories (
  id uuid primary key default gen_random_uuid(),
  subject_type text not null check (subject_type in ('startup', 'founder', 'mentor')),
  subject_id text not null,
  fact text not null,
  audience text not null default 'all' check (audience in ('all', 'mentors')),
  created_by text,
  created_at timestamptz default now()
);
create index if not exists memories_subject_idx on public.memories (subject_id, created_at desc);

alter table public.notes enable row level security;
alter table public.tasks enable row level security;
alter table public.bot_messages enable row level security;
alter table public.memories enable row level security;
