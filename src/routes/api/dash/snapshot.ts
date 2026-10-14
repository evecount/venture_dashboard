import { createFileRoute } from "@tanstack/react-router";
import { admin } from "@/lib/supabase-admin";
import { isMonitored } from "@/lib/integrations";
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
type MilestoneRow = {
  id: string;
  startup_id: string;
  title: string;
  due_date: string | null;
  status: string;
  created_by: string | null;
  created_by_role: string | null;
  goals: Array<{ id: string; title: string; done: boolean; created_by: string | null }> | null;
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
        const [startups, founders, submissions, signals, repos, handled, milestones, notes, tasks] =
          await Promise.all([
            admin(`startups?select=id,name,tagline,stream,lead${by("id")}`),
            admin(`founders?select=id,name,startup_id,profile,target_audience${by("startup_id")}`),
            admin(
              `submissions?select=id,startup_id,founder_id,deliverable_id,status,progress,blocker,digest,raw_transcript,artifact_url,created_at` +
                `&confirmed=eq.true&order=created_at.desc&limit=300${by("startup_id")}`,
            ),
            admin<SignalRow[]>(
              `signals?select=id,startup_id,type,headline,detail,stream,meta,created_at&order=created_at.desc&limit=200${by("startup_id")}`,
            ),
            admin<Repos[]>(
              `integrations?select=startup_id,repos,selected_repos&provider=eq.github${by("startup_id")}`,
            ),
            mentorOnly("blocker_reviews?select=startup_id,handled_at"),
            admin<MilestoneRow[]>(
              `milestones?select=id,startup_id,title,due_date,status,created_by,created_by_role,goals(id,title,done,created_by)&status=neq.dropped` +
                `&order=due_date.asc.nullslast${by("startup_id")}`,
            ),
            // Mentor notes about a startup are for the studio team, not the founders.
            mentorOnly(
              "notes?select=id,startup_id,author_name,body,created_at&order=created_at.desc&limit=200",
            ),
            admin(
              `tasks?select=id,startup_id,owner_slack_id,title,due_date,status,created_at&status=eq.open` +
                `&order=due_date.asc.nullslast&limit=200${by("startup_id")}`,
            ),
          ]);
        if (!startups.ok) return json({ error: "unavailable" }, 502);

        // Who set each milestone or goal: Slack IDs become names here, so the browser never sees Slack IDs.
        const setters = new Set<string>();
        for (const m of milestones.data ?? []) {
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
            : [{ data: [] }, { data: [] }];
          for (const f of fs.data ?? [])
            people.set(f.slack_user_id, { name: f.name, role: "founder" });
          for (const m of ms.data ?? [])
            people.set(m.slack_user_id, { name: m.name, role: "mentor" });
        }
        const setBy = (id: string | null | undefined, role?: string | null) => {
          const p = id ? people.get(id) : undefined;
          if (p) return p;
          return role === "mentor" || role === "founder" ? { name: null, role } : null;
        };

        // GitHub work counts only for the repos the founder currently monitors; changing the choice in Slack
        // changes what shows here straight away (older rows from other repos are hidden, not deleted).
        const reposBy = new Map<string, Repos[]>();
        for (const r of repos.data ?? [])
          reposBy.set(r.startup_id, [...(reposBy.get(r.startup_id) ?? []), r]);
        const visible = (signals.data ?? []).filter(
          (s) =>
            !GITHUB_TYPES.has(s.type) ||
            (reposBy.get(s.startup_id ?? "") ?? []).some((r) =>
              isMonitored(r.selected_repos, s.meta?.repo, r.repos),
            ),
        );

        return json({
          identity,
          startups: startups.data ?? [],
          founders: founders.data ?? [],
          submissions: submissions.data ?? [],
          // Only the counts the trends need leave the server, not repo names or other metadata.
          signals: visible.map(({ meta, ...s }) => ({
            ...s,
            weight: Number(meta?.commits ?? meta?.meetings ?? 1) || 1,
            merged: !!meta?.merged,
          })),
          handled: handled.data ?? [],
          milestones: (milestones.data ?? []).map(
            ({ created_by, created_by_role, goals, ...m }) => ({
              ...m,
              set_by: setBy(created_by, created_by_role),
              goals: (goals ?? []).map(({ created_by: by, ...g }) => ({ ...g, set_by: setBy(by) })),
            }),
          ),
          notes: notes.data ?? [],
          tasks: tasks.data ?? [],
        });
      },
    },
  },
});
