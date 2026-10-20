import { ArrowLeft, CircleDashed, Flag, MessageSquare, NotebookPen, Video } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { DashSnapshot } from "@/hooks/use-dash-data";
import type { Founder } from "./data";
import { formatDay, sgtDate, sgtTime, type ProgramState } from "./program";
import { blockedDays, checkinStreak, gateStatus, setupGaps, weeklySeries } from "./insights";
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
  const gate = w
    ? gateStatus(founder.id, w, snapshot.submissions, snapshot.signals, now, snapshot.milestones)
    : null;
  const ms = gate?.milestone ?? null;
  const streak = checkinStreak(founder.id, snapshot.submissions, program, now);
  const blocked = blockedDays(founder.id, snapshot.submissions, now);
  const { series, mode } = weeklySeries(
    founder.id,
    snapshot.submissions,
    snapshot.milestones,
    program.weeks,
  );
  const notes = snapshot.notes.filter((n) => n.startup_id === founder.id);
  const tasks = snapshot.tasks.filter((t) => t.startup_id === founder.id);
  const meetings = snapshot.meetings.filter(
    (m) =>
      m.startup_ids.includes(founder.id) &&
      (m.ends_at ? Date.parse(m.ends_at) : Date.parse(m.starts_at)) >= now.getTime(),
  );
  const blocker = founder.blocker && founder.blocker !== "None" ? founder.blocker : null;
  const gaps = isMentor
    ? setupGaps(founder.id, snapshot.setup ?? [], snapshot.founders, snapshot.milestones)
    : [];

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
          label={ms ? "Milestone progress" : "Deliverable progress"}
          value={gate?.progress === null || !gate ? "—" : `${gate.progress}%`}
          sub={
            gate
              ? ms
                ? `About ${gate.expected}% expected by now · ${ms.complete}/${ms.counted} done${ms.overdue ? ` · ${ms.overdue} overdue` : ""}`
                : `About ${gate.expected}% expected by now`
              : "—"
          }
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
              <span className="panel-meta">
                {mode === "milestones"
                  ? "How complete the milestones due each week are"
                  : "Latest progress on each week's deliverable"}
              </span>
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
            {ms?.focus ? (
              <div className="deliverable-box">
                <p className="eyebrow">
                  {ms.focus.overdue ? "Overdue milestone" : "Milestone to work on"}
                  {ms.focus.due ? ` · due ${formatDay(ms.focus.due)}` : ""}
                </p>
                <p className="mt-1 font-medium">{ms.focus.title}</p>
                <div className="mt-3 flex items-center gap-3">
                  <Progress value={ms.focus.pct} expected={ms.focus.expected} />
                  <span className="shrink-0 text-xs text-muted-foreground">{ms.focus.pct}%</span>
                </div>
              </div>
            ) : (
              w &&
              !ms && (
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
              )
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
          {gaps.length > 0 && (
            <section className="panel" aria-labelledby="setup-title">
              <div className="panel-head">
                <h2 id="setup-title">Still to set up</h2>
                <span className="panel-meta">Nudge them in Slack</span>
              </div>
              <ul className="list">
                {gaps.map((g) => (
                  <li key={g}>
                    <CircleDashed size={14} className="mt-0.5 shrink-0 text-muted-foreground" />
                    <span className="min-w-0">{g}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
          <section className="panel">
            <Milestones founder={founder} />
          </section>

          <section className="panel" aria-labelledby="meetings-title">
            <div className="panel-head">
              <h2 id="meetings-title">Upcoming meetings</h2>
              {meetings.length > 0 && <span className="pill pill-neutral">{meetings.length}</span>}
            </div>
            {meetings.length === 0 ? (
              <p className="muted-note">
                None booked. Meetings set up through the bot appear here.
              </p>
            ) : (
              <ul className="list">
                {meetings.map((m) => {
                  const day = sgtDate(new Date(m.starts_at));
                  return (
                    <li key={m.id}>
                      <Video size={14} className="mt-0.5 shrink-0 text-muted-foreground" />
                      <span className="min-w-0 flex-1">
                        <span className="block">{m.title}</span>
                        <span className="list-meta">
                          {day === sgtDate(now) ? "Today" : formatDay(day)}, {sgtTime(m.starts_at)}
                          {m.ends_at ? `–${sgtTime(m.ends_at)}` : ""}
                          {m.people.length > 0 ? ` · with ${m.people.slice(0, 4).join(", ")}` : ""}
                        </span>
                      </span>
                      {m.meet_url && (
                        <a
                          className="agenda-join"
                          href={m.meet_url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Join
                        </a>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
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
