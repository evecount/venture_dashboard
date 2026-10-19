-- Run once in the Supabase SQL editor.
-- Standing routines: recurring messages a mentor sets up in chat with the bot ("every Wednesday at 2 PM remind the
-- founders to ..."). The mentor confirms a card first; the bot sends them on schedule. Service role only.
create table if not exists public.bot_routines (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  instruction text not null,               -- what the message should say or ask, in the mentor's words
  weekday smallint not null check (weekday between 0 and 6),  -- 0 = Monday
  at_time text not null,                   -- HH:MM, Singapore time
  every_weeks smallint not null default 1, -- 1 weekly, 2 fortnightly, 4 four-weekly
  anchor_date date,                        -- first run; fortnightly counts from here
  audience text not null default 'founders', -- founders | mentors | everyone | cohort | people
  cohort_id text,
  people text[] not null default '{}',     -- Slack ids when audience = people
  tailored boolean not null default true,  -- written per person by the agent (can skip people it doesn't apply to)
  active boolean not null default true,
  created_by text,
  created_by_name text,
  created_at timestamptz not null default now(),
  last_run_at timestamptz
);
alter table public.bot_routines enable row level security;
