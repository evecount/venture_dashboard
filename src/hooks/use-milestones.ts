import { useMemo } from "react";
import { useDashData, type Goal, type Milestone } from "@/hooks/use-dash-data";

export type { Goal, Milestone };

/** Milestones and goals for one startup, from the dashboard snapshot. null = still loading. */
export function useMilestones(startupId: string | undefined): Milestone[] | null {
  const { snapshot } = useDashData();
  return useMemo(
    () =>
      snapshot && startupId ? snapshot.milestones.filter((m) => m.startup_id === startupId) : null,
    [snapshot, startupId],
  );
}
