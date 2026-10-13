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
  meta: { repo?: string } | null;
  created_at: string;
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
        const [startups, founders, submissions, signals, repos, handled, milestones] =
          await Promise.all([
            admin(`startups?select=id,name,tagline,stream,lead${by("id")}`),
            admin(`founders?select=id,name,startup_id,profile,target_audience${by("startup_id")}`),
            admin(
              `submissions?select=id,startup_id,founder_id,status,progress,blocker,digest,raw_transcript,created_at` +
                `&confirmed=eq.true&order=created_at.desc&limit=300${by("startup_id")}`,
            ),
            admin<SignalRow[]>(
              `signals?select=id,startup_id,type,headline,detail,stream,meta,created_at&order=created_at.desc&limit=200${by("startup_id")}`,
            ),
            admin<Repos[]>(
              `integrations?select=startup_id,repos,selected_repos&provider=eq.github${by("startup_id")}`,
            ),
            identity.role === "mentor"
              ? admin("blocker_reviews?select=startup_id,handled_at")
              : Promise.resolve({ data: [] }),
            admin(
              `milestones?select=id,startup_id,title,due_date,status,goals(id,title,done)&status=neq.dropped` +
                `&order=due_date.asc.nullslast${by("startup_id")}`,
            ),
          ]);
        if (!startups.ok) return json({ error: "unavailable" }, 502);

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
          signals: visible.map(({ meta: _meta, ...s }) => s),
          handled: handled.data ?? [],
          milestones: milestones.data ?? [],
        });
      },
    },
  },
});
