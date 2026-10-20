-- Run once in the Supabase SQL editor (after the earlier migrations; nothing here changes existing data).
--
-- One call for everything the mentor Home tab needs about the cohort, instead of 3 base queries plus ~5 per startup
-- (slack_bot.cohort_overview: GitHub connections, activity counts, monitored repos, milestones/goals per startup).
-- The bot calls it with the service-role key:  supabase.rpc("mentor_home_data", {"p_days": 7}).execute().data
--
-- It returns ONE json object:
--   startups     [{id, name, stream, lead, cohort_id}]
--   founders     [{name, startup_id}]
--   submissions  newest-first confirmed check-ins, up to p_sub_limit: [{startup_id, founder_id, status, progress, blocker, digest, created_at}]
--   activity     {startup_id: {commits, prs_opened, prs_merged, issues_closed, meetings, external_meetings, last_activity, signals}}
--                over the last p_days. Same rules as integrations.activity_summary: GitHub work only counts for repos being
--                monitored right now (selected_repos, or the single shared repo); meetings always count. A startup with no
--                signals has no key (treat as zeros).
--   github       {startup_id: {connected: true, has_tracked: bool}}  has_tracked = at least one repo is being monitored
--   goals        {startup_id: {goals_total, goals_done}}  over OPEN milestones (as memory.milestones does)
--
-- Service role only: the function is not executable by anon or signed-in users, so it exposes nothing new to the dashboard.

create or replace function public.mentor_home_data(p_days int default 7, p_sub_limit int default 300)
returns jsonb
language sql
stable
set search_path = public
as $$
  with watched as (            -- repos being monitored right now, per startup
    select i.startup_id, r.repo
    from public.integrations i
    cross join lateral unnest(
      case
        when coalesce(cardinality(i.selected_repos), 0) > 0 then i.selected_repos
        when coalesce(cardinality(i.repos), 0) = 1 then i.repos
        else '{}'::text[]
      end
    ) as r(repo)
    where i.provider = 'github'
  ),
  conn as (                    -- startups with a GitHub connection, and whether anything is tracked
    select i.startup_id,
           bool_or(coalesce(cardinality(i.selected_repos), 0) > 0 or coalesce(cardinality(i.repos), 0) = 1) as has_tracked
    from public.integrations i
    where i.provider = 'github'
    group by i.startup_id
  ),
  sig as (                     -- work signals in the window; GitHub ones only for monitored repos
    select s.startup_id, s.type, s.meta, s.created_at
    from public.signals s
    where s.type in ('commit', 'pull_request', 'issue', 'meeting')
      and s.created_at >= now() - make_interval(days => p_days)
      and (s.type = 'meeting'
           or exists (select 1 from watched w where w.startup_id = s.startup_id and w.repo = s.meta ->> 'repo'))
  ),
  act as (
    select startup_id,
           coalesce(sum(case when type = 'commit' then coalesce(nullif(meta ->> 'commits', '')::numeric, 1) end), 0)::int as commits,
           count(*) filter (where type = 'pull_request' and coalesce(meta ->> 'merged', 'false') <> 'true') as prs_opened,
           count(*) filter (where type = 'pull_request' and meta ->> 'merged' = 'true') as prs_merged,
           count(*) filter (where type = 'issue' and meta ->> 'action' = 'closed') as issues_closed,
           coalesce(sum(case when type = 'meeting' then coalesce(nullif(meta ->> 'meetings', '')::numeric, 0) end), 0)::int as meetings,
           coalesce(sum(case when type = 'meeting' then coalesce(nullif(meta ->> 'external', '')::numeric, 0) end), 0)::int as external_meetings,
           max(created_at) as last_activity,
           count(*) as signals
    from sig
    group by startup_id
  ),
  goal_totals as (
    select m.startup_id, count(g.id) as goals_total, count(g.id) filter (where g.done) as goals_done
    from public.milestones m
    join public.goals g on g.milestone_id = m.id
    where m.status = 'open'
    group by m.startup_id
  ),
  subs as (
    select c.startup_id, c.founder_id, c.status, c.progress, c.blocker, c.digest, c.created_at
    from public.submissions c
    where c.confirmed
    order by c.created_at desc
    limit p_sub_limit
  )
  select jsonb_build_object(
    'startups', coalesce((select jsonb_agg(jsonb_build_object('id', s.id, 'name', s.name, 'stream', s.stream, 'lead', s.lead, 'cohort_id', s.cohort_id)
                                           order by s.name) from public.startups s), '[]'::jsonb),
    'founders', coalesce((select jsonb_agg(jsonb_build_object('name', f.name, 'startup_id', f.startup_id)) from public.founders f), '[]'::jsonb),
    'submissions', coalesce((select jsonb_agg(to_jsonb(x) order by x.created_at desc) from subs x), '[]'::jsonb),
    'activity', coalesce((select jsonb_object_agg(a.startup_id, to_jsonb(a) - 'startup_id') from act a), '{}'::jsonb),
    'github', coalesce((select jsonb_object_agg(c.startup_id, jsonb_build_object('connected', true, 'has_tracked', c.has_tracked)) from conn c), '{}'::jsonb),
    'goals', coalesce((select jsonb_object_agg(g.startup_id, jsonb_build_object('goals_total', g.goals_total, 'goals_done', g.goals_done)) from goal_totals g), '{}'::jsonb)
  );
$$;

revoke all on function public.mentor_home_data(int, int) from public, anon, authenticated;
grant execute on function public.mentor_home_data(int, int) to service_role;
