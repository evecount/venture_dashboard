import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";

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

/** Loads the timeline for a founder/startup; refetches whenever `refreshKey` changes (live ledger updates). */
export function useTimeline(startupId: string | undefined, refreshKey: string) {
  const [entries, setEntries] = useState<TimelineEntry[] | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!supabase || !startupId) {
      setEntries(null);
      return;
    }
    const client = supabase;
    let cancelled = false;
    setLoading(true);
    (async () => {
      const [subs, sigs] = await Promise.all([
        client
          .from("submissions")
          .select("id,status,progress,blocker,digest,created_at")
          .eq("startup_id", startupId)
          .eq("confirmed", true)
          .order("created_at", { ascending: false })
          .limit(40),
        client
          .from("signals")
          .select("id,type,headline,detail,created_at")
          .eq("startup_id", startupId)
          .order("created_at", { ascending: false })
          .limit(40),
      ]);
      if (cancelled) return;
      setEntries(mergeTimeline((subs.data ?? []) as SubRow[], (sigs.data ?? []) as SigRow[]));
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [startupId, refreshKey]);

  return { entries, loading };
}
