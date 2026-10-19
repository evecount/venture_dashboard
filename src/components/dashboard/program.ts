import syllabusData from "../../data/syllabus.json";

export type SyllabusEvent = {
  date: string; // YYYY-MM-DD, studio local (SGT)
  day: string;
  week: number;
  phase: string;
  focus: string;
  activity: string;
  owner: string;
  deliverable: string;
};

export type ProgramWeek = {
  week: number;
  phase: string;
  deliverable: string;
  gateDate: string | null;
  events: SyllabusEvent[];
};

export type ProgramState = {
  week: number;
  totalWeeks: number;
  phase: string;
  deliverable: string;
  gateDate: string | null;
  daysToGate: number | null;
  upcoming: SyllabusEvent[];
  weeks: ProgramWeek[];
};

type RawRow = Record<string, string | null | undefined>;

const str = (value: string | null | undefined) => (typeof value === "string" ? value.trim() : "");

export function parseSyllabus(rows: RawRow[]): SyllabusEvent[] {
  return rows
    .filter((r) => str(r["Date"]) && /^WK \d+$/.test(str(r["Week"])))
    .map((r) => ({
      date: str(r["Date"]).slice(0, 10),
      day: str(r["Day"]),
      week: Number(str(r["Week"]).slice(3)),
      phase: str(r["Sprint Phase"]),
      focus: str(r["Module / Tactical Focus"]),
      activity: str(r["Exercise / Activity"]),
      owner: str(r["Owner / Lead"]),
      deliverable: str(r["Weekly Deliverable / Milestone"]),
    }))
    .sort((a, b) => a.date.localeCompare(b.date));
}

export const syllabus: SyllabusEvent[] = parseSyllabus(
  ((syllabusData as Record<string, unknown>)["Mamba_MVP_Official_Syllabus_Sch"] ?? []) as RawRow[],
);

/** Today's date in Singapore as YYYY-MM-DD, so the program week flips at local midnight. */
export function sgtDate(now: Date): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Singapore" }).format(now);
}

function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000);
}

/** Where the cohort is in the 12-week program, derived from the syllabus dates rather than hard-coded. */
export function programState(
  now: Date,
  events: SyllabusEvent[] = syllabus,
  upcomingCount = 4,
): ProgramState {
  const weeks: ProgramWeek[] = [];
  for (const e of events) {
    let w = weeks.find((x) => x.week === e.week);
    if (!w) {
      w = { week: e.week, phase: e.phase, deliverable: "", gateDate: null, events: [] };
      weeks.push(w);
    }
    w.events.push(e);
    if (e.deliverable) {
      w.deliverable = e.deliverable;
      w.gateDate = e.date;
    }
  }
  weeks.sort((a, b) => a.week - b.week);

  const today = sgtDate(now);
  // The current week is the first one whose gate (or last event) hasn't passed yet.
  const current =
    weeks.find((w) => (w.gateDate ?? w.events.at(-1)?.date ?? "") >= today) ?? weeks.at(-1);

  return {
    week: current?.week ?? 1,
    totalWeeks: weeks.length || 12,
    phase: current?.phase ?? "",
    deliverable: current?.deliverable ?? "",
    gateDate: current?.gateDate ?? null,
    daysToGate: current?.gateDate ? daysBetween(today, current.gateDate) : null,
    upcoming: events.filter((e) => e.date >= today).slice(0, upcomingCount),
    weeks,
  };
}

export function formatDay(
  date: string,
  opts: Intl.DateTimeFormatOptions = { weekday: "short", day: "numeric", month: "short" },
) {
  return new Date(`${date}T00:00:00Z`).toLocaleDateString("en-SG", { ...opts, timeZone: "UTC" });
}

export type SessionKind =
  "mentor" | "specialist" | "industry" | "office" | "prep" | "gate" | "holiday" | "other";

export type DaySession = {
  kind: SessionKind;
  title: string;
  length: string | null;
  about: string | null;
  build: string | null;
};

const dash = (t: string) => t.replace(/(\d)-(\d)/g, "$1–$2");

/**
 * Turns a syllabus line like "4-6 hrs build time + 45 min Mentor/Advisor Sync (Decisions/Accountability)" into
 * plain labels: what the session is, how long, what it covers and the build time. No owner titles.
 */
