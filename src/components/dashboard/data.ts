export type Founder = {
  id: string;
  startupId?: string;
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
    responsibility: "Coordinate the cohort calendar, office hours, deliverables and gate readiness.",
  },
  {
    id: "gtm",
    title: "GTM Venture Advisor",
    focus: "Venture strategy",
    responsibility: "Guide positioning, customer discovery, business models and go-to-market experiments.",
  },
  {
    id: "marketing",
    title: "Marketing / Rollout / User Validation",
    focus: "Market validation",
    responsibility: "Support launch planning, user recruitment, validation experiments and activation feedback.",
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

import syllabusData from "../../data/syllabus.json";

const rawData = (syllabusData as any).Mamba_MVP_Official_Syllabus_Sch || [];
export const allSyllabusEvents = rawData;

const rawSprints = rawData
  .map((row: any) => row["Sprint Phase"])
  .filter((phase: any) => typeof phase === "string" && phase.trim() !== "");

export const roadmap = Array.from(new Set(rawSprints)) as string[];

// Dynamic extraction for "On the horizon" section (Defaulting to WK 01)
const wk01Data = rawData.filter((row: any) => row["Week"] === "WK 01");

export const currentSprintPhase = wk01Data[0]?.["Sprint Phase"] || "Sprint 1: Problem, Founder Thesis & Opportunity";

const fridayRow = wk01Data.find((row: any) => row["Day"] === "Fri");
export const currentDeliverable = fridayRow?.["Weekly Deliverable / Milestone"] || "1-page venture thesis & Top 10 assumptions ranked";
export const currentDeliverableDate = fridayRow?.["Date"]
  ? new Date(fridayRow["Date"]).toLocaleDateString("en-US", {
      weekday: "long",
      month: "short",
      day: "numeric",
    })
  : "Friday, Oct 16";

const wednesdayRow = wk01Data.find((row: any) => row["Day"] === "Wed");
export const nextOfficeHoursActivity = wednesdayRow?.["Exercise / Activity"] || "Dashboard review, block removal & decision locking";
export const nextOfficeHoursDate = wednesdayRow?.["Date"]
  ? new Date(wednesdayRow["Date"]).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    })
  : "Oct 14";
export const nextOfficeHoursOwner = wednesdayRow?.["Owner / Lead"] || "Studio Lead";
