import type { Founder } from "./data";

export type StartupRow = {
  id: string;
  name: string;
  tagline?: string | null;
  stream: string;
  lead: string;
  cohort_id?: string | null;
};
export type FounderRow = {
  id: string;
  name: string;
  startup_id: string;
  profile?: string | null;
  target_audience?: string | null;
};
export type SubmissionRow = {
  startup_id: string;
  founder_id: string | null;
  status: string;
  progress: number | null;
  blocker: string | null;
  digest: string;
  raw_transcript?: string | null;
  created_at: string;
};

// Same rules as the Slack bot's mentor view (mentor_home.py): keep the two in sync.
export const QUIET_DAYS = 7;
const DAY = 24 * 60 * 60 * 1000;

export function relativeTime(iso: string, now: Date): string {
  const secs = Math.max(0, Math.floor((now.getTime() - Date.parse(iso)) / 1000));
  if (secs < 120) return "just now";
  if (secs < 3600) return `${Math.floor(secs / 60)} min ago`;
  if (secs < 86400) {
    const h = Math.floor(secs / 3600);
    return `${h} hour${h === 1 ? "" : "s"} ago`;
  }
  const d = Math.floor(secs / 86400);
  return `${d} day${d === 1 ? "" : "s"} ago`;
}

/** One dashboard row per startup, ordered blocked, then quiet, then on track (matches Slack). */
export function buildRoster(
  startups: StartupRow[],
  founders: FounderRow[],
  subs: SubmissionRow[],
  now: Date = new Date(),
): Founder[] {
  const rows = startups.map((st): Founder => {
    const mine = subs
      .filter((s) => s.startup_id === st.id)
      .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
    const people = founders.filter((f) => f.startup_id === st.id);
    const latest = mine[0];

    let health: NonNullable<Founder["health"]> = "on_track";
    let healthDetail = "";
    if (!latest) {
      health = "quiet";
      healthDetail = "No check-ins yet";
    } else if (latest.status === "Blocked") {
      let since = latest.created_at;
      for (const s of mine) {
        if (s.status !== "Blocked") break;
        since = s.created_at;
      }
      const days = Math.floor((now.getTime() - Date.parse(since)) / DAY);
      health = "blocked";
      healthDetail = days
        ? `Blocked for ${days} day${days === 1 ? "" : "s"}`
        : "Blocked since today";
    } else {
      const idle = Math.floor((now.getTime() - Date.parse(latest.created_at)) / DAY);
      if (idle >= QUIET_DAYS) {
        health = "quiet";
        healthDetail = `No check-in for ${idle} days`;
      }
    }

    return {
      id: st.id,
      startupId: st.id,
      cohortId: st.cohort_id ?? null,
      founderIds: people.map((p) => p.id),
      name: people.map((p) => p.name).join(", ") || "No founder linked yet",
      startup: st.tagline ? `${st.name} · ${st.tagline}` : st.name,
      stream: st.stream,
      lead: st.lead,
      status: latest?.status === "Blocked" ? "Blocked" : "In progress",
      digest: latest?.digest ?? "No check-ins yet.",
      time: latest ? relativeTime(latest.created_at, now) : "—",
      ...(latest ? { lastCheckInAt: latest.created_at } : {}),
      progress: latest?.progress ?? 0,
      audience: people[0]?.target_audience ?? "",
      stack: [],
      blocker: latest?.blocker ?? "None",
      profile: people[0]?.profile ?? "",
      transcript: latest?.raw_transcript ?? "",
      note: "",
      health,
      healthDetail,
    };
  });
  const order = { blocked: 0, quiet: 1, on_track: 2 } as const;
  return rows.sort(
    (a, b) =>
      order[a.health ?? "on_track"] - order[b.health ?? "on_track"] ||
      a.startup.localeCompare(b.startup),
  );
}

/** Why a startup needs a mentor's attention, or null when it's on track. Same rules as the Slack mentor view. */
export function attentionReason(f: Founder): string | null {
  if (f.health === "blocked")
    return f.blocker && f.blocker !== "None" ? f.blocker : f.healthDetail || "Blocked";
  if (f.health === "quiet") return f.healthDetail || "Quiet";
  return null;
}

/** A "handled" mark covers the check-in it was made against; a newer check-in reopens the item. */
export function isHandled(f: Founder, handledAt: string | undefined): boolean {
  if (!handledAt) return false;
  return !f.lastCheckInAt || Date.parse(handledAt) >= Date.parse(f.lastCheckInAt);
}
