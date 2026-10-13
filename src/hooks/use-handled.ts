import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";

/**
 * "Mark handled" state shared by every mentor: startup id -> handled_at, live from Supabase.
 * Writes go through /api/dash/handled (the browser key is read-only). Updates optimistically.
 */
export function useHandled() {
  const [handled, setHandled] = useState<Record<string, string>>({});
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!supabase) return;
    const client = supabase;
    let cancelled = false;

    async function load() {
      const res = await client.from("blocker_reviews").select("startup_id,handled_at");
      if (cancelled || res.error) return;
      setHandled(
        Object.fromEntries(
          (res.data ?? []).map((r) => [r.startup_id as string, r.handled_at as string]),
        ),
      );
    }

    void load();
    const channel = client
      .channel("handled-live")
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "blocker_reviews" },
        () => void load(),
      )
      .subscribe();
    return () => {
      cancelled = true;
      client.removeChannel(channel);
    };
  }, []);

  async function setMark(startupId: string, value: boolean) {
    const previous = handled;
    setError(false);
    setHandled((h) => {
      const next = { ...h };
      if (value) next[startupId] = new Date().toISOString();
      else delete next[startupId];
      return next;
    });
    try {
      const res = await fetch("/api/dash/handled", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ startup_id: startupId, handled: value }),
      });
      if (!res.ok) throw new Error(String(res.status));
    } catch {
      setHandled(previous);
      setError(true);
    }
  }

  return { handled, setMark, error };
}
