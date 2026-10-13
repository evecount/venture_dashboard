import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { buildRoster, type FounderRow, type StartupRow, type SubmissionRow } from "@/components/dashboard/roster";
import type { Founder } from "@/components/dashboard/data";

/**
 * Live cohort roster from Supabase (one row per startup), the same data the Slack bot reads.
 * Returns null when Supabase is not configured or has no startups, so the demo fixtures stay in use.
 * Refetches on any change to submissions, founders or startups.
 */
export function useLiveRoster(): Founder[] | null {
  const [roster, setRoster] = useState<Founder[] | null>(null);

  useEffect(() => {
    if (!supabase) return;
    const client = supabase;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function load() {
      const [st, fo, su] = await Promise.all([
        client.from("startups").select("id,name,tagline,stream,lead"),
        client.from("founders").select("id,name,startup_id,profile,target_audience"),
        client
          .from("submissions")
          .select("startup_id,founder_id,status,progress,blocker,digest,raw_transcript,created_at")
          .eq("confirmed", true)
          .order("created_at", { ascending: false })
          .limit(300),
      ]);
      if (cancelled || st.error || !st.data?.length) return;
      setRoster(buildRoster(st.data as StartupRow[], (fo.data ?? []) as FounderRow[], (su.data ?? []) as SubmissionRow[]));
    }

    const refresh = () => {
      clearTimeout(timer);
      timer = setTimeout(load, 300);
    };
    void load();
    const channel = client
      .channel("roster-live")
      .on("postgres_changes", { event: "*", schema: "public", table: "submissions" }, refresh)
      .on("postgres_changes", { event: "*", schema: "public", table: "founders" }, refresh)
      .on("postgres_changes", { event: "*", schema: "public", table: "startups" }, refresh)
      .subscribe();

    return () => {
      cancelled = true;
      clearTimeout(timer);
      client.removeChannel(channel);
    };
  }, []);

  return roster;
}
