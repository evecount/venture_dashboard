import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  DashDataProvider,
  useDashData,
  type DashSnapshot,
  type SignalRow,
} from "@/hooks/use-dash-data";
import { useAuth } from "@/components/auth/sign-in-gate";
import type { Identity } from "@/lib/dash-auth";
import {
  Activity,
  Check,
  ChevronDown,
  CircleAlert,
  Flag,
  GitPullRequest,
  LayoutGrid,
  LogOut,
  MessageSquare,
  Search,
  Sun,
  Undo2,
  Video,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { type Founder, type DemoPerspective, isStudioRole } from "./data";
import { attentionReason, isHandled, relativeTime } from "./roster";
import { formatDay, programState, sgtDate, type ProgramState, type SyllabusEvent } from "./program";
import { gateStatus, upcomingMilestones, weeklyProgress } from "./insights";
import { setByLabel } from "./milestones";
import { GateBoard, GateMatrix } from "./gates";
import { StartupPage } from "./startup-page";
import { DeveloperLink } from "./developer-link";
import {
  GatePill,
  HealthPill,
  Kpi,
  PageHead,
  StreamTag,
  Progress,
  WeekBars,
  gateLabel,
  greeting,
  initials,
  startupName,
} from "./parts";
import { ViewAs } from "./studio-perspectives";

type Tab = "today" | "cohort" | "activity" | "program";

type Props = {
  initialPerspective?: DemoPerspective;
  onPerspectiveChange?: (value: DemoPerspective) => void;
  /** Startup page open from the URL (?s=), so it can be linked and the browser's back button works. */
  openStartupId?: string | undefined;
  onOpenStartup?: (id: string | undefined) => void;
};

export function CommandCenter(props: Props = {}) {
  return (
    <DashDataProvider>
      <Dashboard {...props} />
    </DashDataProvider>
  );
}

function AccountMenu({ identity, onSignOut }: { identity: Identity; onSignOut: () => void }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="avatar account"
          aria-label={`Signed in as ${identity.name}`}
        >
          {initials(identity.name)}
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-60 p-0">
        <div className="border-b border-border px-4 py-3">
          <p className="truncate text-sm font-semibold">{identity.name}</p>
          <p className="text-xs text-muted-foreground">
            {identity.role === "mentor"
              ? "Mentor · sees the whole cohort"
              : "Founder · sees your venture"}
          </p>
        </div>
        <DeveloperLink />
        <button
          type="button"
          className="flex w-full items-center gap-2 px-4 py-3 text-left text-sm hover:bg-secondary"
          onClick={onSignOut}
        >
          <LogOut size={15} /> Sign out
        </button>
      </PopoverContent>
    </Popover>
  );
}

