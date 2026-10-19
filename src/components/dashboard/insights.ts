// Pure calculations behind gate readiness, trends and ownership. No React, no fetching: easy to test.
import { sgtDate, type ProgramState, type ProgramWeek } from "./program";

export type SubLike = {
  startup_id: string;
  deliverable_id?: string | null;
  status: string;
  progress: number | null;
  artifact_url?: string | null;
  created_at: string;
};
export type SignalLike = {
  startup_id: string | null;
  type: string;
  weight?: number;
  created_at: string;
};

export type GateState = "submitted" | "on_track" | "behind" | "blocked" | "no_update" | "upcoming";

export type GateStatus = {
  week: number;
  state: GateState;
  progress: number | null;
  expected: number;
  checkins: number;
  work: number;
  meetings: number;
  lastUpdate: string | null;
  reason: string;
};

export const GATE_LABEL: Record<GateState, string> = {
  submitted: "Submitted",
  on_track: "On track",
  behind: "Behind",
  blocked: "Blocked",
  no_update: "No update",
  upcoming: "Upcoming",
};

const WORK_TYPES = new Set(["commit", "pull_request", "issue"]);
const DAY = 86_400_000;

/** Matches the deliverables table and the bot (syllabus.py current_deliverable): del-wk01 … del-wk12. */
export const deliverableId = (week: number) => `del-wk${String(week).padStart(2, "0")}`;

export function weekWindow(w: ProgramWeek): { start: string; end: string } {
  const start = w.events[0]?.date ?? w.gateDate ?? "";
  return { start, end: w.gateDate ?? w.events.at(-1)?.date ?? start };
}

const dayNum = (d: string) => Date.parse(`${d}T00:00:00Z`) / DAY;

/** How far along a startup should be by now, as a straight line from the week's first day to its gate. */
export function expectedProgress(w: ProgramWeek, now: Date): number {
  const { start, end } = weekWindow(w);
  const today = sgtDate(now);
  if (today < start) return 0;
  if (today >= end) return 100;
  const span = Math.max(1, dayNum(end) - dayNum(start));
  return Math.round(((dayNum(today) - dayNum(start)) / span) * 100);
}

export function gateStatus(
  startupId: string,
  w: ProgramWeek,
  subs: SubLike[],
  signals: SignalLike[],
  now: Date,
): GateStatus {
  const { start, end } = weekWindow(w);
  const today = sgtDate(now);
  const inWindow = (iso: string) => {
    const d = sgtDate(new Date(iso));
    return d >= start && d <= end;
  };
  const mine = subs
    .filter((s) => s.startup_id === startupId)
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  const forGate = mine.filter((s) => s.deliverable_id === deliverableId(w.week));
  const sigs = signals.filter((s) => s.startup_id === startupId && inWindow(s.created_at));
  const latest = forGate[0];
  const expected = expectedProgress(w, now);
  const base = {
    week: w.week,
    progress: latest?.progress ?? null,
    expected,
    checkins: mine.filter((s) => inWindow(s.created_at)).length,
    work: sigs.filter((s) => WORK_TYPES.has(s.type)).reduce((n, s) => n + (s.weight ?? 1), 0),
    meetings: sigs.filter((s) => s.type === "meeting").reduce((n, s) => n + (s.weight ?? 1), 0),
    lastUpdate: latest?.created_at ?? null,
  };

  const submitted = forGate.some(
    (s) => s.status === "Completed" || (s.progress ?? 0) >= 100 || !!s.artifact_url,
  );
  if (submitted) return { ...base, state: "submitted", reason: "Deliverable marked complete" };
  if (today < start) return { ...base, state: "upcoming", reason: "Not started yet" };
  if (latest?.status === "Blocked")
    return { ...base, state: "blocked", reason: "Blocked on the latest check-in" };
  if (!latest) {
    return {
      ...base,
      state: today > end ? "behind" : "no_update",
      reason: today > end ? "Gate passed with no update" : "No check-in on this deliverable yet",
    };
  }
  const progress = latest.progress ?? 0;
  if (today > end) return { ...base, state: "behind", reason: `Gate passed at ${progress}%` };
  if (progress < expected - 25) {
    return {
      ...base,
      state: "behind",
      reason: `${progress}% done, about ${expected}% expected by now`,
    };
  }
  return {
    ...base,
    state: "on_track",
    reason: `${progress}% done, about ${expected}% expected by now`,
  };
}

