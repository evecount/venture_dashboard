import { useMemo } from "react";
import { useDashData } from "@/hooks/use-dash-data";

export type TimelineEntry = {
  id: string;
  kind: "checkin" | "blocker" | "signal";
  at: string;
  title: string;
  detail: string;
  status?: string;
  progress?: number | undefined;
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
      at: g.created_at,
      title: g.headline,
      detail: g.detail ?? "",
    });
  }
  return entries.sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
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
