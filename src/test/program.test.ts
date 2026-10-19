import { describe, expect, it } from "vitest";
import {
  cohortProgram,
  cohortStartMonday,
  describeSession,
  nextSprintSession,
  programState,
  sgtDate,
  splitPhase,
  sprintSessions,
  syllabus,
} from "@/components/dashboard/program";
import { attentionReason, isHandled } from "@/components/dashboard/roster";
import type { Founder } from "@/components/dashboard/data";

describe("program week", () => {
  it("reads the current week and gate from the syllabus instead of hard-coding them", () => {
    // Wed 14 Oct 2026, 10:00 SGT: week 2, gate Fri 16 Oct.
    const p = programState(new Date("2026-10-14T02:00:00Z"));
    expect(p.week).toBe(2);
    expect(p.totalWeeks).toBe(12);
    expect(p.gateDate).toBe("2026-10-16");
    expect(p.daysToGate).toBe(2);
    expect(p.deliverable).toMatch(/Sprint 1 evidence pack/);
    expect(p.upcoming[0]?.date).toBe("2026-10-14");
  });

  it("keeps the gate day in its own week and moves on the day after", () => {
    expect(programState(new Date("2026-10-16T08:00:00Z")).week).toBe(2);
    expect(programState(new Date("2026-10-16T08:00:00Z")).daysToGate).toBe(0);
    expect(programState(new Date("2026-10-17T02:00:00Z")).week).toBe(3);
  });

  it("uses Singapore dates, not UTC", () => {
    // 20:00 UTC on the 13th is already the 14th in Singapore.
    expect(sgtDate(new Date("2026-10-13T20:00:00Z"))).toBe("2026-10-14");
  });

  it("parses all 12 weeks", () => {
    expect(new Set(syllabus.map((e) => e.week)).size).toBe(12);
  });
});

describe("attention queue", () => {
  const base = {
    stack: [],
    name: "A",
    startup: "S",
    stream: "Tech",
    lead: "L",
    status: "In progress",
    digest: "",
    time: "",
    progress: 0,
    audience: "",
    blocker: "None",
    profile: "",
    transcript: "",
    note: "",
  } as const;
  const f = (over: Partial<Founder>): Founder => ({ id: "s1", ...base, stack: [], ...over });

  it("only lists blocked or quiet startups", () => {
    expect(attentionReason(f({ health: "on_track" }))).toBeNull();
    expect(attentionReason(f({ health: "quiet", healthDetail: "No check-ins yet" }))).toBe(
      "No check-ins yet",
    );
    expect(attentionReason(f({ health: "blocked", blocker: "Need AWS credits" }))).toBe(
      "Need AWS credits",
    );
    expect(
      attentionReason(
        f({ health: "blocked", blocker: "None", healthDetail: "Blocked for 2 days" }),
      ),
    ).toBe("Blocked for 2 days");
  });

  it("reopens a handled item when a newer check-in arrives", () => {
    const blocked = f({ health: "blocked", lastCheckInAt: "2026-10-13T10:00:00Z" });
    expect(isHandled(blocked, undefined)).toBe(false);
    expect(isHandled(blocked, "2026-10-13T11:00:00Z")).toBe(true);
    expect(
      isHandled({ ...blocked, lastCheckInAt: "2026-10-13T12:00:00Z" }, "2026-10-13T11:00:00Z"),
    ).toBe(false);
    expect(isHandled(f({ health: "quiet" }), "2026-10-13T11:00:00Z")).toBe(true);
  });
});

describe("plain schedule labels", () => {
  it("describes every syllabus day without owner titles", () => {
    for (const e of syllabus) {
      const d = describeSession(e);
      expect(d.kind).not.toBe("other");
      expect(`${d.title} ${d.about} ${d.build}`).not.toMatch(
        /Founders \/|Functional Lead|Industry Lead|Program Lead/,
      );
    }
    const mon = describeSession(syllabus[0]!);
    expect(mon).toMatchObject({
      kind: "mentor",
      title: "Mentor sync",
      length: "45 min",
      build: "4–6 hrs build time",
    });
    const review = syllabus.find((e) => /formal review/i.test(e.activity))!;
    expect(describeSession(review)).toMatchObject({ kind: "gate", length: "60–90 min" });
  });

  it("splits a sprint phase into number, theme and review week", () => {
    expect(splitPhase("Sprint 1: Ideation, Concept Selection & Sprint 1 Review")).toEqual({
      sprint: 1,
      theme: "Ideation, Concept Selection",
      review: true,
    });
    expect(splitPhase("Sprint 5: MVP Build Sprint I")).toEqual({
      sprint: 5,
      theme: "MVP Build Sprint I",
      review: false,
    });
    expect(splitPhase("Sprint 6: Iterate, Demo & 90-Day Scale Plan / Sprint 6 Review").review).toBe(
      true,
    );
  });
});

describe("fortnightly sprint session", () => {
  const { weeks } = programState(new Date("2026-10-15T02:00:00Z"));
  it("falls on the Thursday of each sprint's second week", () => {
    expect(
      sprintSessions(weeks)
        .map((x) => x.date)
        .slice(0, 3),
    ).toEqual(["2026-10-15", "2026-10-29", "2026-11-12"]);
    expect(sprintSessions(weeks)[0]).toMatchObject({ sprint: 1, week: 2 });
  });
  it("finds the next one, counting today", () => {
    expect(nextSprintSession(weeks, "2026-10-15")?.date).toBe("2026-10-15");
    expect(nextSprintSession(weeks, "2026-10-16")?.date).toBe("2026-10-29");
  });
});

describe("cohorts on their own calendars", () => {
  const monday = new Date("2026-10-19T02:00:00Z"); // Mon 19 Oct, 10:00 SGT
  it("finds each cohort's start Monday in Singapore time", () => {
    expect(cohortStartMonday("2026-10-18T16:00:00+00:00")).toBe("2026-10-19");
    expect(cohortStartMonday("2026-10-04T16:00:00+00:00")).toBe("2026-10-05");
    expect(cohortStartMonday("2026-10-21")).toBe("2026-10-19");
  });
  it("puts MVP#1 in week 3 and MVP#2 in week 1 on the same day", () => {
    const one = cohortProgram(monday, "2026-10-04T16:00:00+00:00");
    const two = cohortProgram(monday, "2026-10-18T16:00:00+00:00");
    expect([one.week, one.gateDate]).toEqual([3, "2026-10-23"]);
    expect([two.week, two.gateDate]).toEqual([1, "2026-10-23"]);
    expect(two.deliverable).toMatch(/venture thesis/);
    expect(nextSprintSession(two.weeks, "2026-10-19")?.date).toBe("2026-10-29");
  });
});
