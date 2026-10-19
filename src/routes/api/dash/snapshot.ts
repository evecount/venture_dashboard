import { createFileRoute } from "@tanstack/react-router";
import { admin } from "@/lib/supabase-admin";
import { isMonitored } from "@/lib/integrations";
import { visibleTasks } from "@/lib/dash-scope";
import { identityFromRequest, json } from "@/lib/dash-auth";

const GITHUB_TYPES = new Set(["commit", "pull_request", "issue"]);

type SignalRow = {
  id: string;
  startup_id: string | null;
  type: string;
  headline: string;
  detail: string | null;
  stream: string | null;
  meta: { repo?: string; commits?: number; merged?: boolean; meetings?: number } | null;
  created_at: string;
};
/**
 * Rows from a query, or none if it failed. A failed PostgREST call returns an error object, not a list, so reading
 * `.data` directly would crash the whole dashboard over one missing table or column.
 */
function rowsOf<T>(r: { ok: boolean; data: T[] | null }): T[];
function rowsOf(r: { ok: boolean; data: unknown }): unknown[];
function rowsOf(r: { ok: boolean; data: unknown }): unknown[] {
  return r.ok && Array.isArray(r.data) ? r.data : [];
}

type MilestoneRow = {
  id: string;
  startup_id: string;
  title: string;
  due_date: string | null;
  status: string;
  created_by: string | null;
  created_by_role: string | null;
  goals: Array<{
    id: string;
    title: string;
    done: boolean;
    created_by: string | null;
    progress: number | null;
    est_progress: number | null;
    est_reason: string | null;
  }> | null;
};
type EventRow = {
  id: string;
  title: string;
  starts_at: string;
  ends_at: string | null;
  location: string | null;
  meet_url: string | null;
  attendees: Array<{ name: string; email: string; response: string }> | null;
};
type MentorEventRow = {
  id: string;
  event_id: string;
  slack_user_id: string;
  title: string;
  busy_only: boolean;
  all_day: boolean;
  starts_at: string;
  ends_at: string | null;
};
type Repos = { startup_id: string; repos: string[] | null; selected_repos: string[] | null };

