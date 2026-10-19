import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  DashDataProvider,
  useDashData,
  type DashSnapshot,
  type MeetingRow,
  type SignalRow,
} from "@/hooks/use-dash-data";
import { useAuth } from "@/components/auth/sign-in-gate";
import type { Identity } from "@/lib/dash-auth";
import {
  Activity,
  Check,
  ChevronDown,
  CircleDashed,
  CircleAlert,
  Flag,
  GitPullRequest,
  LayoutGrid,
  LogOut,
  MessageSquare,
  Search,
  Sun,
  Undo2,
  Users,
  Video,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { type Founder, type DemoPerspective, isStudioRole } from "./data";
import { attentionReason, isHandled, relativeTime } from "./roster";
import {
  cohortProgram,
  cohortStartMonday,
  formatDay,
  nextSprintSession,
  sgtDate,
  sgtTime,
  type ProgramState,
} from "./program";
import { gateStatus, setupGaps, upcomingMilestones, weeklyProgress } from "./insights";
import { setByLabel } from "./milestones";
import { GateBoard } from "./gates";
import { ProgramView } from "./program-view";
import { ComingUp, sprintMeeting } from "./coming-up";
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
  /** Cohort tab from the URL (?c=sg-02). */
  initialCohortId?: string | undefined;
  onCohortChange?: (id: string) => void;
};

const COHORT_KEY = "vd_cohort";

/** Only the given startups' rows. Meetings with no known startup (studio-wide) stay in every cohort. */
function scopeSnapshot(s: DashSnapshot, ids: Set<string>): DashSnapshot {
  const mine = <T extends { startup_id: string | null }>(rows: T[]) =>
    rows.filter((r) => r.startup_id !== null && ids.has(r.startup_id));
  return {
    ...s,
    startups: s.startups.filter((r) => ids.has(r.id)),
    founders: s.founders.filter((r) => ids.has(r.startup_id)),
    submissions: s.submissions.filter((r) => ids.has(r.startup_id)),
    signals: mine(s.signals),
    milestones: s.milestones.filter((m) => ids.has(m.startup_id)),
    notes: mine(s.notes),
    tasks: mine(s.tasks),
    meetings: s.meetings.filter(
      (m) => !m.startup_ids.length || m.startup_ids.some((id) => ids.has(id)),
    ),
  };
}

/** "Week 3 of 12", or when it starts / that it's finished. */
function cohortWeekLabel(now: Date, startDate: string, totalWeeks: number | null): string {
  const today = sgtDate(now);
  const start = cohortStartMonday(startDate);
  if (today < start) return `Starts ${formatDay(start)}`;
  const p = cohortProgram(now, startDate);
  const last = p.weeks.at(-1)?.gateDate;
  if (last && today > last) return "Finished";
  return `Week ${p.week} of ${totalWeeks ?? p.totalWeeks}`;
}

