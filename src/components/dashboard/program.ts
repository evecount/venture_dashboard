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
