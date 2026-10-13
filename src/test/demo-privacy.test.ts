import { describe, expect, it } from "vitest";
import { studioRoles } from "@/components/dashboard/data";
import dashboardSource from "@/components/dashboard/command-center.tsx?raw";
import perspectivesSource from "@/components/dashboard/studio-perspectives.tsx?raw";

describe("Dashboard shows live data only", () => {
  it("ships no simulation or fictional placeholder content", () => {
    const content = `${dashboardSource} ${perspectivesSource}`;
    expect(content).not.toMatch(/simulat|fictional|invented|PROTOTYPE|Demo Founder|demo-founder|AiChatOverlay/i);
  });

  it("hard-codes no real people or ventures in the UI source", () => {
    const content = `${JSON.stringify(studioRoles)} ${dashboardSource} ${perspectivesSource}`;
    expect(content).not.toMatch(/benjamin|\bben\b|arthur|james|gwen|logistics|enterprise studio|supabase auth|auth loop/i);
  });

  it("models the studio team roles separately from cohort members", () => {
    expect(studioRoles.map((role) => role.title)).toEqual([
      "Program Coordinator", "GTM Venture Advisor", "Marketing / Rollout / User Validation", "Technical Advisor",
    ]);
    expect(perspectivesSource).toContain("No sign-in or access control");
    expect(perspectivesSource).toContain("Cohort members");
  });
});
