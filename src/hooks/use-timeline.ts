import { useMemo } from "react";
import { useDashData } from "@/hooks/use-dash-data";

export type TimelineEntry = {
  id: string;
  kind: "checkin" | "blocker" | "signal";
  /** For signals: commit, pull_request, issue, meeting, ... */
  type?: string | undefined;
  at: string;
  title: string;
  detail: string;
  status?: string;
  progress?: number | undefined;
  /** Commits in a push, or meetings in a day. */
  weight?: number | undefined;
  merged?: boolean | undefined;
};

type SubRow = {
  id: string;
  status: string;
  progress: number | null;
  blocker: string | null;
  digest: string;
  created_at: string;
};
type SigRow = {
  id: string;
  type: string;
  headline: string;
  detail: string | null;
  weight?: number | undefined;
  merged?: boolean | undefined;
  created_at: string;
};

const TWO_MINUTES = 2 * 60 * 1000;

/** Merges confirmed check-ins and ledger signals for one startup into a single newest-first timeline. */
export function mergeTimeline(subs: SubRow[], sigs: SigRow[]): TimelineEntry[] {
  const entries: TimelineEntry[] = subs.map((s) => ({
    id: `sub-${s.id}`,
    kind: s.status === "Blocked" ? "blocker" : "checkin",
    at: s.created_at,
    title: s.status,
    detail:
      s.status === "Blocked" && s.blocker && s.blocker !== "None"
        ? `${s.digest} Blocker: ${s.blocker}`
        : s.digest,
    status: s.status,
    progress: s.progress ?? undefined,
  }));
  for (const g of sigs) {
    // The Slack bot writes a signal alongside every check-in; skip those echoes.
    const echo = subs.some(
      (s) =>
        s.digest === g.detail &&
        Math.abs(Date.parse(s.created_at) - Date.parse(g.created_at)) < TWO_MINUTES,
    );
    if (echo) continue;
    entries.push({
      id: `sig-${g.id}`,
      kind: "signal",
      type: g.type,
      at: g.created_at,
      title: g.headline,
      detail: g.detail ?? "",
      weight: g.weight,
      merged: g.merged,
    });
  }
  return entries.sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
}

export type TimelineGroup = "checkin" | "code" | "meeting" | "other";

/** Which filter chip an entry belongs to. */
export function entryGroup(e: TimelineEntry): TimelineGroup {
  if (e.kind !== "signal") return "checkin";
  if (e.type === "commit" || e.type === "pull_request" || e.type === "issue") return "code";
  if (e.type === "meeting") return "meeting";
  return "other";
}

export type WorkSummary = { commits: number; prsMerged: number; meetings: number };

/** Real work in the last `days` days: commits pushed, pull requests merged, meetings held. */
export function workSummary(entries: TimelineEntry[], now = Date.now(), days = 7): WorkSummary {
  const since = now - days * 24 * 60 * 60 * 1000;
  const out: WorkSummary = { commits: 0, prsMerged: 0, meetings: 0 };
  for (const e of entries) {
    if (e.kind !== "signal" || Date.parse(e.at) < since) continue;
    if (e.type === "commit") out.commits += e.weight ?? 1;
    else if (e.type === "pull_request" && e.merged) out.prsMerged += 1;
    else if (e.type === "meeting") out.meetings += e.weight ?? 1;
  }
  return out;
}

/** The timeline for one startup, from the dashboard snapshot (newest 40 check-ins and signals). */
export function useTimeline(startupId: string | undefined, _refreshKey?: string) {
  const { snapshot } = useDashData();
  const entries = useMemo(() => {
    if (!snapshot || !startupId) return null;
    const subs = snapshot.submissions.filter((s) => s.startup_id === startupId).slice(0, 40);
    const sigs = snapshot.signals.filter((s) => s.startup_id === startupId).slice(0, 40);
    return mergeTimeline(subs, sigs);
  }, [snapshot, startupId]);
  return { entries, loading: snapshot === null };
}
