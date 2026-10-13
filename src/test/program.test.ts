import { describe, expect, it } from "vitest";
import { programState, sgtDate, syllabus } from "@/components/dashboard/program";
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