// Everything the dashboard shows, scoped to who is asking: mentors see the cohort, a founder sees only their
// own startup. The browser never reads Supabase directly; this route (service-role key) is the only way in.
export const Route = createFileRoute("/api/dash/snapshot")({
  server: {
    handlers: {
      GET: async ({ request }) => {
        const identity = await identityFromRequest(request);
        if (!identity) return json({ error: "signed_out" }, 401);

        const only = identity.role === "founder" ? encodeURIComponent(identity.startupId) : null;
        const by = (col: string) => (only ? `&${col}=eq.${only}` : "");
        const mentorOnly = <T>(path: string) =>
          identity.role === "mentor"
            ? admin<T>(path)
            : Promise.resolve({ ok: true, data: [] as T });
        // Mentors share one cohort-wide query, so its cap is generous and limited to recent weeks; otherwise one busy
        // startup would push the others' signals out and their trends would read as "no activity".
        const signalsSince = encodeURIComponent(
          new Date(Date.now() - 45 * 86_400_000).toISOString(),
        );
        const [startups, founders, submissions, signals, repos, handled, milestones, notes, tasks] =
          await Promise.all([
            admin(`startups?select=id,name,tagline,stream,lead,cohort_id${by("id")}`),
            admin(`founders?select=id,name,startup_id,profile,target_audience${by("startup_id")}`),
            admin(
              `submissions?select=id,startup_id,founder_id,deliverable_id,status,progress,blocker,digest,raw_transcript,artifact_url,created_at` +
                `&confirmed=eq.true&order=created_at.desc&limit=${only ? 300 : 800}${by("startup_id")}`,
            ),
            admin<SignalRow[]>(
              `signals?select=id,startup_id,type,headline,detail,stream,meta,created_at&created_at=gte.${signalsSince}&order=created_at.desc&limit=${only ? 300 : 1500}${by("startup_id")}`,
            ),
            admin<Repos[]>(
              `integrations?select=startup_id,repos,selected_repos&provider=eq.github${by("startup_id")}`,
            ),
            mentorOnly("blocker_reviews?select=startup_id,handled_at"),
            admin<MilestoneRow[]>(
              `milestones?select=id,startup_id,title,due_date,status,created_by,created_by_role,goals(id,title,done,created_by,progress,est_progress,est_reason)&status=neq.dropped` +
                `&order=due_date.asc.nullslast${by("startup_id")}`,
            ),
            // Mentor notes about a startup are for the studio team, not the founders.
            mentorOnly(
              "notes?select=id,startup_id,author_name,body,created_at&order=created_at.desc&limit=200",
            ),
            admin<{ owner_slack_id: string | null }[]>(
              `tasks?select=id,startup_id,owner_slack_id,title,due_date,status,created_at&status=eq.open` +
                `&order=due_date.asc.nullslast&limit=200${by("startup_id")}`,
            ),
          ]);
        if (!startups.ok) return json({ error: "unavailable" }, 502);

        // Cohorts (MVP#1, MVP#2, ...): each runs the same 12-week syllabus from its own start Monday. A founder only
        // gets their own cohort.
        const myCohorts = new Set(
          rowsOf(startups as { ok: boolean; data: { cohort_id: string | null }[] | null }).map(
            (s) => s.cohort_id,
          ),
        );
        const cohorts = rowsOf(
          await admin<
            { id: string; name: string; start_date: string; total_weeks: number | null }[]
          >("cohorts?select=id,name,start_date,total_weeks&order=start_date.asc"),
        ).filter((c) => identity.role === "mentor" || myCohorts.has(c.id));
        // Slack ids of the founder's own team: their tasks stay visible, mentors' private ones do not.
        const teamSlack =
          identity.role === "founder"
            ? await admin<{ slack_user_id: string }[]>(
                `founders?select=slack_user_id&startup_id=eq.${only}&slack_user_id=not.is.null`,
              )
            : { ok: true, data: [] as { slack_user_id: string }[] };

        // Studio meetings, copied from the studio calendar by the bot. Mentors see every meeting; a founder only
        // the ones they're invited to (same rule as the bot). Attendee emails never leave the server.
        const since = encodeURIComponent(new Date(Date.now() - 12 * 3600_000).toISOString());
        const [events, roster] = await Promise.all([
          admin<EventRow[]>(
            `studio_events?select=id,title,starts_at,ends_at,location,meet_url,attendees&starts_at=gte.${since}&order=starts_at.asc&limit=100`,
          ),
          admin<{ id: string; email: string | null; startup_id: string | null }[]>(
            identity.role === "founder"
              ? `founders?select=id,email,startup_id&id=eq.${encodeURIComponent(identity.founderId)}`
              : "founders?select=id,email,startup_id",
          ),
        ]);
        const startupByEmail = new Map(
          rowsOf(roster)
            .filter((p) => p.email)
            .map((p) => [p.email!.toLowerCase(), p.startup_id]),
        );
        // Mentors' own calendars (connected read-only through the bot): mentors only, never founders. Studio meetings
        // also appear on attendees' calendars, so those copies are dropped here.
        const studioIds = new Set(rowsOf(events).map((e) => e.id));
        const [mentorEvents, mentorNames] =
          identity.role === "mentor"
            ? await Promise.all([
                admin<MentorEventRow[]>(
                  `mentor_events?select=id,event_id,slack_user_id,title,busy_only,all_day,starts_at,ends_at&ends_at=gte.${since}&order=starts_at.asc&limit=400`,
                ),
                admin<{ slack_user_id: string; name: string }[]>(
                  "mentors?select=slack_user_id,name",
                ),
              ])
            : [
                { ok: true, data: [] as MentorEventRow[] },
                { ok: true, data: [] },
              ];
        const nameOf = new Map(rowsOf(mentorNames).map((m) => [m.slack_user_id, m.name]));
        const mentorBusy = (mentorEvents.ok ? rowsOf(mentorEvents) : [])
          .filter((e) => !studioIds.has(e.event_id))
          .map(({ slack_user_id, event_id: _e, ...e }) => ({
            ...e,
            mentor: nameOf.get(slack_user_id) ?? "A mentor",
          }));
        const myEmail =
          identity.role === "founder" ? rowsOf(roster)[0]?.email?.toLowerCase() : null;
        const meetings = (events.ok ? rowsOf(events) : [])
          .filter(
            (e) =>
              identity.role === "mentor" ||
              (!!myEmail && (e.attendees ?? []).some((a) => a.email === myEmail)),
          )
          .map(({ attendees, ...e }) => ({
            ...e,
            startup_ids: [
              ...new Set(
                (attendees ?? [])
                  .map((a) => startupByEmail.get(a.email))
                  .filter((x): x is string => !!x),
              ),
            ],
            people:
              identity.role === "mentor"
                ? (attendees ?? []).map((a) => a.name || a.email.split("@")[0])
                : [],
          }));

        // Who set each milestone or goal: Slack IDs become names here, so the browser never sees Slack IDs.
        const setters = new Set<string>();
        for (const m of rowsOf(milestones)) {
          if (m.created_by) setters.add(m.created_by);
          for (const g of m.goals ?? []) if (g.created_by) setters.add(g.created_by);
        }
        const people = new Map<string, { name: string; role: "mentor" | "founder" }>();
        if (setters.size) {
          const ids = [...setters].filter((id) => /^[UW][A-Z0-9]{2,24}$/.test(id)).join(",");
          const [ms, fs] = ids
            ? await Promise.all([
                admin<{ slack_user_id: string; name: string }[]>(
                  `mentors?select=slack_user_id,name&slack_user_id=in.(${ids})`,
                ),
                admin<{ slack_user_id: string; name: string }[]>(
                  `founders?select=slack_user_id,name&slack_user_id=in.(${ids})`,
                ),
              ])
            : [
                { ok: true, data: [] },
                { ok: true, data: [] },
              ];
          for (const f of rowsOf(fs))
            people.set(f.slack_user_id, { name: f.name, role: "founder" });
          for (const m of rowsOf(ms)) people.set(m.slack_user_id, { name: m.name, role: "mentor" });
        }
        const setBy = (id: string | null | undefined, role?: string | null) => {
          const p = id ? people.get(id) : undefined;
          if (p) return p;
          return role === "mentor" || role === "founder" ? { name: null, role } : null;
        };

        // GitHub work counts only for the repos the founder currently monitors; changing the choice in Slack
        // changes what shows here straight away (older rows from other repos are hidden, not deleted).
        const reposBy = new Map<string, Repos[]>();
        for (const r of rowsOf(repos))
          reposBy.set(r.startup_id, [...(reposBy.get(r.startup_id) ?? []), r]);
        const visible = rowsOf(signals).filter(
          (s) =>
            !GITHUB_TYPES.has(s.type) ||
            (reposBy.get(s.startup_id ?? "") ?? []).some((r) =>
              isMonitored(r.selected_repos, s.meta?.repo, r.repos),
            ),
        );

        return json({
          identity,
          startups: rowsOf(startups),
          founders: rowsOf(founders),
          submissions: rowsOf(submissions),
          // Only the counts the trends need leave the server, not repo names or other metadata.
          signals: visible.map(({ meta, ...s }) => ({
            ...s,
            weight: Number(meta?.commits ?? meta?.meetings ?? 1) || 1,
            merged: !!meta?.merged,
          })),
          handled: rowsOf(handled),
          milestones: rowsOf(milestones).map(({ created_by, created_by_role, goals, ...m }) => ({
            ...m,
            set_by: setBy(created_by, created_by_role),
            goals: (goals ?? []).map(({ created_by: by, ...g }) => ({ ...g, set_by: setBy(by) })),
          })),
          notes: rowsOf(notes),
          tasks: visibleTasks(
            rowsOf(tasks),
            identity.role,
            rowsOf(teamSlack).map((f) => f.slack_user_id),
          ),
          meetings,
          mentorBusy,
          cohorts,
        });
      },
    },
  },
});
