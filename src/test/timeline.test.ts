import { describe, expect, it } from "vitest";
import { entryGroup, mergeTimeline, workSummary } from "@/hooks/use-timeline";

const NOW = Date.parse("2026-10-15T08:00:00Z");
const sub = (id: string, at: string, status = "In progress") => ({
  id,
  status,
  progress: 50,
  blocker: null,
  digest: `digest ${id}`,
  created_at: at,
});
const sig = (id: string, type: string, at: string, extra: Record<string, unknown> = {}) => ({
  id,
  type,
  headline: `${type} ${id}`,
  detail: null,
  created_at: at,
  ...extra,
});

describe("startup timeline", () => {
  const entries = mergeTimeline(
    [sub("a", "2026-10-14T10:00:00Z"), sub("b", "2026-10-13T10:00:00Z", "Blocked")],
    [
      sig("c1", "commit", "2026-10-14T09:00:00Z", { weight: 3 }),
      sig("c2", "commit", "2026-10-13T09:00:00Z", { weight: 2 }),
      sig("p1", "pull_request", "2026-10-14T08:00:00Z", { merged: true }),
      sig("p2", "pull_request", "2026-10-14T07:00:00Z", { merged: false }),
      sig("m1", "meeting", "2026-10-12T09:00:00Z", { weight: 4 }),
      sig("old", "commit", "2026-09-01T09:00:00Z", { weight: 50 }),
    ],
  );

  it("keeps the signal type so code and meetings can be told apart", () => {
    expect(entries.map((e) => e.type ?? e.kind)).toContain("pull_request");
    expect(entryGroup(entries.find((e) => e.id === "sig-c1")!)).toBe("code");
    expect(entryGroup(entries.find((e) => e.id === "sig-m1")!)).toBe("meeting");
    expect(entryGroup(entries.find((e) => e.id === "sub-a")!)).toBe("checkin");
    expect(entryGroup(entries.find((e) => e.id === "sub-b")!)).toBe("checkin");
  });

  it("is newest first", () => {
    const times = entries.map((e) => Date.parse(e.at));
    expect([...times].sort((a, b) => b - a)).toEqual(times);
  });

  it("summarises the last 7 days: commits, merged PRs and meetings only", () => {
    expect(workSummary(entries, NOW)).toEqual({ commits: 5, prsMerged: 1, meetings: 4 });
  });

  it("treats a startup with no work signals as zeros", () => {
    expect(workSummary(mergeTimeline([sub("a", "2026-10-14T10:00:00Z")], []), NOW)).toEqual({
      commits: 0,
      prsMerged: 0,
      meetings: 0,
    });
  });
});
