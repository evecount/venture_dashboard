import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { supabase } from "@/lib/supabase";
import { useLiveRoster } from "@/hooks/use-live-roster";
import { useLiveLedger, type SignalRow } from "@/hooks/use-live-ledger";
import { useHandled } from "@/hooks/use-handled";
import {
  Activity,
  CalendarDays,
  Check,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  Flag,
  GitPullRequest,
  LayoutGrid,
  MessageSquare,
  Search,
  Sun,
  Undo2,
  Users,
  Video,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { type Founder, type DemoPerspective, isStudioRole } from "./data";
import { attentionReason, isHandled, relativeTime } from "./roster";
import { formatDay, programState, sgtDate, type ProgramState, type SyllabusEvent } from "./program";
import { TeamPopover, ViewAs } from "./studio-perspectives";
import { Timeline } from "./timeline";
import { Milestones } from "./milestones";

type Tab = "today" | "cohort" | "activity" | "program";
type SheetTab = "Overview" | "Milestones" | "Timeline";

function initials(name: string): string {
  const parts = name.split(/[\s,]+/).filter(Boolean);
  if (parts.length === 1) return (parts[0] ?? "?").slice(0, 2).toUpperCase();
  return ((parts[0]?.[0] ?? "?") + (parts[1]?.[0] ?? "")).toUpperCase();
}

/** "Cybrdeck · tagline" -> "Cybrdeck" */
const startupName = (f: Founder) => f.startup.split(" · ")[0] ?? f.startup;

function HealthPill({ founder }: { founder: Founder }) {
  if (founder.health === "blocked") {
    return (
      <span className="pill pill-danger">
        <CircleAlert size={11} /> Blocked
      </span>
    );
  }
  if (founder.health === "quiet")
    return (
      <span className="pill pill-warning" title={founder.healthDetail}>
        Quiet
      </span>
    );
  return <span className="pill pill-success">On track</span>;
}

function StreamTag({ founder }: { founder: Founder }) {
  const unassigned = !founder.stream || founder.stream === "Unassigned";
  return (
    <span
      className="pill pill-neutral"
      title={unassigned ? "No stream lead yet" : `Lead: ${founder.lead}`}
    >
      {unassigned ? "No stream lead" : founder.stream}
    </span>
  );
}

function Progress({ value }: { value: number }) {
  return (
    <div
      className="progress"
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div style={{ width: `${Math.max(2, Math.min(100, value))}%` }} />
    </div>
  );
}

function Kpi({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: ReactNode;
  sub: ReactNode;
  tone?: "warning" | "danger" | "success";
}) {
  return (
    <div className="kpi">
      <p className="kpi-label">{label}</p>
      <p className="kpi-value">{value}</p>
      <p className={`kpi-sub ${tone ? `text-${tone === "danger" ? "danger" : tone}` : ""}`}>
        {sub}
      </p>
    </div>
  );
}

function greeting(now: Date): string {
  const hour = Number(
    new Intl.DateTimeFormat("en-SG", {
      hour: "numeric",
      hourCycle: "h23",
      timeZone: "Asia/Singapore",
    }).format(now),
  );
  return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}

function gateLabel(p: ProgramState): string {
  if (p.daysToGate === null) return "—";
  if (p.daysToGate <= 0) return "Today";
  return `${p.daysToGate} day${p.daysToGate === 1 ? "" : "s"}`;
}

export function CommandCenter({
  initialPerspective = "coordinator",
  onPerspectiveChange,
}: {
  initialPerspective?: DemoPerspective;
  onPerspectiveChange?: (value: DemoPerspective) => void;
} = {}) {
  const [perspective, setPerspectiveState] = useState<DemoPerspective>(initialPerspective);
  const [founderList, setFounderList] = useState<Founder[]>([]);
  const [signals, setSignals] = useState<SignalRow[]>([]);
  const [tab, setTab] = useState<Tab>("today");
  const [selected, setSelected] = useState<Founder | null>(null);
  const [sheetTab, setSheetTab] = useState<SheetTab>("Overview");
  const [now, setNow] = useState(() => new Date());
  const [lastSync, setLastSync] = useState<Date | null>(null);
  const roster = useLiveRoster();
  const { handled, setMark, error: handledError } = useHandled();
  const searchRef = useRef<HTMLInputElement>(null);

  const memberRow = isStudioRole(perspective)
    ? undefined
    : founderList.find((f) => f.id === perspective || f.founderIds?.includes(perspective));
  const isMember = memberRow !== undefined;
  const program = useMemo(() => programState(now), [now]);

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(t);
  }, []);

  // Live ledger: load the real roster and pulse cards that just changed.
  useEffect(() => {
    if (!roster) return;
    setLastSync(new Date());
    setFounderList((prev) =>
      roster.map((r) => {
        const old = prev.find((p) => p.id === r.id);
        const changed =
          !!old &&
          (old.digest !== r.digest || old.progress !== r.progress || old.status !== r.status);
        return { ...r, isPulsing: changed };
      }),
    );
    const t = setTimeout(
      () => setFounderList((p) => p.map((f) => ({ ...f, isPulsing: false }))),
      4000,
    );
    return () => clearTimeout(t);
  }, [roster]);

  const { connected: liveConnected } = useLiveLedger({
    onSubmission: () => {}, // the roster refetches on submission changes
    onSignals: (rows, live) => {
      setLastSync(new Date());
      setSignals((prev) => (live ? [...rows, ...prev] : rows));
    },
  });

  // ⌘K / Ctrl+K jumps to the cohort search.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k" && !isMember) {
        e.preventDefault();
        setTab("cohort");
        setTimeout(() => searchRef.current?.focus(), 0);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isMember]);

  function setPerspective(value: DemoPerspective) {
    setPerspectiveState(value);
    onPerspectiveChange?.(value);
    setSelected(null);
    setTab("today");
  }

  function openFounder(f: Founder, t: SheetTab = "Overview") {
    setSelected(f);
    setSheetTab(t);
  }

  const attention = founderList.filter((f) => attentionReason(f) !== null);
  const openItems = attention.filter((f) => !isHandled(f, handled[f.id]));

  const tabs: Array<{ id: Tab; label: string; icon: ReactNode; badge?: number }> = isMember
    ? [
        { id: "today", label: "My venture", icon: <Sun size={16} /> },
        { id: "program", label: "Program", icon: <Flag size={16} /> },
      ]
    : [
        { id: "today", label: "Today", icon: <Sun size={16} />, badge: openItems.length },
        { id: "cohort", label: "Cohort", icon: <LayoutGrid size={16} /> },
        { id: "activity", label: "Activity", icon: <Activity size={16} /> },
        { id: "program", label: "Program", icon: <Flag size={16} /> },
      ];

  const syncText = !supabase
    ? "Not connected"
    : lastSync
      ? `Updated ${relativeTime(lastSync.toISOString(), now)}`
      : "Connecting…";

  return (
    <div className="dash">
      <header className="dash-header">
        <div className="dash-header-inner">
          <div className="flex min-w-0 items-center gap-3">
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
            <span className="hide-sm truncate font-semibold">Adventure Studio</span>
            <span className="cohort-tag">SG#01</span>
          </div>
          <nav className="tab-nav" aria-label="Dashboard sections">
            {tabs.map((t) => (
              <button
                key={t.id}
                type="button"
                className={`tab-btn ${tab === t.id ? "active" : ""}`}
                aria-current={tab === t.id ? "page" : undefined}
                onClick={() => setTab(t.id)}
              >
                {t.icon}
                <span>{t.label}</span>
                {!!t.badge && <span className="tab-badge">{t.badge}</span>}
              </button>
            ))}
          </nav>
          <div className="flex items-center justify-end gap-2">
            <span
              className="sync-status"
              title={liveConnected ? "Live updates on" : "Live updates off"}
            >
              <span className={`live-dot ${liveConnected ? "" : "off"}`} />
              <span className="hide-sm">{syncText}</span>
            </span>
            <TeamPopover perspective={perspective} />
            <ViewAs perspective={perspective} members={founderList} onChange={setPerspective} />
          </div>
        </div>
      </header>

      <main className="dash-main">
        {isMember && memberRow ? (
          tab === "program" ? (
            <ProgramView program={program} now={now} />
          ) : (
            <MemberView founder={memberRow} program={program} now={now} openFounder={openFounder} />
          )
        ) : (
          <>
            {tab === "today" && (
              <TodayView
                founders={founderList}
                program={program}
                now={now}
                handled={handled}
                handledError={handledError}
                onHandle={setMark}
                openFounder={openFounder}
                loaded={roster !== null || !supabase}
              />
            )}
            {tab === "cohort" && (
              <CohortView founders={founderList} openFounder={openFounder} searchRef={searchRef} />
            )}
            {tab === "activity" && (
              <ActivityView signals={signals} founders={founderList} now={now} />
            )}
            {tab === "program" && <ProgramView program={program} now={now} />}
          </>
        )}
        <footer className="page-footer">
          <span>Adventure Studio · Cohort SG#01</span>
          <span>From founders&apos; Slack check-ins and connected tools · All times SGT</span>
        </footer>
      </main>

      <FounderSheet
        founder={selected ? (founderList.find((f) => f.id === selected.id) ?? selected) : null}
        tab={sheetTab}
        onTab={setSheetTab}
        program={program}
        onClose={() => setSelected(null)}
      />
    </div>
  );
}

