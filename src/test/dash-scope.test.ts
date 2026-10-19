import { describe, expect, it } from "vitest";
import { canLinkInstallation, visibleTasks } from "@/lib/dash-scope";

const tasks = [
  { id: "1", owner_slack_id: null },
  { id: "2", owner_slack_id: "UMENTOR" },
  { id: "3", owner_slack_id: "UFOUNDER" },
];

describe("visibleTasks", () => {
  it("hides mentor-owned tasks from founders but keeps unowned and team tasks", () => {
    expect(visibleTasks(tasks, "founder", ["UFOUNDER"]).map((t) => t.id)).toEqual(["1", "3"]);
  });
  it("shows mentors everything", () => {
    expect(visibleTasks(tasks, "mentor", []).map((t) => t.id)).toEqual(["1", "2", "3"]);
  });
  it("never returns the owner's Slack id", () => {
    for (const role of ["mentor", "founder"] as const)
      for (const t of visibleTasks(tasks, role, ["UFOUNDER"]))
        expect(t).not.toHaveProperty("owner_slack_id");
  });
});

describe("canLinkInstallation", () => {
  it("allows new installations and reconnects by the same startup", () => {
    expect(canLinkInstallation(null, "s1")).toBe(true);
    expect(canLinkInstallation({ startup_id: "s1" }, "s1")).toBe(true);
  });
  it("refuses an installation that belongs to another startup", () => {
    expect(canLinkInstallation({ startup_id: "s2" }, "s1")).toBe(false);
  });
});