export function describeSession(e: Pick<SyllabusEvent, "activity" | "focus">): DaySession {
  const a = e.activity;
  const build = /^(\d+(?:-\d+)?\s*hrs?)\s+(build time|deep work)/i.exec(a);
  const buildLabel = build ? `${dash(build[1]!)} ${build[2]!.toLowerCase()}` : null;
  const len = (re: RegExp) => {
    const m = re.exec(a);
    return m ? dash(m[1]!) : null;
  };
  if (/holiday/i.test(a))
    return {
      kind: "holiday",
      title: "Public holiday",
      length: null,
      about: a.replace(/^.*?\(|\)$/g, ""),
      build: null,
    };
  if (/mentor\/advisor sync/i.test(a))
    return {
      kind: "mentor",
      title: "Mentor sync",
      length: len(/(\d+\s*min)\s+mentor/i),
      about: "Decisions and accountability",
      build: buildLabel,
    };
  if (/functional specialist/i.test(a))
    return {
      kind: "specialist",
      title: "Specialist session",
      length: len(/(\d+\s*min)\s+functional/i),
      about: "Product, engineering or go-to-market",
      build: buildLabel,
    };
  if (/industry specialist/i.test(a))
    return {
      kind: "industry",
      title: "Industry specialist",
      length: len(/(\d+\s*min)\s+industry/i),
      about: "Domain and customer insight",
      build: buildLabel,
    };
  if (/office hours/i.test(a))
    return {
      kind: "office",
      title: "Office hours",
      length: len(/^(\d+\s*hrs?)/i),
      about: "Dashboard review, unblocking and decisions",
      build: null,
    };
  if (/formal review/i.test(a))
    return {
      kind: "gate",
      title: "Gate review",
      length: len(/^(\d+-\d+\s*min)/i),
      about: "KPIs, evidence pack and a go / iterate / pivot decision",
      build: null,
    };
  if (/demo prep/i.test(a))
    return {
      kind: "prep",
      title: "Demo prep",
      length: null,
      about: "Analytics, demo prep and KPI dashboard update",
      build: null,
    };
  return {
    kind: "other",
    title: e.focus || "Session",
    length: null,
    about: a || null,
    build: buildLabel,
  };
}

/** "Sprint 1: Ideation, Concept Selection & Sprint 1 Review" -> { sprint: 1, theme: "Ideation, Concept Selection", review: true } */
export function splitPhase(phase: string): {
  sprint: number | null;
  theme: string;
  review: boolean;
} {
  const m = /^Sprint\s+(\d+):\s*(.*)$/i.exec(phase.trim());
  const rest = (m ? m[2]! : phase).trim();
  const review = /(&|\/)\s*Sprint\s+\d+\s+Review$/i.test(rest);
  const theme = rest.replace(/\s*(&|\/)\s*Sprint\s+\d+\s+Review$/i, "").trim();
  return { sprint: m ? Number(m[1]) : null, theme, review };
}

export type SprintSession = { date: string; sprint: number; week: number };

/** The fortnightly sprint session: Thursday of each sprint's second week (weeks 2, 4, 6…). */
export function sprintSessions(weeks: ProgramWeek[]): SprintSession[] {
  return weeks
    .filter((w) => w.week % 2 === 0)
    .flatMap((w) => {
      const thu = w.events.find((e) => e.day === "Thu");
      return thu ? [{ date: thu.date, sprint: w.week / 2, week: w.week }] : [];
    });
}

export function nextSprintSession(weeks: ProgramWeek[], today: string): SprintSession | null {
  return sprintSessions(weeks).find((s) => s.date >= today) ?? null;
}

/** "3:00 pm" in Singapore time. */
export function sgtTime(iso: string): string {
  return new Date(iso)
    .toLocaleTimeString("en-SG", {
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
      timeZone: "Asia/Singapore",
    })
    .replace(/\s?([ap])\.?m\.?/i, " $1m")
    .toLowerCase();
}

/** "15:00" in Singapore time, for sorting within a day. */
export function sgtClock(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: "Asia/Singapore",
  }).format(new Date(iso));
}

/** The Monday of week 1 for a cohort, in Singapore time ("2026-10-18T16:00:00+00:00" -> "2026-10-19"). */
export function cohortStartMonday(startDate: string): string {
  const d = startDate.includes("T") ? sgtDate(new Date(startDate)) : startDate.slice(0, 10);
  const t = Date.parse(`${d}T00:00:00Z`);
  const back = (new Date(t).getUTCDay() + 6) % 7;
  return new Date(t - back * 86_400_000).toISOString().slice(0, 10);
}

/** The syllabus moved onto a cohort's own calendar (same weeks and days, starting `startMonday`). */
export function shiftSyllabus(events: SyllabusEvent[], startMonday: string): SyllabusEvent[] {
  if (!events.length) return events;
  const base = cohortStartMonday(events[0]!.date);
  const offset = Date.parse(`${startMonday}T00:00:00Z`) - Date.parse(`${base}T00:00:00Z`);
  if (!offset) return events;
  return events.map((e) => ({
    ...e,
    date: new Date(Date.parse(`${e.date}T00:00:00Z`) + offset).toISOString().slice(0, 10),
  }));
}

/** Where a cohort is in the program today. Same rule as the bot's cohorts.py. */
export function cohortProgram(now: Date, startDate: string | null | undefined): ProgramState {
  return programState(
    now,
    startDate ? shiftSyllabus(syllabus, cohortStartMonday(startDate)) : syllabus,
  );
}
