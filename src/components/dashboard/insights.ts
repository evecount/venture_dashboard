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
  /** Set when progress is measured against the startup's milestones (see milestoneProgress); absent = check-in based. */
  milestone?: MilestoneProgress;
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
  milestones: ProgressMilestone[] = [],
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

  // This week, a startup with milestones is measured against THEM, not against the program's deliverable.
  // (Past and future weeks keep the check-in based reading: milestone completion has no history to replay.)
  const mp =
    milestones.length && today >= start && dayNum(today) <= dayNum(end) + 2
      ? milestoneProgress(milestones, startupId, today)
      : null;
  if (mp) {
    const last = mine[0];
    const withMp = {
      ...base,
      progress: mp.pct,
      expected: mp.expected,
      milestone: mp,
      lastUpdate: last?.created_at ?? null,
    };
    if (last?.status === "Blocked")
      return { ...withMp, state: "blocked", reason: "Blocked on the latest check-in" };
    if (mp.complete === mp.counted)
      return { ...withMp, state: "submitted", reason: "All current milestones are complete" };
    if (base.checkins + base.work + base.meetings === 0)
      return { ...withMp, state: "no_update", reason: "No check-in or work logged this week yet" };
    const detail = `${mp.pct}% across ${mp.counted} milestone${mp.counted === 1 ? "" : "s"}${mp.overdue ? ` · ${mp.overdue} overdue` : ""}`;
    return {
      ...withMp,
      state: mp.pct < mp.expected - 25 ? "behind" : "on_track",
      reason: `${detail}, about ${mp.expected}% expected by now`,
    };
  }

  // A finished week with milestones due in it: judge it by how many of those got done (their state today).
  const wasDue =
    today > end && milestones.length
      ? milestones.filter((m) => {
          const d = m.due_date?.slice(0, 10);
          return (
            m.startup_id === startupId &&
            m.status !== "dropped" &&
            !!d &&
            dayNum(d) > dayNum(start) - 3 &&
            d <= end
          );
        })
      : [];
  if (wasDue.length) {
    const pct = Math.round(wasDue.reduce((n, m) => n + milestoneOwn(m).pct, 0) / wasDue.length);
    const finished = wasDue.filter((m) => isMilestoneComplete(m)).length;
    const plural = wasDue.length === 1 ? "" : "s";
    return finished === wasDue.length
      ? {
          ...base,
          progress: pct,
          expected: 100,
          state: "submitted",
          reason: `All ${wasDue.length} milestone${plural} due that week were finished`,
        }
      : {
          ...base,
          progress: pct,
          expected: 100,
          state: "behind",
          reason: `${pct}% of the ${wasDue.length} milestone${plural} due that week (${finished} finished)`,
        };
  }

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

type ProgressMilestone = MilestoneLike & {
  title?: string;
  progress?: number | null;
  est_progress?: number | null;
  goals?: { done: boolean; progress?: number | null; est_progress?: number | null }[];
};

export type MilestoneProgress = {
  /** Average completion of the milestones in play (goals done, partial progress and GitHub estimates included). */
  pct: number;
  /** Where they should be by now: past-due milestones count as 100, the ones due this week ramp up to 100 on the due day. */
  expected: number;
  estimated: boolean;
  counted: number;
  complete: number;
  overdue: number;
  /** The one to work on next: the oldest overdue, else the next one due. */
  focus: {
    title: string;
    due: string | null;
    pct: number;
    expected: number;
    overdue: boolean;
  } | null;
};

const HORIZON_DAYS = 7; // milestones due within the next week are in play
const RECENT_DAYS = 21; // finished milestones stay in the picture for three weeks, then make room

/** A milestone is expected to be worked on during its last week: 0 before that, 100 on the due day and after. */
export function milestoneExpected(due: string | null, today: string): number {
  if (!due) return 0;
  if (due <= today) return 100;
  const into = dayNum(today) - (dayNum(due) - 6);
  return into <= 0 ? 0 : Math.round((into / 6) * 100);
}

function milestoneOwn(m: ProgressMilestone) {
  return isMilestoneComplete(m) ? { pct: 100, estimated: false } : milestoneValue(m.goals ?? [], m);
}

/**
 * How a startup is doing against the milestones it was actually given.
 * In play: everything unfinished that is due within the next week (or has no date), plus what was finished in the last
 * three weeks. Far-off milestones don't dilute the number and long-finished ones don't inflate it.
 * null when there is nothing to measure (the caller falls back to check-in progress).
 */
