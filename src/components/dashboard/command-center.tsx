import { useState } from "react";
import {
  Activity,
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  AudioLines,
  Bell,
  CalendarDays,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  Circle,
  CircleAlert,
  CircleHelp,
  Code2,
  Command,
  Flag,
  LayoutGrid,
  ListFilter,
  MessageSquare,
  Radio,
  Search,
  Settings2,
  ShieldCheck,
  Target,
  TrendingUp,
  Users,
  Zap,
  LocateFixed,
  Flame,
  Sparkles,
  UserPlus,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from "@/components/ui/accordion";
import { 
  founders, 
  roadmap, 
  currentSprintPhase, 
  currentDeliverable, 
  currentDeliverableDate, 
  nextOfficeHoursActivity, 
  nextOfficeHoursDate, 
  nextOfficeHoursOwner,
  allSyllabusEvents,
  type Founder, 
  type DemoPerspective 
} from "./data";
import { StudioPerspectives } from "./studio-perspectives";
import { AiChatOverlay } from "./ai-chat-overlay";

function Avatar({ founder, small = false }: { founder: Founder; small?: boolean }) {
  return (
    <div
      aria-label={`${founder.name} · fictional user`}
      className={`founder-avatar flex items-center justify-center text-[10px] font-semibold text-muted-foreground ${small ? "size-7!" : ""}`}
    >
      {founder.id === "demo-founder-01" ? "DA" : "DB"}
    </div>
  );
}
function StreamPill({ founder }: { founder: Founder }) {
  return (
    <span className={`pill max-w-full whitespace-normal! ${founder.stream === "Tech" ? "pill-info" : "pill-warning"}`}>
      <span className="stream-dot shrink-0" />
      <span className="min-w-0 break-words">{founder.stream} · {founder.lead}</span>
    </span>
  );
}
function Status({ founder }: { founder: Founder }) {
  return (
    <span className={`pill ${founder.status === "Blocked" ? "pill-danger" : "pill-info"}`}>
      {founder.status === "Blocked" ? <CircleAlert size={10} /> : <Circle size={9} />}{" "}
      {founder.status}
      {founder.status === "In progress" && " · 80%"}
    </span>
  );
}
const filters = [
  "All startups",
  "Tech",
  "GTM & Strategy",
  "Marketing & Activation",
  "Flagged blockers",
];

export interface Cohort {
  id: string;
  name: string;
  tag: string;
  location: string;
  founders: Founder[];
}

export function CommandCenter() {
  const [perspective, setPerspective] = useState<DemoPerspective>("coordinator");
  const isMember = perspective.startsWith("demo-founder-");
  const [filter, setFilter] = useState("All startups");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Founder | null>(null);
  const [handled, setHandled] = useState<string[]>([]);
  const [detailTab, setDetailTab] = useState("Overview");
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const [notificationOpen, setNotificationOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState("All statuses");
  const [filterOpen, setFilterOpen] = useState(false);
  const [notice, setNotice] = useState("");
  const [section, setSection] = useState("overview");
  const [chatOpen, setChatOpen] = useState(false);
  
  const [cohorts, setCohorts] = useState<Cohort[]>([
    {
      id: "SG#01",
      name: "Mamba MVP Program",
      tag: "SG#01",
      location: "Singapore · Current Cohort",
      founders: founders,
    },
  ]);
  const [activeCohortId, setActiveCohortId] = useState("SG#01");
  const currentCohort = cohorts.find((c) => c.id === activeCohortId) || cohorts[0];
  const cohortFounders = currentCohort.founders;

  const handleAddFounder = (newFounder: Founder) => {
    setCohorts((prev) =>
      prev.map((c) =>
        c.id === activeCohortId ? { ...c, founders: [newFounder, ...c.founders] } : c
      )
    );
  };

  const handleAddCohort = (newCohort: Cohort) => {
    setCohorts((prev) => [...prev, newCohort]);
    setActiveCohortId(newCohort.id);
    setNotice(`Switched to ${newCohort.name} · ${newCohort.tag} (${newCohort.founders.length} founders).`);
  };

  const visible = cohortFounders.filter((f) => {
    const matchesStream =
      filter === "All startups" ||
      (filter === "Tech" && f.stream === "Tech") ||
      (filter === "GTM & Strategy" && f.stream === "GTM") ||
      (filter === "Flagged blockers" && !handled.includes(f.id));
    return (
      matchesStream &&
      (statusFilter === "All statuses" || f.status === statusFilter) &&
      `${f.name} ${f.startup} ${f.lead}`.toLowerCase().includes(search.toLowerCase())
    );
  });
  function openFounder(f: Founder, tab = "Overview") {
    setSelected(f);
    setDetailTab(tab);
  }
  function navigateSection(id: string) {
    setSection(id);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  return (
    <div className="dashboard-shell">
      <aside className="side-rail" aria-label="Main navigation">
        <div className="brand-mark" title="Mamba MVP Program · SG#01">
          <LocateFixed size={20} strokeWidth={2.2} />
        </div>
        <div className="flex flex-col gap-3">
          <Button
            variant="quiet"
            size="icon"
            className={`nav-icon ${section === "overview" ? "selected" : ""}`}
            title="Command center"
            aria-label="Command center"
            onClick={() => navigateSection("overview")}
          >
            <LayoutGrid />
          </Button>
          <Button
            variant="quiet"
            size="icon"
            className={`nav-icon ${section === "cohort" ? "selected" : ""}`}
            title="Cohort roster"
            aria-label="Cohort roster"
            onClick={() => navigateSection("cohort")}
          >
            <Users />
          </Button>
          <Button
            variant="quiet"
            size="icon"
            className={`nav-icon ${section === "program" ? "selected" : ""}`}
            title="Sprint roadmap"
            aria-label="Sprint roadmap"
            onClick={() => navigateSection("program")}
          >
            <Flag />
          </Button>
          <Button
            variant="quiet"
            size="icon"
            className={`nav-icon ${section === "activity" ? "selected" : ""}`}
            title="Activity feed"
            aria-label="Activity feed"
            onClick={() => navigateSection("activity")}
          >
            <Activity />
          </Button>
        </div>
        <div className="mt-auto flex flex-col gap-3">
          <Button
            variant="default"
            size="icon"
            className="rounded-full shadow-lg hover:shadow-primary/25 hover:scale-105 transition-all"
            title="Resident AI Assistant"
            aria-label="Resident AI Assistant"
            onClick={() => setChatOpen(true)}
          >
            <MessageSquare className="size-5" />
          </Button>
          <Button
            variant="quiet"
            size="icon"
            title="Workspace information"
            aria-label="Workspace information"
            onClick={() =>
              setNotice(
                "SG#01 · 2 founders · 12-week venture studio program. This workspace is a preview with sample data.",
              )
            }
          >
            <Settings2 />
          </Button>
          <Button
            variant="quiet"
            size="icon"
            title="Support"
            aria-label="Support"
            onClick={() =>
              setNotice(
                "Demo support roles: Program Coordinator, GTM Venture Advisor, Marketing / Rollout / User Validation and Technical Advisor. No live support connection.",
              )
            }
          >
            <CircleHelp />
          </Button>
          <span
            className="flex size-8 items-center justify-center rounded-full bg-secondary text-xs font-semibold"
            title="Demo Program Coordinator · Studio operations"
          >
            DO
          </span>
        </div>
      </aside>
      <div className="min-w-0">
        <header className="main-header">
          <div className="relative">
            <Button
              variant="ghost"
              className="workspace px-0!"
              onClick={() => setWorkspaceOpen(!workspaceOpen)}
              aria-expanded={workspaceOpen}
            >
              <span className="workspace-name font-semibold">{currentCohort.name}</span>
              <span className="cohort-tag">{currentCohort.tag}</span>
              <ChevronDown className="size-3! text-muted-foreground" />
            </Button>
            {workspaceOpen && (
              <div className="absolute top-11 left-0 z-20 w-72 rounded-md border border-border bg-card p-3 shadow-md">
                <p className="mb-2 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">ACTIVE COHORTS</p>
                <div className="space-y-1">
                  {cohorts.map((c) => (
                    <button
                      key={c.id}
                      onClick={() => {
                        setActiveCohortId(c.id);
                        setWorkspaceOpen(false);
                      }}
                      className={`w-full flex items-center justify-between p-2 rounded text-xs transition-colors cursor-pointer text-left ${
                        c.id === activeCohortId
                          ? "bg-primary/10 text-primary font-semibold border border-primary/20"
                          : "hover:bg-muted text-foreground"
                      }`}
                    >
                      <div>
                        <div>{c.name} · {c.tag}</div>
                        <div className="text-[10px] text-muted-foreground font-normal">{c.location} · {c.founders.length} founders</div>
                      </div>
                      {c.id === activeCohortId && <Check size={14} className="text-primary shrink-0" />}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
          <div className="header-sprint flex items-center gap-2 text-[11px] text-muted-foreground">
            <Flag size={12} />
            <span>Sprint 1: Problem & Founder Thesis</span>
            <span className="mx-2 text-border">/</span>
            <span>
              Week <strong className="font-medium text-foreground">1</strong> of 12
            </span>
          </div>
          <div className="flex items-center gap-3">
            {!isMember && <label className="search-field header-search">
              <Search size={13} className="text-muted-foreground" />
              <input
                aria-label="Search founders"
                placeholder="Search anything…"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  navigateSection("cohort");
                }}
              />
              <span className="rounded border border-border px-1 text-[9px] text-muted-foreground">
                ⌘ K
              </span>
            </label>}
            <div className="relative">
              <Button
                variant="quiet"
                size="icon"
                aria-label="Notifications"
                title="Notifications"
                onClick={() => setNotificationOpen(!notificationOpen)}
              >
                <Bell size={16} />
                <span className="absolute top-2 right-2 size-1.5 rounded-full bg-primary" />
              </Button>
              {notificationOpen && (
                <div className="absolute right-0 top-11 z-20 w-64 rounded-md border border-border bg-card p-4 shadow-sm">
                  <p className="text-xs font-semibold">Notifications</p>
                  <p className="mt-3 text-xs text-muted-foreground">
                    2 blockers awaiting studio review.
                  </p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    Both founders checked in this week.
                  </p>
                </div>
              )}
            </div>
            <span className="h-5 border-l border-border" />
            <span className="flex size-7 items-center justify-center rounded-full bg-accent text-[10px] font-semibold text-primary">
              {isMember ? (perspective === "demo-founder-01" ? "DA" : "DB") : "CT"}
            </span>
          </div>
        </header>
        <main className="content-wrap" id="overview">
          <div className="page-intro flex items-center justify-between gap-4">
            <div>
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <span className="pill pill-neutral">PROTOTYPE · FICTIONAL DATA</span>
                <span className="flex items-center gap-1.5 text-[10px] text-success">
                  <span className="live-dot" />
                  Slack simulation · Not connected
                </span>
              </div>
              <h1 className="page-title text-[30px] font-semibold leading-tight">
                {isMember ? "My venture" : "Cohort pulse"}<span className="text-primary">.</span>
              </h1>
              <p className="mt-2 text-xs text-muted-foreground">
                Demo users, ventures and conversations are entirely fictional.
              </p>
            </div>
            <div className="date-label text-right">
              <div className="mb-1 text-xs font-semibold text-foreground">
                {new Date().toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}
              </div>
              <span className="text-[10px] text-muted-foreground">
                Real-time cohort telemetry
              </span>
            </div>
          </div>

          {/* --- FOUNDER POKEMON CARDS SHOWCASE --- */}
          <div className="mt-6 mb-8">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-bold tracking-tight text-foreground flex items-center gap-2">
                    <Sparkles className="size-4 text-primary" /> Active Founder Roster
                  </h2>
                  <span className="rounded-full bg-primary/10 px-2.5 py-0.5 text-[11px] font-semibold text-primary">
                    {cohortFounders.length} Live Cards
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Real-time telemetry cards showing current abilities, sprint progress, and active blockers.
                </p>
              </div>
              <Button
                size="sm"
                className="gap-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 text-xs shadow-xs cursor-pointer"
                onClick={() => setChatOpen(true)}
              >
                <UserPlus size={14} />
                + Onboard Founder via AI
              </Button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {cohortFounders.map((f) => {
                const isTech = f.stream === "Tech";
                const isBlocked = f.status === "Blocked";
                return (
                  <div
                    key={f.id}
                    className="group relative flex flex-col justify-between rounded-xl border border-border bg-card p-5 shadow-xs transition-all duration-200 hover:-translate-y-1 hover:shadow-md hover:border-primary/40"
                  >
                    {/* Card Top: Stream Type + Velocity Bar */}
                    <div>
                      <div className="flex items-center justify-between border-b border-border/50 pb-3 mb-3">
                        <span
                          className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[10px] font-bold tracking-wide uppercase ${
                            isTech
                              ? "bg-sky-500/10 text-sky-600 border border-sky-500/20"
                              : "bg-amber-500/10 text-amber-700 border border-amber-500/20"
                          }`}
                        >
                          {isTech ? <Zap size={11} className="fill-current" /> : <Flame size={11} className="fill-current" />}
                          {isTech ? "Tech Architect" : "GTM Strategist"}
                        </span>

                        <div className="flex items-center gap-1.5">
                          <span className="text-[10px] font-mono font-semibold text-muted-foreground">
                            VELOCITY {f.progress}%
                          </span>
                          <div className="h-1.5 w-12 rounded-full bg-muted overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all duration-500 ${
                                isBlocked ? "bg-destructive" : "bg-primary"
                              }`}
                              style={{ width: `${f.progress}%` }}
                            />
                          </div>
                        </div>
                      </div>

                      {/* Card Portrait & Identity */}
                      <div className="flex items-start gap-3.5 mb-3.5">
                        <div
                          className={`relative flex size-12 shrink-0 items-center justify-center rounded-2xl font-bold text-sm text-white shadow-sm ${
                            isTech
                              ? "bg-gradient-to-br from-sky-500 to-indigo-600"
                              : "bg-gradient-to-br from-amber-500 to-orange-600"
                          }`}
                        >
                          {f.name.split(" ").map((n) => n[0]).join("")}
                          <span
                            className={`absolute -bottom-1 -right-1 size-3.5 rounded-full border-2 border-card ${
                              isBlocked ? "bg-destructive" : "bg-emerald-500 animate-pulse"
                            }`}
                            title={f.status}
                          />
                        </div>
                        <div className="min-w-0 flex-1">
                          <h3 className="font-bold text-sm text-foreground truncate group-hover:text-primary transition-colors">
                            {f.name}
                          </h3>
                          <p className="text-xs font-medium text-muted-foreground truncate">
                            {f.startup}
                          </p>
                          <p className="text-[10px] text-muted-foreground/80 mt-0.5 flex items-center gap-1">
                            <span className="size-1.5 rounded-full bg-muted-foreground/40" />
                            Lead: {f.lead}
                          </p>
                        </div>
                      </div>

                      {/* Weekly Sprint Progress Bars */}
                      <div className="rounded-lg border border-border/40 bg-muted/20 p-2.5 mb-3">
                        <div className="flex items-center justify-between text-[10px] mb-1.5">
                          <span className="font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                            <CalendarDays size={11} className="text-primary" />
                            Weekly Sprint Track
                          </span>
                          <span className="font-mono font-medium text-foreground">
                            Week 1 of 12 · <span className={isBlocked ? "text-amber-600 font-semibold" : "text-primary font-semibold"}>{f.progress}%</span>
                          </span>
                        </div>
                        {/* 12-Week Segmented Progress Bar */}
                        <div className="grid grid-cols-12 gap-1 mb-1.5">
                          {Array.from({ length: 12 }).map((_, wIdx) => {
                            const weekNum = wIdx + 1;
                            const isCurrent = weekNum === 1;
                            return (
                              <div
                                key={wIdx}
                                className="group/pip relative flex flex-col items-center"
                                title={`Week ${weekNum}: ${isCurrent ? `${f.progress}% complete (Sprint 1: Problem Thesis)` : "Upcoming Sprint Milestone"}`}
                              >
                                <div
                                  className={`h-2 w-full rounded-xs transition-all ${
                                    isCurrent
                                      ? isBlocked
                                        ? "bg-amber-500 animate-pulse"
                                        : "bg-primary"
                                      : "bg-muted/80"
                                  }`}
                                  style={
                                    isCurrent
                                      ? {
                                          opacity: Math.max(0.5, f.progress / 100),
                                        }
                                      : {}
                                  }
                                />
                                <span className="text-[8px] font-mono text-muted-foreground/70 mt-0.5 group-hover/pip:text-foreground">
                                  W{weekNum}
                                </span>
                              </div>
                            );
                          })}
                        </div>
                        <div className="flex items-center justify-between text-[9px] text-muted-foreground pt-1 border-t border-border/30">
                          <span>Current Milestone: Problem & Thesis</span>
                          <span className={isBlocked ? "text-amber-600 font-medium" : "text-emerald-600 font-medium"}>
                            {isBlocked ? "Blocked on OCR" : "Sprint 1 Velocity"}
                          </span>
                        </div>
                      </div>

                      {/* Moves: What they're doing */}
                      <div className="rounded-lg bg-muted/40 p-2.5 mb-3 border border-border/30">
                        <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-1 flex items-center gap-1">
                          <Activity size={10} className="text-primary" /> Active Sprint Move:
                        </p>
                        <p className="text-xs text-foreground/90 line-clamp-2 leading-relaxed">
                          {f.digest}
                        </p>
                      </div>

                      {/* Vulnerability / Blocker */}
                      <div
                        className={`rounded-lg p-2.5 mb-3 border text-xs leading-relaxed ${
                          isBlocked
                            ? "bg-destructive/10 border-destructive/20 text-destructive font-medium"
                            : "bg-emerald-500/10 border-emerald-500/20 text-emerald-700"
                        }`}
                      >
                        <p className="text-[10px] font-bold uppercase tracking-wider mb-0.5 flex items-center gap-1">
                          {isBlocked ? <CircleAlert size={10} /> : <CheckCheck size={10} />}
                          {isBlocked ? "Current Blocker:" : "Sprint Status:"}
                        </p>
                        <p className="line-clamp-2 text-[11px]">
                          {isBlocked ? f.blocker : "Unblocked. Execution on track."}
                        </p>
                      </div>

                      {/* Stack Tags */}
                      <div className="flex flex-wrap gap-1 mb-4">
                        {f.stack.slice(0, 3).map((tool, tIdx) => (
                          <span
                            key={tIdx}
                            className="rounded bg-muted px-2 py-0.5 text-[9px] font-mono text-muted-foreground"
                          >
                            {tool}
                          </span>
                        ))}
                      </div>
                    </div>

                    {/* Card Footer Actions */}
                    <div className="pt-2 border-t border-border/40 flex items-center justify-between gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        className="w-full text-xs h-7 rounded-md cursor-pointer"
                        onClick={() => openFounder(f)}
                      >
                        Inspect Dossier
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-xs h-7 px-2 text-muted-foreground hover:text-foreground cursor-pointer"
                        title="Poke in Slack"
                        onClick={() =>
                          setNotice(`Slack Bot: Poked ${f.name} in their private Slack channel.`)
                        }
                      >
                        <MessageSquare size={13} />
                      </Button>
                    </div>
                  </div>
                );
              })}

              {/* Onboard New Founder Card (Pokemon Mint Card) */}
              <button
                onClick={() => setChatOpen(true)}
                className="group relative flex min-h-[300px] flex-col items-center justify-center rounded-xl border-2 border-dashed border-border bg-muted/20 p-6 text-center transition-all hover:border-primary/60 hover:bg-primary/5 cursor-pointer"
              >
                <div className="flex size-14 items-center justify-center rounded-2xl bg-primary/10 text-primary group-hover:scale-110 transition-transform shadow-xs mb-3">
                  <UserPlus size={26} />
                </div>
                <h3 className="font-bold text-sm text-foreground group-hover:text-primary transition-colors">
                  Onboard New Founder
                </h3>
                <p className="text-xs text-muted-foreground mt-1 max-w-[200px]">
                  Trigger the AI Intake Protocol to request thesis & discovery notes, then mint their card.
                </p>
                <span className="mt-4 inline-flex items-center gap-1.5 rounded-full bg-primary px-3.5 py-1.5 text-xs font-semibold text-primary-foreground shadow-xs">
                  <Sparkles size={12} /> Launch Protocol
                </span>
              </button>
            </div>
          </div>
          <StudioPerspectives perspective={perspective} onChange={(value) => {
            setPerspective(value);
            setSelected(null);
            setNotificationOpen(false);
            setSearch("");
            setFilter("All startups");
            setStatusFilter("All statuses");
          }} openFounder={openFounder} />
          {!isMember && <>
          <div className="kpi-grid">
            <div className="kpi">
              <div className="kpi-label">
                Cohort velocity
                <TrendingUp size={14} />
              </div>
              <div className="mt-4 flex items-center justify-between">
                <div className="flex items-baseline gap-2">
                  <span className="kpi-value">
                    88<span className="text-xl">%</span>
                  </span>
                  <span className="text-[11px] text-muted-foreground">on track</span>
                </div>
                <svg
                  width="78"
                  height="32"
                  viewBox="0 0 78 32"
                  className="text-success"
                  aria-label="Velocity trending upwards"
                >
                  <path
                    d="M1 30 12 25 23 28 34 17 45 20 56 10 67 13 77 2"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinejoin="round"
                  />
                  <path
                    d="M1 30 12 25 23 28 34 17 45 20 56 10 67 13 77 2V32H1Z"
                    fill="currentColor"
                    opacity=".07"
                  />
                </svg>
              </div>
              <div className="kpi-foot">
                <ArrowUpRight size={12} className="text-success" />
                <span className="text-success">12%</span> vs. last check-in
              </div>
            </div>
            <div className="kpi">
              <div className="kpi-label">
                Active blockers
                <CircleAlert size={14} />
              </div>
              <div className="mt-4 flex items-baseline gap-2">
                <span className="kpi-value">{2 - handled.length}</span>
                <span className="text-[11px] text-muted-foreground">open blockers</span>
              </div>
              <div className="kpi-foot">
                <span className="pill pill-info">
                  Tech · {handled.includes("demo-founder-02") ? 0 : 1}
                </span>
                <span className="pill pill-warning">
                  GTM · {handled.includes("demo-founder-01") ? 0 : 1}
                </span>
              </div>
            </div>
            <div className="kpi">
              <div className="kpi-label">
                Check-in response rate
                <AudioLines size={14} />
              </div>
              <div className="mt-4 flex items-baseline gap-2">
                <span className="kpi-value">
                  100<span className="text-xl">%</span>
                </span>
                <span className="text-[11px] text-muted-foreground">active</span>
              </div>
              <div className="kpi-foot">
                <CheckCheck size={13} className="text-success" />2 of 2 founders checked in
              </div>
            </div>
            <div className="kpi">
              <div className="kpi-label">
                Next program gate
                <Flag size={14} />
              </div>
              <div className="mt-4 flex items-baseline gap-2">
                <span className="kpi-value text-[26px]!">Oct 16</span>
                <span className="pill pill-orange">6 days left</span>
              </div>
              <div className="kpi-foot">
                Sprint 1 gate{" "}
                <span className="ml-auto">
                  <ArrowRight size={12} />
                </span>
              </div>
            </div>
          </div>
          <section aria-labelledby="triage-title">
            <div className="section-heading">
              <div className="flex items-center gap-2">
                <CircleAlert size={15} className="text-danger" />
                <h2 id="triage-title">Needs your attention</h2>
                <span className="pill pill-danger">{2 - handled.length}</span>
              </div>
              <span className="text-[10px] text-muted-foreground">
                Prioritized from founder check-ins
              </span>
            </div>
            <div className="blocker-grid">
              {[...founders].reverse().map((f) => (
                <article
                  key={f.id}
                  className={`blocker ${handled.includes(f.id) ? "handled" : ""}`}
                >
                  <div className="mb-3 flex items-center justify-between">
                    <StreamPill founder={f} />
                    <span
                      className={`flex items-center gap-1 text-[10px] ${handled.includes(f.id) ? "text-success" : "text-danger"}`}
                    >
                      <span className="stream-dot" />
                      {handled.includes(f.id) ? "Handled" : "Open blocker"}
                    </span>
                  </div>
                  <div className="flex items-center gap-2.5">
                    <Avatar founder={f} small />
                    <span className="text-xs font-semibold">{f.name}</span>
                    <span className="truncate text-[10px] text-muted-foreground">{f.startup}</span>
                  </div>
                  <p className="mt-3 min-h-10 text-xs leading-relaxed">{f.blocker}</p>
                  <div className="mt-2 flex items-center gap-1.5 text-[10px] text-muted-foreground">
                    <AudioLines size={12} />
                    Simulated voice note<span className="mx-1">·</span>
                    {f.time}
                  </div>
                  <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border pt-3">
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7! text-[10px]!"
                      disabled={handled.includes(f.id)}
                      onClick={() => setHandled([...handled, f.id])}
                    >
                      <Check size={11} />
                      {handled.includes(f.id)
                        ? "Handled in office hours"
                        : "Mark handled in office hours"}
                    </Button>
                    <Button
                      variant="quiet"
                      size="sm"
                      className="ml-auto h-7! px-0! text-[10px]!"
                      onClick={() => openFounder(f, "Check-ins")}
                    >
                      View source
                      <ArrowUpRight size={11} />
                    </Button>
                  </div>
                </article>
              ))}
            </div>
          </section>
          <section
            className="matrix-section scroll-mt-6"
            id="cohort"
            aria-labelledby="cohort-title"
          >
            <div className="section-heading">
              <div>
                <div className="flex items-center gap-2">
                  <h2 id="cohort-title">The cohort</h2>
                  <span className="pill pill-neutral">2 startups</span>
                </div>
                <p className="mt-1.5 text-[11px] text-muted-foreground">
                  Fictional founder momentum, deliverables and simulated check-ins.
                </p>
              </div>
              <Button
                variant="quiet"
                size="sm"
                onClick={() => {
                  setFilter("All startups");
                  setSearch("");
                  setStatusFilter("All statuses");
                }}
              >
                <Radio size={12} />
                <span className="text-[10px]">Demo overview</span>
              </Button>
            </div>
            <div className="matrix-tools">
              <div className="filter-tabs" role="tablist" aria-label="Workstream filters">
                {filters.map((f, i) => (
                  <Button
                    role="tab"
                    aria-selected={filter === f}
                    key={f}
                    size="sm"
                    variant="ghost"
                    className={`filter-tab h-8! px-2.5! text-[10px]! ${filter === f ? "active" : ""}`}
                    onClick={() => setFilter(f)}
                  >
                    {i === 0 && <LayoutGrid className="size-3!" />}
                    {i === 1 && <Code2 className="size-3!" />}
                    {i === 4 && <Flag className="size-3!" />}
                    {f}
                    {i === 0 && <span className="ml-1 text-muted-foreground">2</span>}
                  </Button>
                ))}
              </div>
              <div className="relative">
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8! text-[10px]!"
                  onClick={() => setFilterOpen(!filterOpen)}
                  aria-expanded={filterOpen}
                >
                  <ListFilter className="size-3!" />
                  Filters
                  {statusFilter !== "All statuses" && (
                    <span className="size-1.5 rounded-full bg-primary" />
                  )}
                </Button>
                {filterOpen && (
                  <div className="absolute top-10 right-0 z-10 w-48 rounded-md border border-border bg-card p-3 shadow-sm">
                    <label className="text-[10px] text-muted-foreground" htmlFor="status-filter">
                      Deliverable status
                    </label>
                    <select
                      id="status-filter"
                      className="mt-2 w-full rounded border border-border bg-card p-2 text-xs"
                      value={statusFilter}
                      onChange={(e) => setStatusFilter(e.target.value)}
                    >
                      <option>All statuses</option>
                      <option>Blocked</option>
                      <option>In progress</option>
                    </select>
                  </div>
                )}
              </div>
            </div>
            <div className="table-frame">
              <table className="cohort-table">
                <colgroup>
                  <col className="w-[19%]" />
                  <col className="w-[19%]" />
                  <col className="w-[13%]" />
                  <col className="w-[26%]" />
                  <col className="w-[12%]" />
                  <col className="w-[11%]" />
                </colgroup>
                <thead>
                  <tr>
                    <th>
                      Founder & startup <ArrowDown className="ml-1 inline size-2.5" />
                    </th>
                    <th>Sprint 1 milestone</th>
                    <th>Deliverable status</th>
                    <th className="flex items-center gap-1.5">
                      <Zap size={11} className="text-primary" />
                      Latest AI check-in digest
                    </th>
                    <th>Stream ownership</th>
                    <th>Last check-in</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((f) => (
                    <tr key={f.id} onClick={() => openFounder(f)}>
                      <td>
                        <div className="flex gap-2.5">
                          <Avatar founder={f} />
                          <div>
                            <p className="font-semibold">{f.name}</p>
                            <p className="mt-1 text-[10px] text-muted-foreground">{f.startup}</p>
                          </div>
                        </div>
                      </td>
                      <td>
                        <p className="leading-relaxed">1-page venture thesis</p>
                        <p className="mt-1 text-[10px] leading-relaxed text-muted-foreground">
                          Top 10 assumptions ranked
                        </p>
                        <div className="mt-3 flex items-center gap-2">
                          <progress
                            max={100}
                            value={f.progress}
                            className="h-1 w-20 overflow-hidden rounded-full [&::-webkit-progress-bar]:bg-secondary [&::-webkit-progress-value]:bg-primary"
                          />
                          <span className="text-[9px] text-muted-foreground">{f.progress}%</span>
                        </div>
                      </td>
                      <td>
                        <Status founder={f} />
                      </td>
                      <td>
                        <p className="text-[11px] leading-[1.7]">{f.digest}</p>
                        <Button
                          variant="quiet"
                          className="mt-1 h-auto! p-0! text-[10px]!"
                          onClick={(e) => {
                            e.stopPropagation();
                            openFounder(f, "Check-ins");
                          }}
                        >
                          View timeline & transcript
                          <ArrowUpRight className="size-2.5!" />
                        </Button>
                      </td>
                      <td>
                        <StreamPill founder={f} />
                      </td>
                      <td>
                        <p className="text-[11px]">{f.time}</p>
                        <p className="mt-1.5 flex items-center gap-1 text-[9px] text-muted-foreground">
                          <AudioLines size={10} />
                          Demo audio
                        </p>
                        <Button
                          variant="quiet"
                          size="icon"
                          className="mt-2 h-6! w-6!"
                          aria-label={`View ${f.name} details`}
                        >
                          <ChevronRight className="size-3!" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                  {visible.length === 0 && (
                    <tr>
                      <td colSpan={6}>
                        <div className="py-6 text-center">
                          <Search size={20} className="mx-auto mb-3 text-muted-foreground" />
                          <p className="text-sm font-medium">No startups match these filters</p>
                          <Button
                            variant="link"
                            size="sm"
                            onClick={() => {
                              setFilter("All startups");
                              setSearch("");
                              setStatusFilter("All statuses");
                            }}
                          >
                            Clear filters
                          </Button>
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
              <div className="table-footer">
                <span>Showing {visible.length} of 2 startups</span>
                <span className="flex items-center gap-1.5">
                  <ShieldCheck size={11} />
                  AI summaries · human oversight
                </span>
              </div>
            </div>
          </section>
          </>}
          <div className="bottom-grid">
            {!isMember && <section id="activity" className="scroll-mt-6">
              <div className="section-heading">
                <div className="flex items-center gap-2">
                  <Activity size={14} />
                  <h2>Latest signals</h2>
                </div>
                <span className="text-[10px] text-muted-foreground">Today</span>
              </div>
              <div className="activity-item">
                <span className="activity-symbol text-danger">
                  <Flag size={12} />
                </span>
                <div className="flex-1">
                  <p className="text-[11px]">
                    <strong className="font-medium">Demo Founder B</strong> flagged a technical
                    blocker
                    <span className="ml-2 pill pill-info">Tech</span>
                  </p>
                  <p className="mt-1 text-[10px] text-muted-foreground">
                    Mock calendar issue · Routed to Demo Technical Advisor
                  </p>
                </div>
                <span className="text-[10px] text-muted-foreground">2h ago</span>
              </div>
              <div className="activity-item">
                <span className="activity-symbol text-success">
                  <AudioLines size={12} />
                </span>
                <div className="flex-1">
                  <p className="text-[11px]">
                    <strong className="font-medium">Demo Founder A</strong> completed her weekly
                    check-in
                  </p>
                  <p className="mt-1 text-[10px] text-muted-foreground">
                    Sample persona exercise completed · Simulated voice note
                  </p>
                </div>
                <span className="text-[10px] text-muted-foreground">3h ago</span>
              </div>
              <div className="activity-item">
                <span className="activity-symbol text-primary">
                  <Zap size={12} />
                </span>
                <div className="flex-1">
                  <p className="text-[11px]">
                    Cohort pulse updated by <strong className="font-medium">Studio AI</strong>
                  </p>
                  <p className="mt-1 text-[10px] text-muted-foreground">
                    2 check-ins processed · 2 signals flagged for review
                  </p>
                </div>
                <span className="text-[10px] text-muted-foreground">3h ago</span>
              </div>
            </section>
            }
            <section id="program" className="scroll-mt-6">
              <div className="section-heading">
                <div className="flex items-center gap-2">
                  <Flag size={14} />
                  <h2>On the horizon</h2>
                </div>
                <span className="pill pill-neutral">Week 1 / 12</span>
              </div>
              <div className="border-b border-border pb-5">
                <div className="flex items-start gap-3">
                  <div className="rounded-md bg-accent p-2 text-primary">
                    <Target size={18} />
                  </div>
                  <div>
                    <span className="text-[9px] font-medium uppercase text-primary">
                      Next program gate
                    </span>
                    <h3 className="mt-1 text-[13px] font-semibold">{currentSprintPhase}</h3>
                    <p className="mt-1.5 text-[10px] text-muted-foreground">
                      {currentDeliverableDate}<span className="mx-2">·</span>{currentDeliverable}
                    </p>
                  </div>
                </div>
                <div className="program-band" aria-label="Week 1 of 12">
                  {roadmap.map((r, i) => (
                    <div
                      key={r}
                      className={`program-step ${i === 0 ? "current" : ""}`}
                      title={`Week ${i + 1}: ${r}`}
                    />
                  ))}
                </div>
                <div className="mt-2 flex justify-between text-[9px] text-muted-foreground">
                  <span>Kickoff</span>
                  <span>Demo day</span>
                </div>
              </div>
              <div className="flex items-center gap-3 pt-4">
                <CalendarDays size={16} className="text-muted-foreground" />
                <div>
                  <p className="text-[11px] font-medium">{nextOfficeHoursActivity}</p>
                  <p className="mt-1 text-[10px] text-muted-foreground">
                    {nextOfficeHoursDate} · {nextOfficeHoursOwner}
                  </p>
                </div>
                <Button
                  variant="quiet"
                  size="icon"
                  className="ml-auto"
                  aria-label="View office hours preparation"
                  title="Office hours preparation"
                  onClick={() => {
                    const founder = founders.find((f) => f.id === (isMember ? perspective : "demo-founder-02"));
                    if (founder) openFounder(founder, "Office hours");
                  }}
                >
                  <ArrowUpRight size={13} />
                </Button>
              </div>
            </section>
            
            <section id="full-syllabus" className="mt-8 scroll-mt-6">
              <div className="section-heading mb-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <CalendarDays size={16} className="text-primary" />
                    <h2 className="text-base font-bold text-foreground">Full Syllabus Timeline & Founder Completion</h2>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1 font-medium"><Check size={12} className="text-emerald-600" /> Done</span>
                    <span className="flex items-center gap-1 font-medium"><Zap size={12} className="text-sky-600" /> In Progress</span>
                    <span className="flex items-center gap-1 font-medium"><CircleAlert size={12} className="text-destructive" /> Blocked</span>
                    <span className="flex items-center gap-1 font-medium"><Circle size={10} className="text-muted-foreground" /> Pending</span>
                  </div>
                </div>
              </div>
              <div className="flex flex-col gap-3 pt-2">
                {allSyllabusEvents.map((event: any, idx: number) => {
                  const isWeek1 = event["Week"] === "WK 01";
                  const hasDeliverable = !!event["Weekly Deliverable / Milestone"];

                  return (
                    <div 
                      key={idx} 
                      className={`grid grid-cols-1 lg:grid-cols-12 gap-4 rounded-xl border p-4 shadow-xs bg-card transition-all hover:border-primary/40 ${
                        hasDeliverable ? "border-primary/30 bg-primary/2" : "border-border"
                      }`}
                    >
                      {/* Left: Syllabus Event Details (8 cols) */}
                      <div className="lg:col-span-7 flex flex-col justify-between">
                        <div>
                          <div className="flex items-center justify-between mb-1.5">
                            <span className="inline-flex items-center gap-1.5 font-mono text-[10px] font-bold text-primary uppercase">
                              <span className="size-1.5 rounded-full bg-primary" />
                              {event["Week"]} · {event["Day"]}
                            </span>
                            <span className="text-[10px] font-medium text-muted-foreground">
                              {event["Date"] ? new Date(event["Date"]).toLocaleDateString("en-US", { month: 'short', day: 'numeric', year: 'numeric' }) : "TBD"}
                            </span>
                          </div>

                          {event["Sprint Phase"] && (
                            <h3 className="text-xs font-bold text-foreground leading-snug">{event["Sprint Phase"]}</h3>
                          )}

                          {event["Exercise / Activity"] && (
                            <p className="text-[11px] text-muted-foreground mt-1.5 leading-relaxed">
                              <strong className="text-foreground font-semibold">Activity:</strong> {event["Exercise / Activity"]}
                            </p>
                          )}

                          {event["Weekly Deliverable / Milestone"] && (
                            <div className="mt-2.5 rounded-md border border-primary/20 bg-primary/5 p-2 text-xs">
                              <span className="font-bold text-primary flex items-center gap-1">
                                <Flag size={12} /> Milestone Deliverable:
                              </span>
                              <p className="font-medium text-foreground mt-0.5">{event["Weekly Deliverable / Milestone"]}</p>
                            </div>
                          )}
                        </div>

                        {event["Owner / Lead"] && (
                          <p className="text-[10px] text-muted-foreground mt-2 pt-2 border-t border-border/40">
                            <strong>Session Lead:</strong> {event["Owner / Lead"]}
                          </p>
                        )}
                      </div>

                      {/* Right Column: Founder Completion Tracker (5 cols) */}
                      <div className="lg:col-span-5 lg:border-l lg:border-border/60 lg:pl-4 flex flex-col justify-between bg-muted/20 -m-4 p-4 lg:m-0 rounded-b-xl lg:rounded-none">
                        <div>
                          <div className="flex items-center justify-between mb-2">
                            <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                              Founder Completion
                            </span>
                            <span className="text-[9px] font-mono text-muted-foreground">
                              {isWeek1 ? "Active Sprint" : "Upcoming"}
                            </span>
                          </div>

                          {/* Founder checklist */}
                          <div className="space-y-1.5">
                            {cohortFounders.map((f, fIdx) => {
                              // Dynamic completion state simulation
                              let status: "done" | "in-progress" | "blocked" | "pending" = "pending";
                              if (isWeek1) {
                                if (f.id.includes("alex")) status = "done";
                                else if (f.id.includes("jordan")) status = f.status === "Blocked" ? "blocked" : "in-progress";
                                else status = "done";
                              } else {
                                status = "pending";
                              }

                              return (
                                <button
                                  key={f.id}
                                  onClick={() => {
                                    setNotice(`Updated ${f.name} on ${event["Week"]} milestone: Status verified.`);
                                  }}
                                  className="w-full flex items-center justify-between rounded-lg border border-border/50 bg-card px-2.5 py-1.5 text-xs text-left transition-colors hover:bg-muted/60 cursor-pointer"
                                  title={`Click to update ${f.name}'s milestone progress`}
                                >
                                  <div className="flex items-center gap-2 min-w-0">
                                    <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-muted text-[9px] font-bold text-foreground">
                                      {f.name.split(" ").map(n => n[0]).join("")}
                                    </span>
                                    <span className="truncate text-[11px] font-medium text-foreground">{f.name}</span>
                                  </div>

                                  <span className="shrink-0 text-[10px]">
                                    {status === "done" && (
                                      <span className="inline-flex items-center gap-1 font-bold text-emerald-600 bg-emerald-500/10 px-1.5 py-0.5 rounded">
                                        <Check size={10} /> Done
                                      </span>
                                    )}
                                    {status === "in-progress" && (
                                      <span className="inline-flex items-center gap-1 font-bold text-sky-600 bg-sky-500/10 px-1.5 py-0.5 rounded">
                                        <Zap size={10} /> In Progress
                                      </span>
                                    )}
                                    {status === "blocked" && (
                                      <span className="inline-flex items-center gap-1 font-bold text-destructive bg-destructive/10 px-1.5 py-0.5 rounded">
                                        <CircleAlert size={10} /> Blocked
                                      </span>
                                    )}
                                    {status === "pending" && (
                                      <span className="inline-flex items-center gap-1 font-medium text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                                        Pending
                                      </span>
                                    )}
                                  </span>
                                </button>
                              );
                            })}
                          </div>
                        </div>

                        <p className="mt-2 text-[9px] text-muted-foreground/80 italic text-right">
                          Tap any founder to review or toggle check-in record.
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          </div>
          <footer className="page-footer">
            <span className="flex items-center gap-1.5">
              <Command size={11} />
              Mamba MVP Program<span className="mx-2">/</span>Built for founder momentum.
            </span>
            <span className="flex items-center gap-1.5">
              <span className="live-dot" />
              Fictional demo data<span className="mx-2">·</span>All times SGT
            </span>
          </footer>
        </main>
      </div>
      <Sheet
        open={selected !== null}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
      >
        <SheetContent className="detail-sheet sm:max-w-[560px]">
          {selected && (
            <>
              <SheetHeader>
                <span className="mb-4 text-[10px] font-medium uppercase text-muted-foreground">
                  Fictional founder · Demo workspace
                </span>
                <div className="flex items-center gap-3">
                  <Avatar founder={selected} />
                  <div>
                    <SheetTitle>{selected.name}</SheetTitle>
                    <SheetDescription className="mt-1 text-xs">{selected.startup}</SheetDescription>
                  </div>
                </div>
              </SheetHeader>
              <div className="mt-5 flex gap-2">
                <Status founder={selected} />
                <StreamPill founder={selected} />
              </div>
              <div className="mt-6 flex gap-1 border-b border-border pb-2">
                {["Overview", "Check-ins", "Office hours"].map((t) => (
                  <Button
                    key={t}
                    variant={detailTab === t ? "secondary" : "ghost"}
                    size="sm"
                    onClick={() => setDetailTab(t)}
                  >
                    {t}
                  </Button>
                ))}
              </div>
              {detailTab === "Overview" && (
                <>
                  <h3 className="detail-heading">Founder profile</h3>
                  <p className="text-xs leading-relaxed text-muted-foreground">
                    {selected.profile}
                  </p>
                  <div className="mt-4 grid grid-cols-2 gap-4 text-xs">
                    <div>
                      <p className="text-[10px] text-muted-foreground">Stage</p>
                      <p className="mt-1">Discovery & validation</p>
                    </div>
                    <div>
                      <p className="text-[10px] text-muted-foreground">Target audience</p>
                      <p className="mt-1">{selected.audience}</p>
                    </div>
                  </div>
                  <p className="mt-4 text-[10px] text-muted-foreground">Tech stack</p>
                  <div className="mt-2 flex gap-2">
                    {selected.stack.map((s) => (
                      <span key={s} className="pill pill-neutral">
                        {s}
                      </span>
                    ))}
                  </div>
                  <h3 className="detail-heading">12-week sprint roadmap</h3>
                  <Accordion type="single" collapsible defaultValue="sprint-0">
                    {roadmap.map((r, i) => (
                      <AccordionItem key={r} value={`sprint-${i}`}>
                        <AccordionTrigger className="py-3 text-xs">
                          <span className="flex items-center gap-3">
                            <span
                              className={`text-[10px] ${i === 0 ? "text-primary" : "text-muted-foreground"}`}
                            >
                              {String(i + 1).padStart(2, "0")}
                            </span>
                            {r}
                            {i === 0 && <span className="pill pill-orange">Current</span>}
                          </span>
                        </AccordionTrigger>
                        <AccordionContent className="text-[11px] leading-relaxed text-muted-foreground">
                          {i === 0
                            ? "Deliver a 1-page venture thesis and rank your top 10 assumptions. Gate: October 16."
                            : `Upcoming sprint: ${r}. Deliverables will be reviewed with your stream lead.`}
                        </AccordionContent>
                      </AccordionItem>
                    ))}
                  </Accordion>
                </>
              )}
              {detailTab === "Check-ins" && (
                <>
                  <h3 className="detail-heading">Simulated check-in history</h3>
                  <div className="drawer-history">
                    <article>
                      <p className="text-[10px] text-muted-foreground">
                        Today · {selected.time} · Simulated voice note
                      </p>
                      <p className="mt-2 text-xs font-medium">{selected.name}</p>
                      <p className="mt-2 text-xs leading-relaxed">“{selected.transcript}”</p>
                      <div className="mt-3 flex items-center gap-2 text-[10px] text-muted-foreground">
                        <AudioLines size={12} />
                        <span>Simulated voice note · No recording</span>
                      </div>
                    </article>
                    <article>
                      <p className="text-[10px] text-muted-foreground">
                        Today · AI confirmation receipt
                      </p>
                      <p className="mt-2 text-xs font-medium">Studio AI</p>
                      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                        Check-in received. Your progress has been captured for Sprint 1. The
                        fictional review request has been assigned to {selected.lead}.
                      </p>
                      <span className="pill pill-success mt-3">
                        <CheckCheck size={10} />
                        Processed
                      </span>
                    </article>
                    <article>
                      <p className="text-[10px] text-muted-foreground">
                        Oct 7 · Simulated direct message
                      </p>
                      <p className="mt-2 text-xs font-medium">{selected.name}</p>
                      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                        “Started drafting a sample venture thesis and mapping assumptions for this
                        fictional concept.”
                      </p>
                    </article>
                  </div>
                  <div className="mt-6 rounded-md border border-border p-3 text-[11px] text-muted-foreground">
                    <MessageSquare className="mr-2 inline size-3" />
                    Invented transcripts · No real messages or recordings
                  </div>
                </>
              )}
              {detailTab === "Office hours" && (
                <>
                  <h3 className="detail-heading">Wednesday, October 14</h3>
                  <p className="text-xs text-muted-foreground">
                    {isMember ? "My session" : "Internal preparation"} · {selected.lead} & Demo Program Coordinator
                  </p>
                  <div className="mt-5 border-l-2 border-primary pl-4">
                    <p className="text-xs font-medium">Discussion priorities</p>
                    <ul className="mt-3 list-disc space-y-3 pl-4 text-xs leading-relaxed text-muted-foreground">
                      <li>Review the venture thesis and ranked assumptions.</li>
                      <li>{selected.blocker}</li>
                      <li>Agree on the next concrete step before the October 16 gate.</li>
                    </ul>
                  </div>
                  {!isMember && <>
                  <h3 className="detail-heading">Studio notes</h3>
                  <div className="rounded-md border border-border bg-background p-4">
                    <p className="text-xs leading-relaxed">{selected.note}</p>
                    <p className="mt-3 text-[10px] text-muted-foreground">
                      Invented demo note · Oct 10
                    </p>
                  </div>
                  <div className="mt-5 flex items-center gap-2 text-[11px] text-muted-foreground">
                    <ShieldCheck size={13} />
                    Read-only office hours log
                  </div>
                  </>}
                </>
              )}
            </>
          )}
        </SheetContent>
      </Sheet>
      <Sheet
        open={!!notice}
        onOpenChange={(open) => {
          if (!open) setNotice("");
        }}
      >
        <SheetContent className="detail-sheet">
          <SheetHeader>
            <SheetTitle>Mamba MVP Program</SheetTitle>
            <SheetDescription>{notice}</SheetDescription>
          </SheetHeader>
        </SheetContent>
      </Sheet>
      
      <AiChatOverlay 
        isOpen={chatOpen} 
        onClose={() => setChatOpen(false)} 
        role={isMember ? (perspective === "demo-founder-01" ? "Demo Founder A" : "Demo Founder B") : "Program Coordinator"}
        activeCohortTag={currentCohort.tag}
        onAddFounder={handleAddFounder}
        onAddCohort={handleAddCohort}
      />
    </div>
  );
}
