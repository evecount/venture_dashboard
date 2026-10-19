import { describe, expect, it } from "vitest";
import { programState } from "@/components/dashboard/program";
import {
  blockedDays,
  checkinStreak,
  expectedProgress,
  gateStatus,
  goalValue,
  milestoneValue,
  upcomingMilestones,
  weeklyProgress,
} from "@/components/dashboard/insights";

// Wed 14 Oct 2026, 10:00 SGT: week 2 runs Mon 12 to the gate on Fri 16.
const now = new Date("2026-10-14T02:00:00Z");
const program = programState(now);
const wk2 = program.weeks.find((w) => w.week === 2)!;
const sub = (over: Record<string, unknown>) => ({
  startup_id: "s1",
  deliverable_id: "del-wk02",
  status: "In progress",
  progress: 50,
  created_at: "2026-10-13T03:00:00Z",
  ...over,
});

describe("gate readiness", () => {
  it("expects steady progress from the week's first day to the gate", () => {
    expect(expectedProgress(wk2, new Date("2026-10-12T02:00:00Z"))).toBe(0);
    expect(expectedProgress(wk2, now)).toBe(50);
    expect(expectedProgress(wk2, new Date("2026-10-16T02:00:00Z"))).toBe(100);
  });

  it("classifies each startup for the gate", () => {
    const at = (subs: Record<string, unknown>[]) =>
      gateStatus("s1", wk2, subs.map(sub), [], now).state;
    expect(at([])).toBe("no_update");
    expect(at([{ progress: 60 }])).toBe("on_track");
    expect(at([{ progress: 10 }])).toBe("behind");
    expect(at([{ status: "Blocked" }])).toBe("blocked");
    expect(at([{ status: "Completed", progress: 100 }])).toBe("submitted");
    // A check-in about last week's deliverable doesn't count towards this gate.
    expect(at([{ deliverable_id: "del-wk01", progress: 90 }])).toBe("no_update");
  });

  it("counts check-ins, work and meetings inside the gate week only", () => {
    const g = gateStatus(
      "s1",
      wk2,
      [sub({}), sub({ created_at: "2026-10-02T03:00:00Z" })],
      [
        { startup_id: "s1", type: "commit", weight: 4, created_at: "2026-10-13T05:00:00Z" },
        { startup_id: "s1", type: "pull_request", weight: 1, created_at: "2026-10-13T06:00:00Z" },
        { startup_id: "s1", type: "meeting", weight: 2, created_at: "2026-10-12T06:00:00Z" },
        { startup_id: "s1", type: "commit", weight: 9, created_at: "2026-10-05T05:00:00Z" },
        { startup_id: "s2", type: "commit", weight: 9, created_at: "2026-10-13T05:00:00Z" },
      ],
      now,
    );
    expect([g.checkins, g.work, g.meetings]).toEqual([1, 5, 2]);
  });

  it("marks a passed gate with no submission as behind", () => {
    const later = new Date("2026-10-20T02:00:00Z");
    expect(gateStatus("s1", wk2, [], [], later).state).toBe("behind");
  });
});

describe("trends", () => {
  it("keeps the latest progress per week's deliverable", () => {
    const subs = [
      sub({ deliverable_id: "del-wk01", progress: 80, created_at: "2026-10-08T03:00:00Z" }),
      sub({ deliverable_id: "del-wk01", progress: 100, created_at: "2026-10-09T03:00:00Z" }),
      sub({ progress: 40 }),
    ];
    const series = weeklyProgress("s1", subs, program.weeks);
    expect(series.slice(0, 3)).toEqual([
      { week: 1, progress: 100 },
      { week: 2, progress: 40 },
      { week: 3, progress: null },
    ]);
  });

  it("counts a check-in streak without breaking it mid-week", () => {
    const wk1 = sub({ created_at: "2026-10-07T03:00:00Z" });
    expect(checkinStreak("s1", [wk1], program, now)).toBe(1); // week 2 still in play
    expect(checkinStreak("s1", [wk1, sub({})], program, now)).toBe(2);
    expect(checkinStreak("s1", [], program, now)).toBe(0);
  });

  it("adds up time spent blocked", () => {
    const subs = [
      sub({ status: "Blocked", created_at: "2026-10-05T02:00:00Z" }),
      sub({ status: "Blocked", created_at: "2026-10-06T02:00:00Z" }),
      sub({ status: "In progress", created_at: "2026-10-08T02:00:00Z" }),
      sub({ status: "Blocked", created_at: "2026-10-13T02:00:00Z" }),
    ];
    expect(blockedDays("s1", subs, now)).toBe(4); // 3 days, then 1 day and counting
  });
});

describe("coming up", () => {
  it("lists open milestones earliest due first, undated last, with overdue flagged", () => {
    const m = (id: string, due_date: string | null, status = "open") => ({
      id,
      startup_id: "s1",
      due_date,
      status,
    });
    const out = upcomingMilestones(
      [
        m("late", "2026-10-30"),
        m("none", null),
        m("done", "2026-10-01", "done"),
        m("soon", "2026-10-16"),
        m("past", "2026-10-10"),
        m("today", "2026-10-14"),
      ],
      "2026-10-14",
    );
    expect(out.map((x) => x.id)).toEqual(["past", "today", "soon", "late", "none"]);
    expect(out[0]!.overdue).toBe(true);
    expect(out[1]!.dueToday).toBe(true);
  });
});

describe("goal progress with GitHub estimates", () => {
  it("shows done as 100, then the estimate, then official progress", () => {
    expect(goalValue({ done: true, est_progress: 40 })).toEqual({ pct: 100, estimated: false });
    expect(goalValue({ done: false, progress: 20, est_progress: 60 })).toEqual({
      pct: 60,
      estimated: true,
    });
    expect(goalValue({ done: false, progress: 30 })).toEqual({ pct: 30, estimated: false });
    expect(milestoneValue([{ done: true }, { done: false, est_progress: 50 }])).toEqual({
      pct: 75,
      estimated: true,
    });
  });
});

describe("milestones without goals", () => {
  it("use their own progress and estimate", () => {
    expect(milestoneValue([], { status: "open", est_progress: 40 })).toEqual({
      pct: 40,
      estimated: true,
    });
    expect(milestoneValue([], { status: "done" })).toEqual({ pct: 100, estimated: false });
    expect(milestoneValue([])).toEqual({ pct: 0, estimated: false });
  });
});