/** One line per cohort for the cohort bar: how many startups need a mentor and how many are at risk for the gate. */
function cohortHealth(
  now: Date,
  startDate: string,
  founders: Founder[],
  snapshot: DashSnapshot,
  handled: Record<string, string>,
): { text: string; tone: "warning" | "success" | "" } {
  if (!founders.length) return { text: "No startups yet", tone: "" };
  const p = cohortProgram(now, startDate);
  const w = p.weeks.find((x) => x.week === p.week);
  const needs = founders.filter(
    (f) => attentionReason(f) !== null && !isHandled(f, handled[f.id]),
  ).length;
  const atRisk = w
    ? founders.filter((f) => {
        const s = gateStatus(f.id, w, snapshot.submissions, snapshot.signals, now).state;
        return s === "behind" || s === "blocked" || s === "no_update";
      }).length
    : 0;
  const bits = [
    needs && `${needs} need${needs === 1 ? "s" : ""} you`,
    atRisk && `${atRisk} at risk`,
  ];
  const text = bits.filter(Boolean).join(" · ");
  return text ? { text, tone: "warning" } : { text: "All on track", tone: "success" };
}

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
  initialCohortId,
  onCohortChange,
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
  const opened =
    isMentor && !isMember ? founderList.find((f) => f.id === openStartupId) : undefined;

  // Cohort tabs: a founder (or a previewed founder) sees their own cohort; an opened startup shows its cohort;
  // otherwise the tab the mentor picked, remembered in the URL and this browser.
  const cohortList = useMemo(() => snapshot?.cohorts ?? [], [snapshot]);
  const [pickedCohort, setPickedCohort] = useState<string | undefined>(() => {
    if (initialCohortId) return initialCohortId;
    try {
      return localStorage.getItem(COHORT_KEY) ?? undefined;
    } catch {
      return undefined;
    }
  });
  const pickedValid = cohortList.some((c) => c.id === pickedCohort) ? pickedCohort : undefined;
  const cohortId =
    (isMember ? memberRow?.cohortId : opened?.cohortId) ?? pickedValid ?? cohortList[0]?.id;
  const cohort = cohortList.find((c) => c.id === cohortId);
  const cohortFounders = useMemo(
    () =>
      cohortList.length && cohortId
        ? founderList.filter((f) => f.cohortId === cohortId)
        : founderList,
    [founderList, cohortList, cohortId],
  );
  const view = useMemo(
    () => (snapshot ? scopeSnapshot(snapshot, new Set(cohortFounders.map((f) => f.id))) : null),
    [snapshot, cohortFounders],
  );
  const program = useMemo(() => cohortProgram(now, cohort?.start_date), [now, cohort?.start_date]);

  function pickCohort(id: string) {
    setPickedCohort(id);
    onCohortChange?.(id);
    try {
      localStorage.setItem(COHORT_KEY, id);
    } catch {
      /* private mode: the URL still remembers it */
    }
  }

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

  const openItems = cohortFounders.filter(
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
  if (!snapshot || !roster || !view) {
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
        key={cohortId}
        founders={cohortFounders}
        program={program}
        now={now}
        snapshot={view}
        handled={handled}
        handledError={handledError}
        onHandle={setHandled}
        openStartup={openStartup}
      />
    );
  } else if (tab === "cohort") {
    body = (
      <CohortView
        founders={cohortFounders}
        program={program}
        now={now}
        snapshot={view}
        openStartup={openStartup}
        searchRef={searchRef}
      />
    );
  } else if (tab === "activity") {
    body = <ActivityView signals={view.signals} founders={cohortFounders} now={now} />;
  } else {
    body = (
      <ProgramView
        key={cohortId}
        program={program}
        now={now}
        founders={cohortFounders}
        snapshot={view}
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
            <span className="cohort-tag">{cohort?.name ?? "MVP"}</span>
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

      {isMentor && !isMember && !opened && snapshot && cohortList.length > 1 && (
        <div className="cohort-bar">
          <div className="cohort-bar-inner" role="tablist" aria-label="Cohorts">
            {cohortList.map((c) => {
              const members = founderList.filter((f) => f.cohortId === c.id);
              const count = members.length;
              const health = cohortHealth(now, c.start_date, members, snapshot, handled);
              return (
                <button
                  key={c.id}
                  type="button"
                  role="tab"
                  aria-selected={c.id === cohortId}
                  className={`cohort-tab ${c.id === cohortId ? "active" : ""}`}
                  onClick={() => pickCohort(c.id)}
                >
                  <span className="cohort-tab-name">{c.name}</span>
                  <span className="cohort-tab-meta">
                    {cohortWeekLabel(now, c.start_date, c.total_weeks)} · {count} startup
                    {count === 1 ? "" : "s"}
                  </span>
                  <span className={`cohort-tab-status ${health.tone}`}>{health.text}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      <main className="dash-main">
        {body}
        <footer className="page-footer">
          <span>Adventure Studio · MVP Program</span>
          <span>From founders&apos; Slack check-ins and connected tools · All times SGT</span>
        </footer>
      </main>
    </div>
  );
}

/** Today's date plus the next fortnightly sprint session (Thursday of each sprint's second week). */
function SprintChip({
  program,
  now,
  meetings,
}: {
  program: ProgramState;
  now: Date;
  meetings: MeetingRow[];
}) {
  const today = sgtDate(now);
  const next = nextSprintSession(program.weeks, today);
  const booked = next ? sprintMeeting(meetings, next.date) : undefined;
  const at = booked ? `, ${sgtTime(booked.starts_at)}` : "";
  return (
    <div className="page-head-side">
      {next && (
        <span className={`sprint-chip ${next.date === today ? "today" : ""}`}>
          <Users size={14} />
          {next.date === today
            ? `Sprint ${next.sprint} session today${at}`
            : `Next sprint session · ${formatDay(next.date)}${at}`}
        </span>
      )}
      <span className="page-date">
        {formatDay(today, { weekday: "short", day: "numeric", month: "long" })}
      </span>
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
  onHandle: (startupId: string, value: boolean, note?: string) => void;
  openStartup: (id: string) => void;
}) {
  // "Mark handled" asks for an optional note for the other mentors before saving.
  const [noting, setNoting] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const handledInfo = new Map(snapshot.handled.map((r) => [r.startup_id, r]));
  const saveHandled = (id: string) => {
    onHandle(id, true, note.trim() || undefined);
    setNoting(null);
    setNote("");
  };
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
        right={<SprintChip program={program} now={now} meetings={snapshot.meetings} />}
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
                <p>
                  {done.length
                    ? `Nothing new. ${done.length} handled by the studio, below.`
                    : "No startup is blocked or quiet right now."}
                </p>
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
                    {noting !== f.id && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="row-action"
                        aria-label={`Mark ${startupName(f)} handled`}
                        onClick={() => {
                          setNoting(f.id);
                          setNote("");
                        }}
                      >
                        <Check size={14} /> <span className="hide-sm">Mark handled</span>
                      </Button>
                    )}
                    {noting === f.id && (
                      <form
                        className="handle-form"
                        onSubmit={(e) => {
                          e.preventDefault();
                          saveHandled(f.id);
                        }}
                      >
                        <input
                          className="handle-note"
                          autoFocus
                          maxLength={300}
                          value={note}
                          onChange={(e) => setNote(e.target.value)}
                          onKeyDown={(e) => e.key === "Escape" && setNoting(null)}
                          placeholder="What was done? (optional, mentors see this)"
                          aria-label={`Note on how ${startupName(f)} was handled`}
                        />
                        <Button type="submit" size="sm">
                          <Check size={14} /> Mark handled
                        </Button>
                        <Button
                          type="button"
                          variant="quiet"
                          size="sm"
                          onClick={() => setNoting(null)}
                        >
                          Cancel
                        </Button>
                      </form>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {done.length > 0 && (
              <details className="handled" open={open.length === 0}>
                <summary>Handled · {done.length}</summary>
                <ul className="rows">
                  {done.map((f) => {
                    const info = handledInfo.get(f.id);
                    return (
                      <li key={f.id} className="row muted">
                        <span className="avatar">{initials(startupName(f))}</span>
                        <span className="min-w-0 flex-1">
                          <span className="row-title">{startupName(f)}</span>
                          <span className="row-reason">{attentionReason(f)}</span>
                          <span className="row-reason">
                            Handled{info?.handled_by ? ` by ${info.handled_by}` : ""}{" "}
                            {relativeTime(handled[f.id] ?? "", now)} · reopens on the next check-in
                          </span>
                          {info?.note && (
                            <span className="row-note">&ldquo;{info.note}&rdquo;</span>
                          )}
                        </span>
                        <Button variant="quiet" size="sm" onClick={() => onHandle(f.id, false)}>
                          <Undo2 size={14} /> Undo
                        </Button>
                      </li>
                    );
                  })}
                </ul>
              </details>
            )}
          </section>
        </div>
        <ComingUp
          founders={founders}
          snapshot={snapshot}
          program={program}
          now={now}
          openStartup={openStartup}
        />
      </div>
    </>
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
  // Essential setup still missing (the optional calendar doesn't count here).
  const gapsOf = (f: Founder) =>
    setupGaps(f.id, snapshot.setup ?? [], snapshot.founders, snapshot.milestones).filter(
      (g) => !g.endsWith("(optional)"),
    );
  const matches: Record<string, (f: Founder) => boolean> = {
    All: () => true,
    "Needs attention": (f) => attentionReason(f) !== null,
    ...(snapshot.setup?.length ? { "Setup incomplete": (f: Founder) => gapsOf(f).length > 0 } : {}),
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
                {gapsOf(f).length > 0 && (
                  <span className="card-setup" title={gapsOf(f).join(" · ")}>
                    <CircleDashed size={13} /> {gapsOf(f)[0]}
                    {gapsOf(f).length > 1 && ` +${gapsOf(f).length - 1} more`}
                  </span>
                )}
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
