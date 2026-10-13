-- Run once in the Supabase SQL editor.
-- Google Calendar connection: encrypted refresh token on the integration row, plus a short-lived inbox for the
-- one-time code Google hands our website (the bot, which holds the client secret, exchanges it).
alter table public.integrations add column if not exists refresh_token text;  -- Fernet-encrypted by the bot; service role only

create table if not exists public.google_pending (
  id uuid primary key default gen_random_uuid(),
  founder_id text not null references public.founders(id) on delete cascade,
  startup_id text not null references public.startups(id) on delete cascade,
  code text not null,
  created_at timestamptz default now()
);
alter table public.google_pending enable row level security;  -- no policies: service role only
