-- Side-by-side trial of Gemini's dedicated speech model (voice_compare.py). Service role only, pruned after 14 days.
create table if not exists public.voice_comparisons (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  model text,
  current_text text,
  current_ms integer,
  candidate_text text,
  candidate_ms integer,
  similarity real,
  error text
);
create index if not exists voice_comparisons_created_at on public.voice_comparisons (created_at desc);
alter table public.voice_comparisons enable row level security;  -- no policies: only the bot's service role can read or write
