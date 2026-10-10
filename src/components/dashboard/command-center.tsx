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
  const visible = founders.filter((f) => {
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
        <div className="brand-mark" title="Adventure Studio">
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              d="M3 19 11 4l4 7-4 8H3Z M13 19l4-8 4 8h-8Z"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinejoin="round"
            />
          </svg>
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
              <span className="workspace-name font-semibold">Adventure Studio</span>
              <span className="cohort-tag">SG#01</span>
              <ChevronDown className="size-3! text-muted-foreground" />
            </Button>
            {workspaceOpen && (
              <div className="absolute top-11 left-0 z-20 w-64 rounded-md border border-border bg-card p-3 shadow-sm">
                <p className="mb-2 text-[10px] text-muted-foreground">WORKSPACES</p>
                <div className="flex items-center justify-between text-xs">
                  Adventure Studio · SG#01 <Check size={13} className="text-primary" />
                </div>
                <p className="mt-2 text-[10px] text-muted-foreground">Current cohort · Singapore</p>
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
              <div className="mb-2 flex items-center justify-end gap-2 text-xs">
                <CalendarDays size={13} className="text-muted-foreground" />
                October 10, 2026
              </div>
              <span className="text-[10px] text-muted-foreground">
                Simulated activity · No live sync
              </span>
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
              </div>
            </section>
            
            <section id="full-syllabus" className="mt-8 scroll-mt-6">
              <div className="section-heading">
                <div className="flex items-center gap-2">
                  <CalendarDays size={14} />
                  <h2>Full Syllabus Timeline</h2>
                </div>
              </div>
              <div className="flex flex-col gap-3 pt-2">
                {allSyllabusEvents.map((event: any, idx: number) => (
                  <div key={idx} className="flex flex-col gap-1 rounded-md border border-border p-3 shadow-sm bg-card hover:bg-accent/50 transition-colors">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-bold text-primary">{event["Week"]} · {event["Day"]}</span>
                      <span className="text-[9px] text-muted-foreground">
                        {event["Date"] ? new Date(event["Date"]).toLocaleDateString("en-US", { month: 'short', day: 'numeric' }) : "TBD"}
                      </span>
                    </div>
                    {event["Sprint Phase"] && (
                      <h3 className="text-[12px] font-semibold">{event["Sprint Phase"]}</h3>
                    )}
                    {event["Exercise / Activity"] && (
                      <p className="text-[11px] text-muted-foreground mt-1">
                        <strong className="text-foreground">Activity:</strong> {event["Exercise / Activity"]}
                      </p>
                    )}
                    {event["Weekly Deliverable / Milestone"] && (
                      <p className="text-[11px] text-muted-foreground mt-1">
                        <strong className="text-foreground">Deliverable:</strong> {event["Weekly Deliverable / Milestone"]}
                      </p>
                    )}
                    {event["Owner / Lead"] && (
                      <p className="text-[10px] text-muted-foreground mt-1">
                        <strong className="text-foreground">Lead:</strong> {event["Owner / Lead"]}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </section>
          </div>
          <footer className="page-footer">
            <span className="flex items-center gap-1.5">
              <Command size={11} />
              Adventure Studio<span className="mx-2">/</span>Built for founder momentum.
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
            <SheetTitle>Adventure Studio</SheetTitle>
            <SheetDescription>{notice}</SheetDescription>
          </SheetHeader>
        </SheetContent>
      </Sheet>
      
      <AiChatOverlay 
        isOpen={chatOpen} 
        onClose={() => setChatOpen(false)} 
        role={isMember ? (perspective === "demo-founder-01" ? "Demo Founder A" : "Demo Founder B") : "Program Coordinator"} 
      />
    </div>
  );
}
