import { useEffect, useRef, useState } from "react";
import { supabase } from "@/lib/supabase";

export type SubmissionRow = {
  founder_id: string | null;
  status: "In progress" | "Blocked" | "On Track" | "Completed";
  progress: number | null;
  blocker: string | null;
  digest: string;
  created_at?: string;
};

export type SignalRow = {
  id: string;
  type: string;
  headline: string;
  detail: string | null;
  stream: string | null;
  created_at: string;
};

type Handlers = {
  onSubmission: (row: SubmissionRow) => void;
  onSignals: (rows: SignalRow[], live: boolean) => void;
};

/**
 * Subscribes to Supabase Realtime for `submissions` and `signals`.
 * No-ops (connected = false) when VITE_SUPABASE_* env vars are not set.
 */
export function useLiveLedger(handlers: Handlers) {
  const [connected, setConnected] = useState(false);
  const ref = useRef(handlers);
  ref.current = handlers;

  useEffect(() => {
    if (!supabase) return;
    const client = supabase;
    let cancelled = false;

    // Hydrate with the latest persisted state, then stream changes.
    (async () => {
      const [subs, sigs] = await Promise.all([
        client
          .from("submissions")
          .select("founder_id,status,progress,blocker,digest,created_at")
          .eq("confirmed", true)
          .order("created_at", { ascending: false })
          .limit(50),
        client
          .from("signals")
          .select("id,type,headline,detail,stream,created_at")
          .order("created_at", { ascending: false })
          .limit(10),
      ]);
      if (cancelled) return;
      const seen = new Set<string>();
      for (const row of (subs.data ?? []) as SubmissionRow[]) {
        if (row.founder_id && !seen.has(row.founder_id)) {
          seen.add(row.founder_id);
          ref.current.onSubmission(row);
        }
      }
      if (sigs.data?.length) ref.current.onSignals(sigs.data as SignalRow[], false);
    })();

    const channel = client
      .channel("cohort-live")
      .on("postgres_changes", { event: "*", schema: "public", table: "submissions" }, (p) => {
        const row = p.new as SubmissionRow & { confirmed?: boolean };
        if (row?.confirmed !== false) ref.current.onSubmission(row);
      })
      .on("postgres_changes", { event: "INSERT", schema: "public", table: "signals" }, (p) => {
        ref.current.onSignals([p.new as SignalRow], true);
      })
      .subscribe((status) => setConnected(status === "SUBSCRIBED"));

    return () => {
      cancelled = true;
      setConnected(false);
      client.removeChannel(channel);
    };
  }, []);

  return { connected };
}
