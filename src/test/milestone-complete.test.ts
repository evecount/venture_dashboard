import { describe, expect, it } from "vitest";
import { isMilestoneComplete, upcomingMilestones } from "@/components/dashboard/insights";
import { progressScope } from "@/components/dashboard/timeline";
import { mergeTimeline } from "@/hooks/use-timeline";

const m = (status: string, goals: boolean[]) => ({
  id: status + goals.join(),
  startup_id: "s",
  due_date: "2026-10-16",
  status,
  goals: goals.map((done) => ({ done })),
});

describe("milestone completion", () => {
  it("counts a milestone whose goals are all ticked as complete even if never marked done", () => {
    expect(isMilestoneComplete(m("open", [true, true]))).toBe(true);
    expect(isMilestoneComplete(m("open", [true, false]))).toBe(false);
    expect(isMilestoneComplete(m("open", []))).toBe(false);
    expect(isMilestoneComplete(m("done", []))).toBe(true);
  });
  it("keeps finished milestones out of the upcoming list", () => {
    const list = upcomingMilestones([m("open", [true, true]), m("open", [true, false])], "2026-10-19");
    expect(list).toHaveLength(1);
    expect(list[0]!.overdue).toBe(true);
  });
});

describe("timeline progress label", () => {
  const entry = (deliverableId?: string) => mergeTimeline(
    [{ id: "1", status: "On Track", progress: 60, blocker: null, digest: "d", created_at: "2026-10-16T03:00:00Z", deliverable_id: deliverableId ?? null }], [])[0]!;
  const week3 = new Date("2026-10-19T02:00:00Z");
  it("names the week when the last check-in is for an earlier deliverable", () => {
    expect(progressScope(entry("del-wk02"), week3)).toBe("on week 2's deliverable (last check-in)");
  });
  it("says current deliverable only for this week's", () => {
    expect(progressScope(entry("del-wk03"), week3)).toBe("on current deliverable");
  });
});