function PageHead({ title, sub, right }: { title: ReactNode; sub: ReactNode; right?: ReactNode }) {
  return (
    <div className="page-head">
      <div className="min-w-0">
        <h1>{title}</h1>
        <p>{sub}</p>
      </div>
      {right}
    </div>
  );
}

function TodayView({
  founders,
  program,
  now,
  handled,
  handledError,
  onHandle,
  openFounder,
  loaded,
}: {
  founders: Founder[];
  program: ProgramState;
  now: Date;
  handled: Record<string, string>;
  handledError: boolean;
  onHandle: (startupId: string, value: boolean) => void;
  openFounder: (f: Founder, t?: SheetTab) => void;
  loaded: boolean;
}) {
  const n = founders.length;
  const quiet = founders.filter((f) => f.health === "quiet").length;
  const blocked = founders.filter(
    (f) => f.health === "blocked" && !isHandled(f, handled[f.id]),
  ).length;
  const avg = n ? Math.round(founders.reduce((a, f) => a + f.progress, 0) / n) : 0;
  const attention = founders.filter((f) => attentionReason(f) !== null);
  const open = attention.filter((f) => !isHandled(f, handled[f.id]));
  const done = attention.filter((f) => isHandled(f, handled[f.id]));

  return (
    <>
      <PageHead
        title={greeting(now)}
        sub={
          <>
            Week {program.week} of {program.totalWeeks}
            <span className="dot-sep">·</span>
            {program.phase}
          </>
        }
        right={
          <span className="page-date">
            {formatDay(sgtDate(now), { weekday: "short", day: "numeric", month: "long" })}
          </span>
        }
      />

      <div className="kpi-strip">
        <Kpi
          label="Next gate"
          value={gateLabel(program)}
          sub={program.gateDate ? formatDay(program.gateDate) : "No gate scheduled"}
          {...(program.daysToGate !== null && program.daysToGate <= 2
            ? { tone: "warning" as const }
            : {})}
        />
        <Kpi
          label="Checked in, last 7 days"
          value={loaded ? `${n - quiet} / ${n}` : "—"}
          sub={
            !loaded
              ? "Loading"
              : !n
                ? "No startups yet"
                : quiet
                  ? `${quiet} quiet`
                  : "Everyone checked in"
          }
          {...(loaded && n ? { tone: quiet ? ("warning" as const) : ("success" as const) } : {})}
        />
        <Kpi
          label="Open blockers"
          value={loaded ? blocked : "—"}
          sub={!loaded ? "Loading" : blocked ? "Waiting on the studio" : "None reported"}
          {...(blocked ? { tone: "danger" as const } : {})}
        />
        <Kpi
          label="Average progress"
          value={loaded ? `${avg}%` : "—"}
          sub="From latest check-ins"
        />
      </div>

      <div className="today-grid">
        <section className="panel" aria-labelledby="needs-you">
          <div className="panel-head">
            <h2 id="needs-you">Needs you</h2>
            {open.length > 0 && <span className="pill pill-warning">{open.length}</span>}
          </div>
          {handledError && (
            <p className="mb-2 text-xs text-danger">
              Couldn&apos;t save that. Check your connection and try again.
            </p>
          )}
          {!loaded ? (
            <p className="empty">Loading the cohort…</p>
          ) : open.length === 0 ? (
            <div className="empty">
              <Check size={18} className="text-success" />
              <p className="font-medium text-foreground">All clear</p>
              <p>No startup is blocked or quiet right now.</p>
            </div>
          ) : (
            <ul className="rows">
              {open.map((f) => (
                <li key={f.id} className={`row ${f.isPulsing ? "pulsing" : ""}`}>
                  <button
                    type="button"
                    className="row-main"
                    onClick={() => openFounder(f, "Timeline")}
                  >
                    <span className="avatar">{initials(startupName(f))}</span>
                    <span className="min-w-0 flex-1">
                      <span className="row-title">
                        {startupName(f)} <span className="row-meta">· {f.name}</span>
                      </span>
                      <span className="row-reason">{attentionReason(f)}</span>
                    </span>
                    <HealthPill founder={f} />
                  </button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="row-action"
                    aria-label={`Mark ${startupName(f)} handled`}
                    onClick={() => onHandle(f.id, true)}
                  >
                    <Check size={14} /> <span className="hide-sm">Mark handled</span>
                  </Button>
                </li>
              ))}
            </ul>
          )}
          {done.length > 0 && (
            <details className="handled">
              <summary>Handled · {done.length}</summary>
              <ul className="rows">
                {done.map((f) => (
                  <li key={f.id} className="row muted">
                    <span className="avatar">{initials(startupName(f))}</span>
                    <span className="min-w-0 flex-1">
                      <span className="row-title">{startupName(f)}</span>
                      <span className="row-reason">
                        Handled {relativeTime(handled[f.id] ?? "", now)} · reopens on the next
                        check-in
                      </span>
                    </span>
                    <Button variant="quiet" size="sm" onClick={() => onHandle(f.id, false)}>
                      <Undo2 size={14} /> Undo
                    </Button>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </section>
        <ThisWeek program={program} now={now} />
      </div>
    </>
  );
}

function ThisWeek({ program, now }: { program: ProgramState; now: Date }) {
  const today = sgtDate(now);
  return (
    <section className="panel" aria-labelledby="this-week">
      <div className="panel-head">
        <h2 id="this-week">Coming up</h2>
      </div>
      {program.upcoming.length === 0 ? (
        <p className="empty">The program schedule is complete.</p>
      ) : (
        <ol className="agenda">
          {program.upcoming.map((e) => (
            <li key={e.date} className={e.date === today ? "now" : ""}>
              <p className="agenda-when">{e.date === today ? "Today" : formatDay(e.date)}</p>
              <p className="agenda-what">{e.deliverable ? `Gate: ${e.deliverable}` : e.focus}</p>
              <p className="agenda-who">{e.owner}</p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function MemberView({
  founder,
  program,
  now,
  openFounder,
}: {
  founder: Founder;
  program: ProgramState;
  now: Date;
  openFounder: (f: Founder, t?: SheetTab) => void;
}) {
  const blocker = founder.blocker && founder.blocker !== "None" ? founder.blocker : null;
  return (
    <>
      <PageHead
        title={startupName(founder)}
        sub={
          <>
            {founder.name}
            <span className="dot-sep">·</span>Week {program.week} of {program.totalWeeks}
          </>
        }
        right={<HealthPill founder={founder} />}
      />
      <div className="kpi-strip">
        <Kpi
          label="Next gate"
          value={gateLabel(program)}
          sub={program.gateDate ? formatDay(program.gateDate) : "—"}
        />
        <Kpi label="Your progress" value={`${founder.progress}%`} sub="From your latest check-in" />
        <Kpi
          label="Last check-in"
          value={founder.time === "—" ? "None yet" : founder.time}
          sub="Message the bot in Slack to add one"
        />
        <Kpi
          label="Stream lead"
          value={
            <span className="text-lg">
              {founder.lead && founder.lead !== "Unassigned" ? founder.lead : "Not assigned yet"}
            </span>
          }
          sub={
            founder.stream && founder.stream !== "Unassigned"
              ? `${founder.stream} stream`
              : "The studio will assign one"
          }
        />
      </div>
      <div className="today-grid">
        <section className="panel" aria-labelledby="my-latest">
          <div className="panel-head">
            <h2 id="my-latest">Your latest check-in</h2>
          </div>
          <p className="text-sm leading-relaxed">{founder.digest}</p>
          {blocker && (
            <div className="callout danger mt-4">
              <p className="font-medium">Waiting on the studio</p>
              <p>{blocker}</p>
            </div>
          )}
          <div className="mt-5 rounded-lg bg-secondary p-4">
            <p className="text-xs text-muted-foreground">
              Due {program.gateDate ? formatDay(program.gateDate) : "this week"}
            </p>
            <p className="mt-1 text-sm font-medium">
              {program.deliverable || "No deliverable this week"}
            </p>
          </div>
          <div className="mt-5 flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => openFounder(founder, "Timeline")}>
              <MessageSquare size={14} /> Check-in history
            </Button>
            <Button variant="outline" size="sm" onClick={() => openFounder(founder, "Milestones")}>
              <Flag size={14} /> Milestones
            </Button>
          </div>
        </section>
        <ThisWeek program={program} now={now} />
      </div>
    </>
  );
}

function CohortView({
  founders,
  openFounder,
  searchRef,
}: {
  founders: Founder[];
  openFounder: (f: Founder, t?: SheetTab) => void;
  searchRef: React.RefObject<HTMLInputElement | null>;
}) {
  const [filter, setFilter] = useState("All");
  const [search, setSearch] = useState("");
  const streams = Array.from(
    new Set(founders.map((f) => f.stream).filter((s) => s && s !== "Unassigned")),
  ).sort();
  const chips = ["All", "Needs attention", ...streams];
  const visible = founders.filter(
    (f) =>
      (filter === "All" ||
        (filter === "Needs attention" && attentionReason(f) !== null) ||
        f.stream === filter) &&
      `${f.name} ${f.startup} ${f.lead}`.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <>
      <PageHead
        title="Cohort"
        sub={`${founders.length} startup${founders.length === 1 ? "" : "s"} · click one for check-ins, milestones and history`}
      />
      <div className="toolbar">
        <div className="chips" role="group" aria-label="Filter startups">
          {chips.map((c) => (
            <button
              key={c}
              type="button"
              className={`chip ${filter === c ? "active" : ""}`}
              aria-pressed={filter === c}
              onClick={() => setFilter(c)}
            >
              {c}
              <span className="chip-count">
                {c === "All"
                  ? founders.length
                  : c === "Needs attention"
                    ? founders.filter((f) => attentionReason(f) !== null).length
                    : founders.filter((f) => f.stream === c).length}
              </span>
            </button>
          ))}
        </div>
        <label className="search-field">
          <Search size={15} className="text-muted-foreground" />
          <input
            ref={searchRef}
            aria-label="Search startups"
            placeholder="Search startups or founders"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <kbd className="hide-sm">⌘K</kbd>
        </label>
      </div>
      {visible.length === 0 ? (
        <div className="panel empty">
          <p className="font-medium text-foreground">No startups match</p>
          <Button
            variant="link"
            size="sm"
            onClick={() => {
              setFilter("All");
              setSearch("");
            }}
          >
            Clear filters
          </Button>
        </div>
      ) : (
        <div className="card-grid">
          {visible.map((f) => (
            <button
              key={f.id}
              type="button"
              className={`startup-card ${f.isPulsing ? "pulsing" : ""}`}
              onClick={() => openFounder(f)}
            >
              <span className="flex items-start justify-between gap-2">
                <span className="min-w-0">
                  <span className="card-title">{startupName(f)}</span>
                  <span className="card-sub">{f.name}</span>
                </span>
                <HealthPill founder={f} />
              </span>
              <span className="card-digest">{f.digest}</span>
              <span className="mt-auto block">
                <Progress value={f.progress} />
                <span className="card-foot">
                  <span>
                    {f.progress}% · {f.time === "—" ? "no check-in yet" : f.time}
                  </span>
                  <StreamTag founder={f} />
                </span>
              </span>
            </button>
          ))}
        </div>
      )}
    </>
  );
}

const KIND: Record<string, { group: string; noun: string; icon: ReactNode; tone: string }> = {
  checkin: {
    group: "Check-ins",
    noun: "check-in",
    icon: <MessageSquare size={14} />,
    tone: "text-success",
  },
  deliverable_submitted: {
    group: "Check-ins",
    noun: "deliverable",
    icon: <Check size={14} />,
    tone: "text-success",
  },
  ai_digest: {
    group: "Check-ins",
    noun: "digest",
    icon: <MessageSquare size={14} />,
    tone: "text-primary",
  },
  blocker: {
    group: "Blockers",
    noun: "blocker",
    icon: <CircleAlert size={14} />,
    tone: "text-danger",
  },
  unblocked: {
    group: "Blockers",
    noun: "unblock",
    icon: <Check size={14} />,
    tone: "text-success",
  },
  commit: { group: "Work", noun: "push", icon: <GitPullRequest size={14} />, tone: "text-info" },
  pull_request: {
    group: "Work",
    noun: "PR update",
    icon: <GitPullRequest size={14} />,
    tone: "text-info",
  },
  issue: { group: "Work", noun: "issue", icon: <GitPullRequest size={14} />, tone: "text-info" },
  meeting: {
    group: "Meetings",
    noun: "meeting",
    icon: <Video size={14} />,
    tone: "text-muted-foreground",
  },
};
const kindOf = (type: string) =>
  KIND[type] ?? {
    group: "Other",
    noun: "update",
    icon: <Activity size={14} />,
    tone: "text-muted-foreground",
  };

function dayLabel(iso: string, now: Date): string {
  const d = sgtDate(new Date(iso));
  const today = sgtDate(now);
  const yesterday = sgtDate(new Date(now.getTime() - 86_400_000));
  return d === today ? "Today" : d === yesterday ? "Yesterday" : formatDay(d);
}

function ActivityView({
  signals,
  founders,
  now,
}: {
  signals: SignalRow[];
  founders: Founder[];
  now: Date;
}) {
  const [filter, setFilter] = useState("All");
  const names = Object.fromEntries(founders.map((f) => [f.id, startupName(f)]));
  const filtered = signals.filter((s) => filter === "All" || kindOf(s.type).group === filter);
  const chips = ["All", ...Array.from(new Set(signals.map((s) => kindOf(s.type).group)))];

  // Day -> (startup, kind group) bundles, so a burst of commits reads as one line.
  const days: Array<{
    label: string;
    groups: Array<{ key: string; startup: string; items: SignalRow[] }>;
  }> = [];
  for (const s of filtered) {
    const label = dayLabel(s.created_at, now);
    let day = days.find((d) => d.label === label);
    if (!day) days.push((day = { label, groups: [] }));
    const key = `${s.startup_id ?? "studio"}|${kindOf(s.type).group}`;
    let g = day.groups.find((x) => x.key === key);
    if (!g)
      day.groups.push(
        (g = { key, startup: (s.startup_id && names[s.startup_id]) || "Studio", items: [] }),
      );
    g.items.push(s);
  }

  return (
    <>
      <PageHead title="Activity" sub="Check-ins, blockers and connected work, newest first" />
      <div className="toolbar">
        <div className="chips" role="group" aria-label="Filter activity">
          {chips.map((c) => (
            <button
              key={c}
              type="button"
              className={`chip ${filter === c ? "active" : ""}`}
              aria-pressed={filter === c}
              onClick={() => setFilter(c)}
            >
              {c}
            </button>
          ))}
        </div>
      </div>
      {days.length === 0 ? (
        <div className="panel empty">
          <p>No activity yet. It appears here as founders check in and push work.</p>
        </div>
      ) : (
        days.map((d) => (
          <section key={d.label} className="mb-6">
            <h2 className="day-label">{d.label}</h2>
            <div className="panel p-0!">
              {d.groups.map((g) => (
                <ActivityGroup key={g.key} startup={g.startup} items={g.items} />
              ))}
            </div>
          </section>
        ))
      )}
    </>
  );
}

function ActivityGroup({ startup, items }: { startup: string; items: SignalRow[] }) {
  const [open, setOpen] = useState(false);
  const first = items[0]!;
  const kind = kindOf(first.type);
  const time = (iso: string) =>
    new Date(iso).toLocaleTimeString("en-SG", {
      hour: "numeric",
      minute: "2-digit",
      timeZone: "Asia/Singapore",
    });

  if (items.length === 1) {
    return (
      <div className="feed-row">
        <span className={`feed-icon ${kind.tone}`}>{kind.icon}</span>
        <div className="min-w-0 flex-1">
          <p className="feed-title">
            <span className="font-medium">{startup}</span> · {first.headline}
          </p>
          {first.detail && <p className="feed-detail">{first.detail}</p>}
        </div>
        <span className="feed-time">{time(first.created_at)}</span>
      </div>
    );
  }

  const counts: Record<string, number> = {};
  for (const s of items) counts[kindOf(s.type).noun] = (counts[kindOf(s.type).noun] ?? 0) + 1;
  const summary = Object.entries(counts)
    .map(([noun, c]) => `${c} ${noun}${c === 1 ? "" : noun.endsWith("h") ? "es" : "s"}`)
    .join(", ");

  return (
    <div className="feed-group">
      <button
        type="button"
        className="feed-row w-full text-left"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <span className={`feed-icon ${kind.tone}`}>{kind.icon}</span>
        <div className="min-w-0 flex-1">
          <p className="feed-title">
            <span className="font-medium">{startup}</span> · {summary}
          </p>
          <p className="feed-detail truncate">
            {items
              .slice(0, 3)
              .map((s) => s.detail || s.headline)
              .join(" · ")}
          </p>
        </div>
        <span className="feed-time">
          {time(items.at(-1)!.created_at)}–{time(first.created_at)}
        </span>
        <ChevronDown
          size={16}
          className={`text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <ul className="feed-children">
          {items.map((s) => (
            <li key={s.id}>
              <p className="feed-title">{s.headline}</p>
              {s.detail && <p className="feed-detail">{s.detail}</p>}
              <span className="feed-time">{time(s.created_at)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ProgramView({ program, now }: { program: ProgramState; now: Date }) {
  const [week, setWeek] = useState(program.week);
  const today = sgtDate(now);
  const w = program.weeks.find((x) => x.week === week);
  return (
    <>
      <PageHead title="Program" sub={`12-week MVP program · currently week ${program.week}`} />
      <div className="week-band" role="tablist" aria-label="Program weeks">
        {program.weeks.map((x) => (
          <button
            key={x.week}
            type="button"
            role="tab"
            aria-selected={x.week === week}
            title={x.phase}
            className={`week ${x.week < program.week ? "past" : ""} ${x.week === program.week ? "current" : ""} ${x.week === week ? "selected" : ""}`}
            onClick={() => setWeek(x.week)}
          >
            <span className="week-bar" />
            <span className="week-num">{x.week}</span>
          </button>
        ))}
      </div>
      {w && (
        <section className="panel mt-6">
          <p className="text-xs text-muted-foreground">
            Week {w.week}
            {w.week === program.week ? " · this week" : ""}
          </p>
          <h2 className="mt-1 text-lg font-semibold">{w.phase}</h2>
          {w.deliverable && (
            <div className="mt-4 rounded-lg bg-secondary p-4">
              <p className="text-xs text-muted-foreground">
                Gate · {w.gateDate ? formatDay(w.gateDate) : "—"}
              </p>
              <p className="mt-1 text-sm font-medium">{w.deliverable}</p>
            </div>
          )}
          <ol className="agenda mt-5">
            {w.events.map((e: SyllabusEvent) => (
              <li key={e.date} className={e.date === today ? "now" : e.date < today ? "past" : ""}>
                <p className="agenda-when">{e.date === today ? "Today" : formatDay(e.date)}</p>
                <p className="agenda-what">{e.focus}</p>
                <p className="agenda-who">
                  {e.activity}
                  <span className="dot-sep">·</span>
                  {e.owner}
                </p>
              </li>
            ))}
          </ol>
        </section>
      )}
    </>
  );
}

function FounderSheet({
  founder,
  tab,
  onTab,
  program,
  onClose,
}: {
  founder: Founder | null;
  tab: SheetTab;
  onTab: (t: SheetTab) => void;
  program: ProgramState;
  onClose: () => void;
}) {
  return (
    <Sheet
      open={founder !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <SheetContent className="detail-sheet sm:max-w-[560px]">
        {founder && (
          <>
            <SheetHeader className="p-0">
              <div className="flex items-center gap-3">
                <span className="avatar lg">{initials(startupName(founder))}</span>
                <div className="min-w-0">
                  <SheetTitle className="text-lg">{startupName(founder)}</SheetTitle>
                  <SheetDescription className="text-sm">{founder.name}</SheetDescription>
                </div>
              </div>
            </SheetHeader>
            <div className="mt-4 flex flex-wrap gap-2">
              <HealthPill founder={founder} />
              <StreamTag founder={founder} />
            </div>
            <div className="sheet-tabs" role="tablist">
              {(["Overview", "Milestones", "Timeline"] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  role="tab"
                  aria-selected={tab === t}
                  className={`chip ${tab === t ? "active" : ""}`}
                  onClick={() => onTab(t)}
                >
                  {t === "Timeline" ? "Check-in history" : t}
                </button>
              ))}
            </div>
            {tab === "Overview" && (
              <div className="space-y-6">
                <section>
                  <h3 className="detail-heading pt-0!">Latest check-in</h3>
                  <p className="text-sm leading-relaxed">{founder.digest}</p>
                  {founder.time !== "—" && (
                    <p className="mt-1 text-xs text-muted-foreground">{founder.time}</p>
                  )}
                  {founder.blocker && founder.blocker !== "None" && (
                    <div className="callout danger mt-3">
                      <p className="font-medium">Blocker</p>
                      <p>{founder.blocker}</p>
                    </div>
                  )}
                </section>
                <section>
                  <h3 className="detail-heading pt-0!">This week&apos;s deliverable</h3>
                  <p className="text-sm">{program.deliverable || "None this week"}</p>
                  <div className="mt-3 flex items-center gap-3">
                    <Progress value={founder.progress} />
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {founder.progress}%
                    </span>
                  </div>
                  {program.gateDate && (
                    <p className="mt-2 text-xs text-muted-foreground">
                      Gate {formatDay(program.gateDate)}
                    </p>
                  )}
                </section>
                {(founder.profile || founder.audience || founder.stack.length > 0) && (
                  <section>
                    <h3 className="detail-heading pt-0!">Profile</h3>
                    {founder.profile && (
                      <p className="text-sm leading-relaxed text-muted-foreground">
                        {founder.profile}
                      </p>
                    )}
                    {founder.audience && (
                      <p className="mt-3 text-sm">
                        <span className="text-muted-foreground">Target audience · </span>
                        {founder.audience}
                      </p>
                    )}
                    {founder.stack.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {founder.stack.map((s) => (
                          <span key={s} className="pill pill-neutral">
                            {s}
                          </span>
                        ))}
                      </div>
                    )}
                  </section>
                )}
                <section className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Users size={14} /> Stream lead: {founder.lead || "Unassigned"}
                  <span className="dot-sep">·</span>
                  <CalendarDays size={14} /> Week {program.week}
                </section>
              </div>
            )}
            {tab === "Milestones" && <Milestones founder={founder} />}
            {tab === "Timeline" && (
              <Timeline
                founder={founder}
                refreshKey={`${founder.digest}|${founder.progress}|${founder.status}`}
              />
            )}
            <Button variant="quiet" size="sm" className="mt-8" onClick={onClose}>
              <ChevronRight size={14} className="rotate-180" /> Back to dashboard
            </Button>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