export function milestoneProgress(
  milestones: ProgressMilestone[],
  startupId: string,
  today: string,
): MilestoneProgress | null {
  const mine = milestones.filter((m) => m.startup_id === startupId && m.status !== "dropped");
  const day = (m: ProgressMilestone) => (m.due_date ? m.due_date.slice(0, 10) : null);
  const inPlay = mine.filter((m) => {
    const due = day(m);
    if (due && dayNum(due) > dayNum(today) + HORIZON_DAYS) return false;
    if (isMilestoneComplete(m)) return !!due && dayNum(due) >= dayNum(today) - RECENT_DAYS;
    return true;
  });
  if (!inPlay.length) {
    return mine.length && mine.every((m) => isMilestoneComplete(m))
      ? {
          pct: 100,
          expected: 100,
          estimated: false,
          counted: 0,
          complete: 0,
          overdue: 0,
          focus: null,
        }
      : null;
  }
  const rows = inPlay.map((m) => {
    const v = milestoneOwn(m);
    const due = day(m);
    return { m, due, v, exp: milestoneExpected(due, today), complete: isMilestoneComplete(m) };
  });
  const avg = (f: (r: (typeof rows)[number]) => number) =>
    Math.round(rows.reduce((n, r) => n + f(r), 0) / rows.length);
  const open = rows
    .filter((r) => !r.complete)
    .sort((a, b) => (a.due ?? "9999").localeCompare(b.due ?? "9999"));
  const first = open[0];
  return {
    pct: avg((r) => r.v.pct),
    expected: avg((r) => r.exp),
    estimated: rows.some((r) => r.v.estimated),
    counted: rows.length,
    complete: rows.filter((r) => r.complete).length,
    overdue: open.filter((r) => r.due !== null && r.due < today).length,
    focus: first
      ? {
          title: first.m.title ?? "Milestone",
          due: first.due,
          pct: first.v.pct,
          expected: first.exp,
          overdue: first.due !== null && first.due < today,
        }
      : null,
  };
}

/**
 * The per-week bars: how complete the milestones that fall due in each program week are (null where none fall due).
 * Startups with no dated milestones keep the check-in based bars.
 */
export function weeklySeries(
  startupId: string,
  subs: SubLike[],
  milestones: ProgressMilestone[],
  weeks: ProgramWeek[],
): { series: { week: number; progress: number | null }[]; mode: "milestones" | "checkins" } {
  const dated = milestones.filter(
    (m) => m.startup_id === startupId && m.status !== "dropped" && m.due_date,
  );
  let prevEnd = "";
  const series = weeks.map((w) => {
    const { end } = weekWindow(w);
    const due = dated.filter((m) => {
      const d = m.due_date!.slice(0, 10);
      return d > prevEnd && d <= end;
    });
    prevEnd = end || prevEnd;
    return {
      week: w.week,
      progress: due.length
        ? Math.round(due.reduce((n, m) => n + milestoneOwn(m).pct, 0) / due.length)
        : null,
    };
  });
  return series.some((s) => s.progress !== null)
    ? { series, mode: "milestones" }
    : { series: weeklyProgress(startupId, subs, weeks), mode: "checkins" };
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

type SetupLike = {
  founder_id: string;
  startup_id: string;
  slack: boolean;
  github: boolean;
  github_pending?: boolean;
  calendar: boolean;
};

/**
 * What a startup still hasn't set up, in plain words for mentors to chase. Calendar sharing is optional, so it
 * only shows once the essentials are done. Empty when everything is in place (or nothing is known).
 */
export function setupGaps(
  startupId: string,
  setup: SetupLike[],
  founders: { id: string; name: string; startup_id: string }[],
  milestones: { startup_id: string; status: string }[],
): string[] {
  const mine = setup.filter((s) => s.startup_id === startupId);
  if (!mine.length) return [];
  const nameOf = new Map(founders.map((f) => [f.id, f.name]));
  const gaps = mine
    .filter((s) => !s.slack)
    .map((s) => `${nameOf.get(s.founder_id) ?? "A founder"} isn't linked to the Slack bot yet`);
  if (!mine.some((s) => s.github))
    gaps.push(
      mine.some((s) => s.github_pending)
        ? "GitHub connected, but no repo is being tracked yet"
        : "No GitHub repo connected",
    );
  if (!milestones.some((m) => m.startup_id === startupId && m.status !== "dropped"))
    gaps.push("No milestones yet");
  if (!gaps.length && !mine.some((s) => s.calendar)) gaps.push("Calendar not shared (optional)");
  return gaps;
}
