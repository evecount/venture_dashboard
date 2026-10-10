export type Founder = {
  id: string;
  name: string;
  startup: string;
  stream: "Tech" | "GTM";
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
};
// Fully fictional fixtures; never use real founder content in this prototype.
export const founders: Founder[] = [
  {
    id: "demo-founder-01",
    name: "Demo Founder A",
    startup: "Demo Venture A · Creative workspace",
    stream: "GTM",
    lead: "Demo GTM Venture Advisor",
    status: "In progress",
    digest:
      "Tested a fictional creative-workspace concept with sample personas. Revising the demo positioning statement.",
    time: "3h ago",
    progress: 80,
    audience: "Fictional independent creative teams",
    stack: ["Design mockups", "Prototype website"],
    blocker: "Needs feedback on two sample positioning options before the next demo review.",
    profile:
      "Fictional venture exploring a shared planning workspace for creative teams. This is not based on a real founder’s business.",
    transcript:
      "I tested the workspace mockup with sample personas. I’d like feedback on the two positioning options before the next review.",
    note: "Demo GTM Venture Advisor: Compare the sample positioning options and agree on one fictional validation experiment.",
  },
  {
    id: "demo-founder-02",
    name: "Demo Founder B",
    startup: "Demo Venture B · Learning planner",
    stream: "Tech",
    lead: "Demo Technical Advisor",
    status: "Blocked",
    digest:
      "The sample learning-planner flow is drafted. A placeholder calendar interaction needs a technical review.",
    time: "2h ago",
    progress: 65,
    audience: "Fictional adult learners",
    stack: ["UI prototype", "Mock calendar data"],
    blocker:
      "The demo calendar does not retain a selected time slot. Needs a prototype interaction review.",
    profile:
      "Fictional venture exploring a lightweight learning planner for adult learners. All product details are invented for this demo.",
    transcript:
      "The sample planner flow is ready, but the demo calendar loses the selected time slot. Could the demo technical lead review the interaction?",
    note: "Demo Technical Advisor: Review the mock calendar interaction and confirm that the selected time slot remains visible.",
  },
];
export const studioRoles = [
  { id: "coordinator", title: "Program Coordinator", focus: "Program delivery", responsibility: "Coordinate the cohort calendar, office hours, deliverables and gate readiness.", task: "Prepare the demo office-hours agenda and follow up on two review requests." },
  { id: "gtm", title: "GTM Venture Advisor", focus: "Venture strategy", responsibility: "Guide positioning, customer discovery, business models and go-to-market experiments.", task: "Review Demo Venture A’s two sample positioning options." },
  { id: "marketing", title: "Marketing / Rollout / User Validation", focus: "Market validation", responsibility: "Support launch planning, user recruitment, validation experiments and activation feedback.", task: "Draft a fictional user-validation experiment for the creative-workspace concept." },
  { id: "technical", title: "Technical Advisor", focus: "MVP development", responsibility: "Advise on MVP scope, architecture, technical feasibility and build blockers.", task: "Review Demo Venture B’s mock calendar interaction." },
] as const;
export type DemoPerspective = typeof studioRoles[number]["id"] | "demo-founder-01" | "demo-founder-02";
import syllabusData from "../../data/syllabus.json";

const rawData = (syllabusData as any).Mamba_MVP_Official_Syllabus_Sch;

const rawSprints = rawData
  .map((row: any) => row["Sprint Phase"])
  .filter((phase: any) => typeof phase === "string" && phase.trim() !== "");

export const roadmap = Array.from(new Set(rawSprints)) as string[];

// Dynamic extraction for "On the horizon" section (Defaulting to WK 01)
const wk01Data = rawData.filter((row: any) => row["Week"] === "WK 01");

export const currentSprintPhase = wk01Data[0]?.["Sprint Phase"] || "Unknown Phase";

const fridayRow = wk01Data.find((row: any) => row["Day"] === "Fri");
export const currentDeliverable = fridayRow?.["Weekly Deliverable / Milestone"] || "No deliverable set";
export const currentDeliverableDate = fridayRow?.["Date"] ? new Date(fridayRow["Date"]).toLocaleDateString("en-US", { weekday: 'long', month: 'short', day: 'numeric' }) : "TBD";

const wednesdayRow = wk01Data.find((row: any) => row["Day"] === "Wed");
export const nextOfficeHoursActivity = wednesdayRow?.["Exercise / Activity"] || "Office Hours";
export const nextOfficeHoursDate = wednesdayRow?.["Date"] ? new Date(wednesdayRow["Date"]).toLocaleDateString("en-US", { month: 'short', day: 'numeric' }) : "TBD";
export const nextOfficeHoursOwner = wednesdayRow?.["Owner / Lead"] || "Studio Lead";
