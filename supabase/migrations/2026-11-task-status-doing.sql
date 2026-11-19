-- Run once in the Supabase SQL editor.
-- Lets a task be "doing" (shown as "In progress" on the board) as well as open or done.
-- Until this runs everything keeps working; the bot just can't move a task to In progress.
alter table public.tasks drop constraint if exists tasks_status_check;
alter table public.tasks add constraint tasks_status_check check (status in ('open', 'doing', 'done'));
