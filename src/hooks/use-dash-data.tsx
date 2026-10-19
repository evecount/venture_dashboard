import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { buildRoster, type FounderRow, type StartupRow } from "@/components/dashboard/roster";
import type { Founder } from "@/components/dashboard/data";

export type SubmissionRow = {
  id: string;
  startup_id: string;
  founder_id: string | null;
  deliverable_id?: string | null;
  artifact_url?: string | null;
  status: string;
  progress: number | null;
  blocker: string | null;
  digest: string;
  raw_transcript?: string | null;
  created_at: string;
};
export type SignalRow = {
  id: string;
  startup_id: string | null;
  type: string;
  headline: string;
  detail: string | null;
  stream: string | null;
  weight?: number;
  merged?: boolean;
  created_at: string;
};
export type NoteRow = {
  id: string;
  startup_id: string | null;
  author_name: string | null;
  body: string;
  created_at: string;
};
export type TaskRow = {
  id: string;
  startup_id: string | null;
  title: string;
  due_date: string | null;
  status: string;
  created_at: string;
};
/** An event on a mentor's own connected calendar (mentors only). Private events arrive as "Busy". */
export type MentorBusyRow = {
  id: string;
  mentor: string;
  title: string;
  busy_only: boolean;
  all_day: boolean;
  starts_at: string;
  ends_at: string | null;
};
/** A meeting on the studio calendar (synced by the bot). `people` is mentor-only; founders get an empty list. */
export type MeetingRow = {
  id: string;
  title: string;
  starts_at: string;
  ends_at: string | null;
  location: string | null;
  meet_url: string | null;
  startup_ids: string[];
  people: string[];
};
/** Who set a milestone or goal (name is null when the person's record is gone). */
export type SetBy = { name: string | null; role: "mentor" | "founder" } | null;
export type Goal = {
  id: string;
  title: string;
  done: boolean;
  set_by?: SetBy;
  /** Official partial progress, set or confirmed by a founder or mentor. */
  progress?: number | null;
  /** The bot's estimate from GitHub work, until someone confirms or adjusts it. */
  est_progress?: number | null;
  est_reason?: string | null;
};
export type Milestone = {
  id: string;
  startup_id: string;
  title: string;
  due_date: string | null;
  status: "open" | "done" | "dropped";
  set_by?: SetBy;
  goals: Goal[];
};

export type DashSnapshot = {
  startups: StartupRow[];
  founders: FounderRow[];
  submissions: SubmissionRow[];
  signals: SignalRow[];
  handled: Array<{ startup_id: string; handled_at: string }>;
  milestones: Milestone[];
  notes: NoteRow[];
  tasks: TaskRow[];
  meetings: MeetingRow[];
  mentorBusy: MentorBusyRow[];
};

type DashData = {
  snapshot: DashSnapshot | null;
  roster: Founder[] | null;
  handled: Record<string, string>;
  lastSync: Date | null;
  error: boolean;
  handledError: boolean;
  setHandled: (startupId: string, value: boolean) => Promise<void>;
};

const POLL_MS = 20_000;
const DashContext = createContext<DashData | null>(null);

export function useDashData(): DashData {
  const data = useContext(DashContext);
  if (!data) throw new Error("useDashData must be used inside <DashDataProvider>");
  return data;
}

/**
 * The dashboard's data, from /api/dash/snapshot (already scoped by the server to what the signed-in person may see).
 * Refreshes every 20s and whenever the tab comes back into view.
 */
export function DashDataProvider({ children }: { children: ReactNode }) {
  const [snapshot, setSnapshot] = useState<DashSnapshot | null>(null);
  const [lastSync, setLastSync] = useState<Date | null>(null);
  const [error, setError] = useState(false);
  const [overrides, setOverrides] = useState<Record<string, string | null>>({});
  const [handledError, setHandledError] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/dash/snapshot", { cache: "no-store" });
      if (res.status === 401) {
        window.location.reload(); // session ended: back to the sign-in screen
        return;
      }
      if (!res.ok) throw new Error(String(res.status));
      setSnapshot((await res.json()) as DashSnapshot);
      setOverrides({});
      setLastSync(new Date());
      setError(false);
    } catch {
      setError(true);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, POLL_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") void load();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [load]);

  const handled = useMemo(() => {
    const out: Record<string, string> = {};
    for (const r of snapshot?.handled ?? []) out[r.startup_id] = r.handled_at;
    for (const [id, at] of Object.entries(overrides)) {
      if (at) out[id] = at;
      else delete out[id];
    }
    return out;
  }, [snapshot, overrides]);

  const roster = useMemo(
    () =>
      snapshot
        ? buildRoster(
            snapshot.startups,
            snapshot.founders,
            snapshot.submissions,
            lastSync ?? new Date(),
          )
        : null,
    [snapshot, lastSync],
  );

  const setHandled = useCallback(
    async (startupId: string, value: boolean) => {
      setHandledError(false);
      setOverrides((o) => ({ ...o, [startupId]: value ? new Date().toISOString() : null }));
      try {
        const res = await fetch("/api/dash/handled", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ startup_id: startupId, handled: value }),
        });
        if (!res.ok) throw new Error(String(res.status));
        void load();
      } catch {
        setOverrides((o) => {
          const next = { ...o };
          delete next[startupId];
          return next;
        });
        setHandledError(true);
      }
    },
    [load],
  );

  return (
    <DashContext.Provider
      value={{ snapshot, roster, handled, lastSync, error, handledError, setHandled }}
    >
      {children}
    </DashContext.Provider>
  );
}