function Dashboard({
  initialPerspective = "coordinator",
  onPerspectiveChange,
  openStartupId,
  onOpenStartup,
}: Props) {
  const { identity, signOut } = useAuth();
  const { roster, snapshot, handled, setHandled, handledError, lastSync, error } = useDashData();
  const isMentor = identity.role === "mentor";
  // Mentors can preview a founder's layout; a founder always sees their own startup (the server only sends theirs).
  const [preview, setPreview] = useState<DemoPerspective>(initialPerspective);
  const perspective: DemoPerspective = isMentor ? preview : identity.startupId;
  const [founderList, setFounderList] = useState<Founder[]>([]);
  const [tab, setTab] = useState<Tab>("today");
  const [now, setNow] = useState(() => new Date());
  const searchRef = useRef<HTMLInputElement>(null);

  const memberRow = isStudioRole(perspective)
    ? undefined
    : founderList.find((f) => f.id === perspective || f.founderIds?.includes(perspective));
  const isMember = !isMentor || memberRow !== undefined;
  const program = useMemo(() => programState(now), [now]);
  const opened =
    isMentor && !isMember ? founderList.find((f) => f.id === openStartupId) : undefined;

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(t);
  }, []);

  // Pulse cards whose latest check-in just changed.
  useEffect(() => {
    if (!roster) return;
    let pulsed = false;
    setFounderList((prev) =>
      roster.map((r) => {
        const old = prev.find((p) => p.id === r.id);
        const changed =
          !!old &&
          (old.digest !== r.digest || old.progress !== r.progress || old.status !== r.status);
        pulsed ||= changed;
        return { ...r, isPulsing: changed };
      }),
    );
    // Only re-render again to clear the highlight when something actually changed.
    if (!pulsed) return;
    const t = setTimeout(
      () => setFounderList((p) => p.map((f) => ({ ...f, isPulsing: false }))),
      4000,
    );
    return () => clearTimeout(t);
  }, [roster]);

  // ⌘K / Ctrl+K jumps to the cohort search.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k" && !isMember) {
        e.preventDefault();
        onOpenStartup?.(undefined);
        setTab("cohort");
        setTimeout(() => searchRef.current?.focus(), 0);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isMember, onOpenStartup]);

  // Scroll to the top only when a different startup is opened. Keyed on the id: the startup object itself is
  // rebuilt on every 20-second refresh, which used to snap the page back to the top mid-scroll.
  const openedId = opened?.id;
  useEffect(() => {
    if (openedId) window.scrollTo({ top: 0 });
  }, [openedId]);

  function setPerspective(value: DemoPerspective) {
    setPreview(value);
    onPerspectiveChange?.(value);
    onOpenStartup?.(undefined);
    setTab("today");
  }

  const openStartup = (id: string) => onOpenStartup?.(id);
  const goTab = (t: Tab) => {
    onOpenStartup?.(undefined);
    setTab(t);
  };

  const openItems = founderList.filter(
    (f) => attentionReason(f) !== null && !isHandled(f, handled[f.id]),
  );

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

  const liveConnected = !error && lastSync !== null;
  const syncText = error
    ? "Can't reach the server"
    : lastSync
      ? `Updated ${relativeTime(lastSync.toISOString(), now)}`
      : "Loading…";

  let body: ReactNode;
  if (!snapshot || !roster) {
    body = <p className="empty">Loading the cohort…</p>;
  } else if (isMember && !memberRow) {
    body = <p className="empty">Your startup isn&apos;t set up yet. Ask the studio team.</p>;
  } else if (isMember && memberRow) {
    body =
      tab === "program" ? (
        <ProgramView
          program={program}
          now={now}
          founders={[memberRow]}
          snapshot={snapshot}
          openStartup={() => setTab("today")}
        />
      ) : (
        <StartupPage
          founder={memberRow}
          program={program}
          now={now}
          snapshot={snapshot}
          isMentor={false}
        />
      );
  } else if (opened) {
    body = (
      <StartupPage
        founder={opened}
        program={program}
        now={now}
        snapshot={snapshot}
        isMentor
        onBack={() => window.history.back()}
      />
    );
  } else if (tab === "today") {
    body = (
      <TodayView
        founders={founderList}
        program={program}
        now={now}
        snapshot={snapshot}
        handled={handled}
        handledError={handledError}
        onHandle={setHandled}
        openStartup={openStartup}
      />
    );
  } else if (tab === "cohort") {
    body = (
      <CohortView
        founders={founderList}
        program={program}
        now={now}
        snapshot={snapshot}
        openStartup={openStartup}
        searchRef={searchRef}
      />
    );
  } else if (tab === "activity") {
    body = <ActivityView signals={snapshot.signals} founders={founderList} now={now} />;
  } else {
    body = (
      <ProgramView
        program={program}
        now={now}
        founders={founderList}
        snapshot={snapshot}
        openStartup={openStartup}
      />
    );
  }

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
                className={`tab-btn ${tab === t.id && !opened ? "active" : ""}`}
                aria-current={tab === t.id && !opened ? "page" : undefined}
                onClick={() => goTab(t.id)}
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
              title={liveConnected ? "Refreshes every 20 seconds" : "Not updating"}
            >
              <span className={`live-dot ${liveConnected ? "" : "off"}`} />
              <span className="hide-sm">{syncText}</span>
            </span>
            {isMentor && (
              <ViewAs perspective={perspective} members={founderList} onChange={setPerspective} />
            )}
            <AccountMenu identity={identity} onSignOut={() => void signOut()} />
          </div>
        </div>
      </header>

      <main className="dash-main">
        {body}
        <footer className="page-footer">
          <span>Adventure Studio · Cohort SG#01</span>
          <span>From founders&apos; Slack check-ins and connected tools · All times SGT</span>
        </footer>
      </main>
    </div>
  );
}

