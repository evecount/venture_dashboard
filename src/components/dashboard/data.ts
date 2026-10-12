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
// Synthetic fixtures providing context for the MVP_buddy AI agent and the UI.
export const founders: Founder[] = [
  {
    id: "founder-alex-01",
    name: "Alex Vance",
    startup: "Nexus Logistics · Autonomous Supply Chain",
    stream: "GTM",
    lead: "James Sun (Mamba)",
    status: "In progress",
    digest:
      "Interviewed 4 warehouse managers. Discovered they don't care about AI, they just want fewer delayed trucks. Refining the landing page copy to drop the 'AI' buzzwords.",
    time: "3h ago",
    progress: 80,
    audience: "Mid-market warehouse logistics operators",
    stack: ["Landing Page", "Waitlist Form"],
    blocker: "Needs feedback on the new value proposition copy before launching the LinkedIn ads.",
    profile:
      "Alex is validating a supply chain optimization tool. The goal is to manual-test the matching algorithm using spreadsheets before Cybrdeck builds the automated backend.",
    transcript:
      "I just talked to the warehouse guys. They hated the AI pitch. I am rewriting the site to focus entirely on route speed. Need someone to check my new headline.",
    note: "Mamba GTM Strategy: Review Alex's new headline and ensure it focuses on tangible ROI rather than technology.",
  },
  {
    id: "founder-jordan-02",
    name: "Jordan Lee",
    startup: "Vitals.co · Clinical Data Parsing",
    stream: "Tech",
    lead: "Gwen & Ben (Cybrdeck)",
    status: "Blocked",
    digest:
      "Built the initial frontend upload portal, but struggling to map the PDF OCR outputs into the standardized JSON schema required for the Cybrdeck backend handoff.",
    time: "2h ago",
    progress: 65,
    audience: "B2B telehealth clinics",
    stack: ["React Frontend", "PDF.js", "Supabase"],
    blocker:
      "The OCR script drops critical hormone biomarker fields randomly. Need a technical review on the parsing logic.",
    profile:
      "Jordan is building a tool that extracts blood panel data into doctor-ready dossiers. Currently manually running the OCR script to test willingness-to-pay (Wizard of Oz).",
    transcript:
      "The frontend looks great, but my OCR script is randomly dropping the biomarker fields when the PDF formatting changes. Can Gwen or Ben look at my parsing logic?",
    note: "Cybrdeck Engineering: Review Jordan's parsing script and suggest a more robust regex or mapping library before we scale the backend.",
  },
];
export const studioRoles = [
  { id: "coordinator", title: "Program Coordinator", focus: "Program delivery", responsibility: "Coordinate the cohort calendar, office hours, deliverables and gate readiness.", task: "Prepare the demo office-hours agenda and follow up on two review requests." },
  { id: "gtm", title: "GTM Venture Advisor (Mamba)", focus: "Venture strategy", responsibility: "Guide positioning, customer discovery, business models and go-to-market experiments.", task: "Review Alex's new headline and ensure it focuses on tangible ROI rather than technology." },
  { id: "marketing", title: "Marketing / Rollout / User Validation", focus: "Market validation", responsibility: "Support launch planning, user recruitment, validation experiments and activation feedback.", task: "Draft a fictional user-validation experiment for the supply chain concept." },
  { id: "technical", title: "Technical Advisor (Cybrdeck)", focus: "MVP development", responsibility: "Advise on MVP scope, architecture, technical feasibility and build blockers.", task: "Review Jordan's parsing script and suggest a more robust regex or mapping library before scaling the backend." },
] as const;
export type DemoPerspective = typeof studioRoles[number]["id"] | "founder-alex-01" | "founder-jordan-02";
import syllabusData from "../../data/syllabus.json";

const rawData = (syllabusData as any).Mamba_MVP_Official_Syllabus_Sch;
export const allSyllabusEvents = rawData;

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
