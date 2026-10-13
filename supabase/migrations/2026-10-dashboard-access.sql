-- Run once in the Supabase SQL editor, AFTER the new website is deployed.
-- (The old website reads these tables straight from the browser, so running this first would blank it.)
--
-- Dashboard access control. The browser no longer reads Supabase at all: the website's server reads with the
-- service-role key and only returns what the signed-in person may see (mentors: the cohort; founders: their
-- own startup). People sign in through Slack and must be in `mentors` or `founders`.
-- The Slack bot uses the service-role key, so none of this changes what it can do.

-- 1. Single-use "Open dashboard" links: a link's id is recorded the first time it's used.
create table if not exists public.dash_link_uses (
  jti text primary key,
  used_at timestamptz default now()
);
alter table public.dash_link_uses enable row level security;  -- no policies: service role only

-- 2. Remove public read access. Row level security stays on with no policies, so the public (anon) key
--    published in the website can no longer read check-ins, founders, mentors or anything else.
do $$
declare t text;
begin
  foreach t in array array[
    'cohorts', 'startups', 'founders', 'deliverables', 'submissions', 'signals',
    'mentors', 'milestones', 'goals', 'blocker_reviews'
  ] loop
    if to_regclass('public.' || t) is not null then
      execute format('drop policy if exists "Allow read access to all" on public.%I', t);
    end if;
  end loop;
end $$;

-- 3. Housekeeping: used link ids older than the link lifetime (1 hour) are safe to forget.
delete from public.dash_link_uses where used_at < now() - interval '1 day';
