import { describe, expect, it } from "vitest";
import { buildRoster } from "@/components/dashboard/roster";
import { parsePerspective } from "@/components/dashboard/data";

const now = new Date("2026-10-13T12:00:00Z");
const startups = [
  { id: "s-a", name: "Alpha", stream: "GTM", lead: "L" },
  { id: "s-b", name: "Beta", stream: "Tech", lead: "L" },
  { id: "s-c", name: "Gamma", stream: "Unassigned", lead: "Unassigned" },
];
const founders = [
  { id: "f1", name: "Ann", startup_id: "s-a" },
  { id: "f2", name: "Bob", startup_id: "s-a" },
  { id: "f3", name: "Cy", startup_id: "s-b" },
];
const sub = (startup_id: string, status: string, created_at: string, progress = 50) => ({
  startup_id,
  founder_id: null,
  status,
  progress,
  blocker: status === "Blocked" ? "stuck" : "None",
  digest: "d",
  created_at,
});

describe("live roster", () => {
  it("matches the Slack health rules and ordering", () => {
    const roster = buildRoster(
      startups,
      founders,
      [
        sub("s-a", "In progress", "2026-10-13T10:00:00Z", 80),
        sub("s-b", "Blocked", "2026-10-12T10:00:00Z"),
        sub("s-b", "Blocked", "2026-10-10T10:00:00Z"),
        sub("s-b", "In progress", "2026-10-08T10:00:00Z"),
      ],
      now,
    );
    expect(roster.map((r) => [r.id, r.health])).toEqual([
      ["s-b", "blocked"],
      ["s-c", "quiet"],
      ["s-a", "on_track"],
    ]);
    expect(roster[0]?.healthDetail).toBe("Blocked for 3 days");
    expect(roster[2]?.name).toBe("Ann, Bob");
    expect(roster[2]?.founderIds).toEqual(["f1", "f2"]);
    expect(roster[1]?.healthDetail).toBe("No check-ins yet");
  });

  it("marks a startup quiet after 7 days without a check-in", () => {
    const [row] = buildRoster([startups[0]!], founders, [sub("s-a", "In progress", "2026-10-03T10:00:00Z")], now);
    expect(row?.health).toBe("quiet");
    expect(row?.healthDetail).toBe("No check-in for 10 days");
  });

  it("accepts plausible ?as= ids but not junk", () => {
    expect(parsePerspective("startup-auvira")).toBe("startup-auvira");
    expect(parsePerspective("founder-u05abcd")).toBe("founder-u05abcd");
    expect(parsePerspective("<script>")).toBe("coordinator");
    expect(parsePerspective(undefined)).toBe("coordinator");
  });
});
