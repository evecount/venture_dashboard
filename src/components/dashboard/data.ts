export type Founder = {
  id: string;
  startupId?: string;
  cohortId?: string | null;
  founderIds?: string[];
  health?: "blocked" | "quiet" | "on_track";
  healthDetail?: string;
  name: string;
  startup: string;
  stream: string;
  lead: string;
  status: "Blocked" | "In progress";
  digest: string;
  time: string;
  lastCheckInAt?: string;
  progress: number;
  audience: string;
  stack: string[];
  blocker: string;
  profile: string;
  transcript: string;
  note: string;
  isPulsing?: boolean;
};

export const studioRoles = [
  {
    id: "coordinator",
    title: "Program Coordinator",
    focus: "Program delivery",
    responsibility:
      "Coordinate the cohort calendar, office hours, deliverables and gate readiness.",
  },
  {
    id: "gtm",
    title: "GTM Venture Advisor",
    focus: "Venture strategy",
    responsibility:
      "Guide positioning, customer discovery, business models and go-to-market experiments.",
  },
  {
    id: "marketing",
    title: "Marketing / Rollout / User Validation",
    focus: "Market validation",
    responsibility:
      "Support launch planning, user recruitment, validation experiments and activation feedback.",
  },
  {
    id: "technical",
    title: "Technical Advisor",
    focus: "MVP development",
    responsibility: "Advise on MVP scope, architecture, technical feasibility and build blockers.",
  },
] as const;

// A studio role id, or any founder/startup id (resolved against the roster; unknown ids fall back to the coordinator view).
export type DemoPerspective = (typeof studioRoles)[number]["id"] | (string & {});

const roleIds: readonly string[] = studioRoles.map((role) => role.id);

/** Validates a ?as= value: a studio role, or a plausible founder/startup id. Anything else gets the coordinator view. */
export function parsePerspective(value: string | undefined): DemoPerspective {
  if (value && (roleIds.includes(value) || /^[A-Za-z0-9_-]{1,64}$/.test(value))) return value;
  return "coordinator";
}

export function isStudioRole(value: string): boolean {
  return roleIds.includes(value);
}
