-- One-off personal reminders ("remind me Friday 3 PM to send the deck"), sent by the bot at the chosen time.
-- Service-role only (RLS on, no policies). Run once in the Supabase SQL editor.
create table if not exists bot_reminders (
  id uuid primary key default gen_random_uuid(),
  slack_user_id text not null,
  text text not null,
  remind_at timestamptz not null,
  sent_at timestamptz,
  created_at timestamptz not null default now()
);
create index if not exists bot_reminders_due on bot_reminders (remind_at) where sent_at is null;
alter table bot_reminders enable row level security;
