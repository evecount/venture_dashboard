import { useState, type ReactNode } from "react";
import {
  BarChart3,
  Check,
  Clock,
  Flag,
  Hammer,
  Lightbulb,
  Palmtree,
  Store,
  Users,
  Video,
} from "lucide-react";
import type { DashSnapshot, MeetingRow, MentorBusyRow } from "@/hooks/use-dash-data";
import type { Founder } from "./data";
import {
  describeSession,
  formatDay,
  sgtClock,
  sgtDate,
  sgtTime,
  splitPhase,
  sprintSessions,
  type ProgramState,
  type ProgramWeek,
  type SessionKind,
} from "./program";
import { GateMatrix } from "./gates";
import { PageHead, gateLabel } from "./parts";

const ICON: Record<SessionKind, ReactNode> = {
  mentor: <Users size={16} />,
  specialist: <Lightbulb size={16} />,
  industry: <Store size={16} />,
  office: <Clock size={16} />,
  prep: <BarChart3 size={16} />,
  gate: <Flag size={16} />,
  holiday: <Palmtree size={16} />,
  other: <Clock size={16} />,
};

/** The 12-week program: where the cohort is, the sprint roadmap, the selected week day by day, and gates by startup. */
export function ProgramView({
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
  const selected = program.weeks.find((w) => w.week === week) ?? program.weeks[0];
  const current = splitPhase(program.phase);
  const sessions = sprintSessions(program.weeks);
  const sessionWeeks = new Set(sessions.map((x) => x.week));

  // Six sprints of two weeks each.
  const sprints = new Map<number, ProgramWeek[]>();
  for (const w of program.weeks) {
    const n = splitPhase(w.phase).sprint ?? Math.ceil(w.week / 2);
    sprints.set(n, [...(sprints.get(n) ?? []), w]);
  }

  return (
    <>
      <PageHead
        title="Program"
        sub={
          <>
            Week {program.week} of {program.totalWeeks}
            <span className="dot-sep">·</span>
            Sprint {current.sprint ?? "—"}: {current.theme}
          </>
        }
      />

      <section className="panel roadmap-panel" aria-labelledby="roadmap-title">
        <div className="panel-head">
          <h2 id="roadmap-title">Roadmap</h2>
          <span className="panel-meta">6 sprints · 2 weeks each · pick a week to see its days</span>
        </div>
        <ol className="roadmap">
          {[...sprints.entries()].map(([n, weeks]) => {
            const done = weeks.every((w) => w.week < program.week);
            const active = weeks.some((w) => w.week === program.week);
            return (
              <li key={n} className={`sprint ${done ? "done" : ""} ${active ? "active" : ""}`}>
                <p className="sprint-label">
                  {done ? <Check size={13} /> : null}
                  Sprint {n}
                </p>
                {weeks.map((w) => {
                  const p = splitPhase(w.phase);
                  const state =
                    w.week < program.week ? "past" : w.week === program.week ? "now" : "next";
                  return (
                    <button
                      key={w.week}
                      type="button"
                      className={`rm-week ${state} ${w.week === week ? "selected" : ""}`}
                      aria-pressed={w.week === week}
                      onClick={() => setWeek(w.week)}
                    >
                      <span className="rm-week-top">
                        Week {w.week}
                        {state === "now" && <span className="pill pill-orange">This week</span>}
                        {p.review && state !== "now" && <span className="rm-review">Review</span>}
                        {sessionWeeks.has(w.week) && (
                          <span
                            className="rm-sprint"
                            title="Fortnightly sprint session on Thursday"
                          >
                            <Users size={12} /> Sprint session
                          </span>
                        )}
                      </span>
                      <span className="rm-theme">{p.theme}</span>
                    </button>
                  );
                })}
              </li>
            );
          })}
        </ol>
      </section>

      {selected && (
        <WeekDetail
          w={selected}
          program={program}
          today={today}
          sessionDates={new Set(sessions.map((x) => x.date))}
          meetings={snapshot.meetings}
          mentorBusy={snapshot.mentorBusy ?? []}
        />
      )}

      {founders.length > 0 && (
        <div className="mt-4">
          <GateMatrix
            founders={founders}
            program={program}
            subs={snapshot.submissions}
            signals={snapshot.signals}
            now={now}
            openStartup={openStartup}
          />
        </div>
      )}
    </>
  );
}

function WeekDetail({
  w,
  program,
  today,
  sessionDates,
  meetings,
  mentorBusy,
}: {
  w: ProgramWeek;
  program: ProgramState;
  today: string;
  sessionDates: Set<string>;
  meetings: MeetingRow[];
  mentorBusy: MentorBusyRow[];
}) {
  const p = splitPhase(w.phase);
  const isNow = w.week === program.week;
  const gatePassed = !!w.gateDate && w.gateDate < today;
  return (
    <section className="panel week-detail" aria-labelledby="week-title">
      <div className="week-detail-head">
        <div className="min-w-0">
          <p className="eyebrow">
            Sprint {p.sprint ?? "—"} · Week {w.week}
            {isNow ? " · this week" : ""}
          </p>
          <h2 id="week-title" className="week-title">
            {p.theme}
          </h2>
        </div>
        {w.deliverable && (
          <div className={`gate-callout ${gatePassed ? "passed" : ""}`}>
            <p className="eyebrow">
              <Flag size={13} /> {gatePassed ? "Gate passed" : "Due at the gate"} ·{" "}
              {w.gateDate ? formatDay(w.gateDate) : "—"}
              {isNow && !gatePassed && (
                <span className="gate-countdown">{gateLabel(program)} left</span>
              )}
            </p>
            <p className="gate-deliverable">{w.deliverable}</p>
          </div>
        )}
      </div>

      <ol className="day-grid">
        {w.events.map((e) => {
          const s = describeSession(e);
          const state = e.date === today ? "today" : e.date < today ? "past" : "";
          const sprintDay = sessionDates.has(e.date);
          // All-day events cover every day from their start up to (not including) their end date.
          const busy = mentorBusy
            .filter((b) => {
              const start = sgtDate(new Date(b.starts_at));
              if (!b.all_day) return start === e.date;
              const end = b.ends_at ? sgtDate(new Date(b.ends_at)) : start;
              return start <= e.date && (e.date < end || start === end);
            })
            .sort(
              (a, b) =>
                Number(b.all_day) - Number(a.all_day) || a.starts_at.localeCompare(b.starts_at),
            );
          const dayMeetings = meetings
            .filter((m) => sgtDate(new Date(m.starts_at)) === e.date)
            .sort((a, b) => sgtClock(a.starts_at).localeCompare(sgtClock(b.starts_at)));
          return (
            <li key={e.date} className={`day-card ${state} kind-${s.kind}`}>
              <p className="day-when">
                {state === "today" ? "Today" : formatDay(e.date, { weekday: "long" })}
                <span>{formatDay(e.date, { day: "numeric", month: "short" })}</span>
              </p>
              {sprintDay && (
                <p className="day-sprint">
                  <Users size={13} /> Fortnightly sprint session
                </p>
              )}
              <p className="day-session">
                <span className="day-icon" aria-hidden="true">
                  {ICON[s.kind]}
                </span>
                <span className="min-w-0">
                  <span className="day-title">{s.title}</span>
                  {s.length && <span className="day-length">{s.length}</span>}
                </span>
              </p>
              {s.about && <p className="day-about">{s.about}</p>}
              {s.build && (
                <p className="day-build">
                  <Hammer size={13} /> {s.build}
                </p>
              )}
              {busy.length > 0 && (
                <details className="day-busy">
                  <summary>
                    <Users size={12} /> Mentors&apos; calendars · {busy.length}
                  </summary>
                  <ul>
                    {busy.map((b) => (
                      <li key={b.id} className={b.busy_only ? "private" : ""}>
                        <span className="day-meeting-time">
                          {b.all_day ? "All day" : sgtTime(b.starts_at)}
                        </span>
                        <span className="min-w-0">
                          <span className="day-busy-who">{b.mentor.split(" ")[0]}</span> {b.title}
                        </span>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              {dayMeetings.length > 0 && (
                <ul className="day-meetings" aria-label="Meetings on the studio calendar">
                  {dayMeetings.map((m) => (
                    <li key={m.id}>
                      <span className="day-meeting-time">{sgtTime(m.starts_at)}</span>
                      <span className="min-w-0">
                        <span className="day-meeting-title">{m.title}</span>
                        {m.meet_url && (
                          <a
                            href={m.meet_url}
                            target="_blank"
                            rel="noreferrer"
                            className="day-meeting-join"
                          >
                            <Video size={12} /> Join
                          </a>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
