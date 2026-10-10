import { describe, expect, it } from "vitest";
import { founders, studioRoles } from "@/components/dashboard/data";
import dashboardSource from "@/components/dashboard/command-center.tsx?raw";
import perspectivesSource from "@/components/dashboard/studio-perspectives.tsx?raw";

describe("Prototype privacy", () => {
  it("ships fictional fixtures without original identities or venture details", () => {
    const content = `${JSON.stringify({ founders, studioRoles })} ${dashboardSource} ${perspectivesSource}`;
    expect(content).not.toMatch(/benjamin|\bben\b|arthur|james|gwen|logistics|enterprise studio|supabase auth|auth loop/i);
    for (const founder of founders) {
      expect(founder.id).toMatch(/^demo-founder-/);
      expect(founder.name).toMatch(/^Demo Founder /);
      expect(founder.profile).toMatch(/fictional/i);
      expect(founder.transcript).toBeTruthy();
      expect(founder.note).toMatch(/^Demo /);
    }
  });
  it("models anonymous core-team roles separately from cohort members", () => {
    expect(studioRoles.map((role) => role.title)).toEqual([
      "Program Coordinator", "GTM Venture Advisor", "Marketing / Rollout / User Validation", "Technical Advisor",
    ]);
    expect(perspectivesSource).toContain("No sign-in or access control");
    expect(perspectivesSource).toContain("Cohort members");
  });
  it("clearly labels simulation and does not load founder portraits", () => {
    expect(dashboardSource).toContain("Slack simulation · Not connected");
    expect(dashboardSource).toContain("entirely fictional");
    expect(dashboardSource).not.toContain("founders.jpg");
  });
});