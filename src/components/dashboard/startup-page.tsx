import { ArrowLeft, Flag, MessageSquare, NotebookPen } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { DashSnapshot } from "@/hooks/use-dash-data";
import type { Founder } from "./data";
import { formatDay, type ProgramState } from "./program";
import { blockedDays, checkinStreak, gateStatus, weeklyProgress } from "./insights";
import {
  GatePill,
  HealthPill,
  Kpi,
  Progress,
  StreamTag,
  WeekBars,
  gateLabel,
  initials,
  startupName,
} from "./parts";
import { relativeTime } from "./roster";
import { Timeline } from "./timeline";
import { Milestones } from "./milestones";

/** Everything about one startup on one page. Mentors reach it from any list; founders get it as "My venture". */
export function StartupPage({
  founder,
  program,
  now,
  snapshot,
  isMentor,
  onBack,
}: {
  founder: Founder;
  program: ProgramState;
  now: Date;
  snapshot: DashSnapshot;
  isMentor: boolean;
  onBack?: (() => void) | undefined;
}) {
  const w = program.weeks.find((x) => x.week === program.week);
  const gate = w ? gateStatus(founder.id, w, snapshot.submissions, snapshot.signals, now) : null;
  const streak = checkinStreak(founder.id, snapshot.submissions, program, now);
  const blocked = blockedDays(founder.id, snapshot.submissions, now);
  const series = weeklyProgress(founder.id, snapshot.submissions, program.weeks);
  const notes = snapshot.notes.filter((n) => n.startup_id === founder.id);
  const tasks = snapshot.tasks.filter((t) => t.startup_id === founder.id);
  const blocker = founder.blocker && founder.blocker !== "None" ? founder.blocker : null;

  return (
    <div className="startup-page">
      {onBack && (
        <button type="button" className="back-link" onClick={onBack}>
          <ArrowLeft size={16} /> Back
        </button>
      )}
      <div className="page-head">
        <div className="flex min-w-0 items-center gap-4">
          <span className="avatar lg">{initials(startupName(founder))}</span>
          <div className="min-w-0">
            <h1 className="truncate">{startupName(founder)}</h1>
            <p className="truncate">{founder.name}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <HealthPill founder={founder} />
          <StreamTag founder={founder} />
        </div>
      </div>

      <div className="kpi-strip">
        <Kpi
          label={`Week ${program.week} gate · ${gateLabel(program)}`}
          value={gate ? <GatePill state={gate.state} /> : "—"}
          sub={gate?.reason ?? "No gate this week"}
        />
        <Kpi
          label="Deliverable progress"
          value={gate?.progress === null || !gate ? "—" : `${gate.progress}%`}
          sub={gate ? `About ${gate.expected}% expected by now` : "—"}
          tone={
            gate && gate.progress !== null && gate.progress < gate.expected - 25
              ? "warning"
              : undefined
          }
        />
        <Kpi
          label="Check-in streak"
          value={`${streak} wk${streak === 1 ? "" : "s"}`}
          sub={founder.time === "—" ? "No check-ins yet" : `Last ${founder.time}`}
          tone={streak === 0 ? "warning" : undefined}
        />
        <Kpi
          label="Days blocked"
          value={blocked}
          sub={founder.health === "blocked" ? "Blocked right now" : "Across the program"}
          tone={founder.health === "blocked" ? "danger" : undefined}
        />
      </div>

      <div className="split">
        <div className="split-main">
          <section className="panel" aria-labelledby="trend-title">
            <div className="panel-head">
              <h2 id="trend-title">Progress by week</h2>
              <span className="panel-meta">Latest progress on each week&apos;s deliverable</span>
            </div>
            <WeekBars series={series} current={program.week} size="lg" />
          </section>

          <section className="panel" aria-labelledby="latest-title">
            <div className="panel-head">
              <h2 id="latest-title">Latest check-in</h2>
              {founder.time !== "—" && <span className="panel-meta">{founder.time}</span>}
            </div>
            <p className="text-[15px] leading-relaxed">{founder.digest}</p>
            {blocker && (
              <div className="callout danger mt-4">
                <p className="font-medium">Blocker</p>
                <p>{blocker}</p>
              </div>
            )}
            {w && (
              <div className="deliverable-box">
                <p className="eyebrow">Due {w.gateDate ? formatDay(w.gateDate) : "this week"}</p>
                <p className="mt-1 font-medium">{w.deliverable || "No deliverable this week"}</p>
                {gate && (
                  <div className="mt-3 flex items-center gap-3">
                    <Progress value={gate.progress ?? 0} expected={gate.expected} />
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {gate.progress ?? 0}%
                    </span>
                  </div>
                )}
              </div>
            )}
            {!isMentor && (
              <p className="mt-4 flex items-center gap-2 text-sm text-muted-foreground">
                <MessageSquare size={15} /> Message the bot in Slack to add a check-in.
              </p>
            )}
          </section>

          <section className="panel" aria-label="Check-in history">
            <Timeline
              founder={founder}
              refreshKey={`${founder.digest}|${founder.progress}|${founder.status}`}
            />
          </section>
        </div>

        <aside className="split-side">
          <section className="panel">
            <Milestones founder={founder} />
          </section>

          <section className="panel" aria-labelledby="tasks-title">
            <div className="panel-head">
              <h2 id="tasks-title">Open tasks</h2>
              {tasks.length > 0 && <span className="pill pill-neutral">{tasks.length}</span>}
            </div>
            {tasks.length === 0 ? (
              <p className="muted-note">No open tasks. Tasks set through the bot appear here.</p>
            ) : (
              <ul className="list">
                {tasks.map((t) => (
                  <li key={t.id}>
                    <Flag size={14} className="mt-0.5 shrink-0 text-muted-foreground" />
                    <span className="min-w-0">
                      <span className="block">{t.title}</span>
                      {t.due_date && <span className="list-meta">Due {formatDay(t.due_date)}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {isMentor && (
            <section className="panel" aria-labelledby="notes-title">
              <div className="panel-head">
                <h2 id="notes-title">Mentor notes</h2>
                <span className="panel-meta">Studio team only</span>
              </div>
              {notes.length === 0 ? (
                <p className="muted-note">
                  No notes yet. Tell the bot something like &ldquo;note for {startupName(founder)}:
                  …&rdquo;.
                </p>
              ) : (
                <ul className="list">
                  {notes.map((n) => (
                    <li key={n.id}>
                      <NotebookPen size={14} className="mt-0.5 shrink-0 text-muted-foreground" />
                      <span className="min-w-0">
                        <span className="block whitespace-pre-line">{n.body}</span>
                        <span className="list-meta">
                          {n.author_name ?? "Mentor"} · {relativeTime(n.created_at, now)}
                        </span>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}

          {(founder.profile || founder.audience) && (
            <section className="panel" aria-labelledby="profile-title">
              <div className="panel-head">
                <h2 id="profile-title">Profile</h2>
              </div>
              {founder.profile && (
                <p className="text-sm leading-relaxed text-muted-foreground">{founder.profile}</p>
              )}
              {founder.audience && (
                <p className="mt-3 text-sm">
                  <span className="text-muted-foreground">Target audience · </span>
                  {founder.audience}
                </p>
              )}
            </section>
          )}
        </aside>
      </div>
      {onBack && (
        <Button variant="quiet" size="sm" className="mt-6" onClick={onBack}>
          <ArrowLeft size={14} /> Back to the cohort
        </Button>
      )}
    </div>
  );
}
