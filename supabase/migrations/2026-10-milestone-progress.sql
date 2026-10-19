-- Run once in the Supabase SQL editor.
-- Progress on milestones that have no goals (mentors often set a milestone without breaking it into goals).
-- Same meaning as on goals: `progress` is official (set or confirmed by a founder or mentor); `est_*` is the bot's
-- estimate from GitHub work (progress_estimator.py), shown as "estimated" until someone confirms or adjusts it.
-- Milestones that do have goals keep taking their progress from the goals.

alter table public.milestones add column if not exists progress int check (progress between 0 and 100);
alter table public.milestones add column if not exists est_progress int check (est_progress between 0 and 100);
alter table public.milestones add column if not exists est_reason text;
alter table public.milestones add column if not exists est_at timestamptz;

-- Who marked a blocker handled on the dashboard, and an optional note for the other mentors.
alter table public.blocker_reviews add column if not exists handled_by text;
alter table public.blocker_reviews add column if not exists note text;