/** Latest progress reported on each week's deliverable (null when nothing was reported). */
export function weeklyProgress(startupId: string, subs: SubLike[], weeks: ProgramWeek[]) {
  return weeks.map((w) => {
    const forGate = subs
      .filter((s) => s.startup_id === startupId && s.deliverable_id === deliverableId(w.week))
      .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
    return { week: w.week, progress: forGate[0]?.progress ?? null };
  });
}

/** Consecutive program weeks, counting back from now, with at least one check-in. */
export function checkinStreak(
  startupId: string,
  subs: SubLike[],
  program: ProgramState,
  now: Date,
): number {
  const days = new Set(
    subs.filter((s) => s.startup_id === startupId).map((s) => sgtDate(new Date(s.created_at))),
  );
  const has = (w: ProgramWeek) => {
    const { start, end } = weekWindow(w);
    for (const d of days) if (d >= start && d <= end) return true;
    return false;
  };
  const past = program.weeks.filter((w) => w.week <= program.week).reverse();
  // This week only breaks the streak once its gate has passed; until then it's still in play.
  const current = past[0];
  let i = current && !has(current) && sgtDate(now) <= weekWindow(current).end ? 1 : 0;
  let streak = 0;
  for (; i < past.length && has(past[i]!); i++) streak++;
  return streak;
}

/** Total days spent blocked: from each "Blocked" check-in until the next check-in that isn't (or now). */
export function blockedDays(startupId: string, subs: SubLike[], now: Date): number {
  const mine = subs
    .filter((s) => s.startup_id === startupId)
    .sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at));
  let total = 0;
  let since: number | null = null;
  for (const s of mine) {
    const t = Date.parse(s.created_at);
    if (s.status === "Blocked") since ??= t;
    else if (since !== null) {
      total += t - since;
      since = null;
    }
  }
  if (since !== null) total += now.getTime() - since;
  return Math.round(total / DAY);
}

type MilestoneLike = {
  id: string;
  startup_id: string;
  due_date: string | null;
  status: string;
  goals?: { done: boolean }[];
};

/** Finished: marked done, or it has goals and every one is ticked (older milestones were never marked done). */
export function isMilestoneComplete(m: Pick<MilestoneLike, "status" | "goals">): boolean {
  return m.status === "done" || (!!m.goals?.length && m.goals.every((g) => g.done));
}

/** Open milestones, earliest due first and undated last, flagged when overdue or due today (SGT date). */
export function upcomingMilestones<M extends MilestoneLike>(milestones: M[], today: string) {
  return milestones
    .filter((m) => m.status === "open" && !isMilestoneComplete(m))
    .map((m) => {
      const due = m.due_date ? m.due_date.slice(0, 10) : null;
      return { ...m, due_date: due, overdue: !!due && due < today, dueToday: due === today };
    })
    .sort((a, b) =>
      a.due_date === b.due_date
        ? 0
        : a.due_date === null
          ? 1
          : b.due_date === null
            ? -1
            : a.due_date.localeCompare(b.due_date),
    );
}

type GoalLike = { done: boolean; progress?: number | null; est_progress?: number | null };

/** Same rule as the bot (progress_estimator.goal_value): done = 100; else the GitHub estimate if any; else official. */
export function goalValue(g: GoalLike): { pct: number; estimated: boolean } {
  if (g.done) return { pct: 100, estimated: false };
  if (g.est_progress != null) return { pct: g.est_progress, estimated: true };
  return { pct: g.progress ?? 0, estimated: false };
}

/** Average of the goals. A milestone with no goals carries its own progress and estimate instead (same as the bot). */
export function milestoneValue(
  goals: GoalLike[],
  own?: { status?: string; progress?: number | null; est_progress?: number | null },
): { pct: number; estimated: boolean } {
  if (!goals.length)
    return own ? goalValue({ ...own, done: own.status === "done" }) : { pct: 0, estimated: false };
  const vals = goals.map(goalValue);
  return {
    pct: Math.round(vals.reduce((n, v) => n + v.pct, 0) / vals.length),
    estimated: vals.some((v) => v.estimated),
  };
}