function TodayView({
  founders,
  program,
  now,
  snapshot,
  handled,
  handledError,
  onHandle,
  openStartup,
}: {
  founders: Founder[];
  program: ProgramState;
  now: Date;
  snapshot: DashSnapshot;
  handled: Record<string, string>;
  handledError: boolean;
  onHandle: (startupId: string, value: boolean) => void;
  openStartup: (id: string) => void;
}) {
  const n = founders.length;
  const quiet = founders.filter((f) => f.health === "quiet").length;
  const blocked = founders.filter(
    (f) => f.health === "blocked" && !isHandled(f, handled[f.id]),
  ).length;
  const w = program.weeks.find((x) => x.week === program.week);
  const atRisk = w
    ? founders.filter((f) => {
        const s = gateStatus(f.id, w, snapshot.submissions, snapshot.signals, now).state;
        return s === "behind" || s === "blocked" || s === "no_update";
      }).length
    : 0;
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
          tone={program.daysToGate !== null && program.daysToGate <= 2 ? "warning" : undefined}
        />
        <Kpi
          label="At risk for this gate"
          value={`${atRisk} / ${n}`}
          sub={atRisk ? "Behind, blocked or no update" : "Everyone on track"}
          tone={atRisk ? "warning" : n ? "success" : undefined}
        />
        <Kpi
          label="Checked in, last 7 days"
          value={`${n - quiet} / ${n}`}
          sub={!n ? "No startups yet" : quiet ? `${quiet} quiet` : "Everyone checked in"}
          tone={n ? (quiet ? "warning" : "success") : undefined}
        />
        <Kpi
          label="Open blockers"
          value={blocked}
          sub={blocked ? "Waiting on the studio" : "None reported"}
          tone={blocked ? "danger" : undefined}
        />
      </div>

      <GateBoard
        founders={founders}
        program={program}
        subs={snapshot.submissions}
        signals={snapshot.signals}
        now={now}
        openStartup={openStartup}
      />

      <div className="today-grid">
        <div className="stack">
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
            {open.length === 0 ? (
              <div className="empty">
                <Check size={18} className="text-success" />
                <p className="font-medium text-foreground">All clear</p>
                <p>No startup is blocked or quiet right now.</p>
              </div>
            ) : (
              <ul className="rows">
                {open.map((f) => (
                  <li key={f.id} className={`row ${f.isPulsing ? "pulsing" : ""}`}>
                    <button type="button" className="row-main" onClick={() => openStartup(f.id)}>
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
        </div>
        <ComingUp founders={founders} snapshot={snapshot} now={now} openStartup={openStartup} />
      </div>
    </>
  );
}

/** Open milestones across the cohort, earliest due first (no due date last). */
function ComingUp({
  founders,
  snapshot,
  now,
  openStartup,
}: {
  founders: Founder[];
  snapshot: DashSnapshot;
  now: Date;
  openStartup: (id: string) => void;
}) {
  const [showAll, setShowAll] = useState(false);
  const names = new Map(founders.map((f) => [f.id, startupName(f)]));
  const items = upcomingMilestones(snapshot.milestones, sgtDate(now)).filter((m) =>
    names.has(m.startup_id),
  );
  const LIMIT = 6;
  const shown = showAll ? items : items.slice(0, LIMIT);
  return (
    <section className="panel" aria-labelledby="coming-up">
      <div className="panel-head">
        <h2 id="coming-up">Coming up</h2>
        {items.length > 0 && <span className="panel-meta">Milestones, earliest due first</span>}
      </div>
      {items.length === 0 ? (
        <p className="muted-note">
          No open milestones. Founders and mentors set them through the bot, e.g. &ldquo;Set a
          milestone: 10 customer interviews by Oct 23&rdquo;.
        </p>
      ) : (
        <ol className="agenda">
          {shown.map((m) => {
            const done = m.goals.filter((g) => g.done).length;
            const by = setByLabel(m.set_by);
            return (
              <li key={m.id} className={m.overdue ? "overdue" : m.dueToday ? "now" : ""}>
                <button
                  type="button"
                  className="agenda-btn"
                  onClick={() => openStartup(m.startup_id)}
                >
                  <p className="agenda-when">
                    {m.due_date === null
                      ? "No due date"
                      : m.overdue
                        ? `Overdue · was due ${formatDay(m.due_date)}`
                        : m.dueToday
                          ? "Due today"
                          : `Due ${formatDay(m.due_date)}`}
                  </p>
                  <p className="agenda-what">{m.title}</p>
                  <p className="agenda-who">
                    {names.get(m.startup_id)}
                    {m.goals.length > 0 && (
                      <>
                        <span className="dot-sep">·</span>
                        {done}/{m.goals.length} goals
                      </>
                    )}
                    {by && (
                      <>
                        <span className="dot-sep">·</span>
                        Set by {by}
                      </>
                    )}
                  </p>
                </button>
              </li>
            );
          })}
        </ol>
      )}
      {items.length > LIMIT && (
        <Button variant="quiet" size="sm" className="mt-3" onClick={() => setShowAll(!showAll)}>
          {showAll ? "Show fewer" : `Show all ${items.length}`}
        </Button>
      )}
    </section>
  );
}

function CohortView({
  founders,
  program,
  now,
  snapshot,
  openStartup,
  searchRef,
}: {
  founders: Founder[];
  program: ProgramState;
  now: Date;
  snapshot: DashSnapshot;
  openStartup: (id: string) => void;
  searchRef: React.RefObject<HTMLInputElement | null>;
}) {
  const [filter, setFilter] = useState("All");
  const [search, setSearch] = useState("");
  const streams = Array.from(
    new Set(founders.map((f) => f.stream).filter((s) => s && s !== "Unassigned")),
  ).sort();
  const matches: Record<string, (f: Founder) => boolean> = {
    All: () => true,
    "Needs attention": (f) => attentionReason(f) !== null,
    ...Object.fromEntries(streams.map((s) => [s, (f: Founder) => f.stream === s])),
  };
  const w = program.weeks.find((x) => x.week === program.week);
  const visible = founders.filter(
    (f) =>
      (matches[filter] ?? matches["All"]!)(f) &&
      `${f.name} ${f.startup} ${f.lead}`.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <>
      <PageHead
        title="Cohort"
        sub={`${founders.length} startup${founders.length === 1 ? "" : "s"} · open one for its full page`}
      />
      <div className="toolbar">
        <div className="chips" role="group" aria-label="Filter startups">
          {Object.entries(matches).map(([c, fn]) => (
            <button
              key={c}
              type="button"
              className={`chip ${filter === c ? "active" : ""}`}
              aria-pressed={filter === c}
              onClick={() => setFilter(c)}
            >
              {c}
              <span className="chip-count">{founders.filter(fn).length}</span>
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
          {visible.map((f) => {
            const g = w ? gateStatus(f.id, w, snapshot.submissions, snapshot.signals, now) : null;
            return (
              <button
                key={f.id}
                type="button"
                className={`startup-card ${f.isPulsing ? "pulsing" : ""}`}
                onClick={() => openStartup(f.id)}
              >
                <span className="flex items-start justify-between gap-2">
                  <span className="min-w-0">
                    <span className="card-title">{startupName(f)}</span>
                    <span className="card-sub">{f.name}</span>
                  </span>
                  <HealthPill founder={f} />
                </span>
                <span className="card-digest">{f.digest}</span>
                <span className="card-trend">
                  <WeekBars
                    series={weeklyProgress(f.id, snapshot.submissions, program.weeks)}
                    current={program.week}
                  />
                </span>
                <span className="card-foot">
                  <span className="flex min-w-0 items-center gap-2">
                    {g && <GatePill state={g.state} title={g.reason} />}
                    <span className="truncate">{f.time === "—" ? "No check-in yet" : f.time}</span>
                  </span>
                  <StreamTag founder={f} />
                </span>
              </button>
            );
          })}
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

function ProgramView({
  program,
  now,
  founders,
  snapshot,
  openStartup,
}: {
  program: ProgramState;
  now: Date;
  founders: Founder[];
  snapshot: DashSnapshot;
  openStartup: (id: string) => void;
}) {
  const [week, setWeek] = useState(program.week);
  const today = sgtDate(now);
  const w = program.weeks.find((x) => x.week === week);
  return (
    <>
      <PageHead title="Program" sub={`12-week MVP program · currently week ${program.week}`} />
      {founders.length > 0 && (
        <GateMatrix
          founders={founders}
          program={program}
          subs={snapshot.submissions}
          signals={snapshot.signals}
          now={now}
          openStartup={openStartup}
        />
      )}
      <section className="panel mt-6" aria-labelledby="schedule-title">
        <div className="panel-head">
          <h2 id="schedule-title">Schedule</h2>
        </div>
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
          <div className="mt-6">
            <p className="eyebrow">
              Week {w.week}
              {w.week === program.week ? " · this week" : ""}
            </p>
            <h3 className="mt-1 text-lg font-semibold">{w.phase}</h3>
            {w.deliverable && (
              <div className="deliverable-box">
                <p className="eyebrow">Gate · {w.gateDate ? formatDay(w.gateDate) : "—"}</p>
                <p className="mt-1 font-medium">{w.deliverable}</p>
              </div>
            )}
            <ol className="agenda mt-5">
              {w.events.map((e: SyllabusEvent) => (
                <li
                  key={e.date}
                  className={e.date === today ? "now" : e.date < today ? "past" : ""}
                >
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
          </div>
        )}
      </section>
    </>
  );
}
