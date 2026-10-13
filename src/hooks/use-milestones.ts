import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";

export type Goal = { id: string; title: string; done: boolean };
export type Milestone = {
  id: string;
  title: string;
  due_date: string | null;
  status: "open" | "done" | "dropped";
  goals: Goal[];
};

/** Milestones and goals for one startup. null = not connected or table unavailable. Refetches on live changes. */
export function useMilestones(startupId: string | undefined): Milestone[] | null {
  const [items, setItems] = useState<Milestone[] | null>(null);

  useEffect(() => {
    if (!supabase || !startupId) {
      setItems(null);
      return;
    }
    const client = supabase;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function load() {
      const res = await client
        .from("milestones")
        .select("id,title,due_date,status,goals(id,title,done)")
        .eq("startup_id", startupId)
        .neq("status", "dropped")
        .order("due_date", { ascending: true, nullsFirst: false });
      if (cancelled) return;
      setItems(res.error ? null : ((res.data ?? []) as Milestone[]));
    }

    const refresh = () => {
      clearTimeout(timer);
      timer = setTimeout(load, 300);
    };
    void load();
    const channel = client
      .channel(`milestones-${startupId}`)
      .on("postgres_changes", { event: "*", schema: "public", table: "milestones" }, refresh)
      .on("postgres_changes", { event: "*", schema: "public", table: "goals" }, refresh)
      .subscribe();
    return () => {
      cancelled = true;
      clearTimeout(timer);
      client.removeChannel(channel);
    };
  }, [startupId]);

  return items;
}
