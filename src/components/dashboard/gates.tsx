import { useState } from "react";
import { ChevronLeft, ChevronRight, GitPullRequest, MessageSquare, Video } from "lucide-react";
import type { Milestone, SignalRow, SubmissionRow } from "@/hooks/use-dash-data";
import type { Founder } from "./data";
import { formatDay, type ProgramState } from "./program";
import { GATE_LABEL, gateStatus, type GateState } from "./insights";
import { GatePill, Progress, initials, startupName } from "./parts";
import { relativeTime } from "./roster";

type Common = {
  founders: Founder[];
  program: ProgramState;
  subs: SubmissionRow[];
  signals: SignalRow[];
  milestones: Milestone[];
  now: Date;
  openStartup: (id: string) => void;
};

const ORDER: GateState[] = ["blocked", "behind", "no_update", "on_track", "submitted", "upcoming"];

/** Where every startup stands on one gate's deliverable, with the evidence behind it. */
export function GateBoard({
  founders,
  program,
  subs,
  signals,
  milestones,
  now,
  openStartup,
}: Common) {
  // Today only looks forward: finished gates live in the Program tab's grid.
  const [picked, setWeek] = useState(program.week);
  const week = Math.max(picked, program.week);
  const w = program.weeks.find((x) => x.week === week) ?? program.weeks[0];
  if (!w) return null;
  const rows = founders
    .map((f) => ({ f, g: gateStatus(f.id, w, subs, signals, now, milestones) }))
    .sort(
      (a, b) =>
        ORDER.indexOf(a.g.state) - ORDER.indexOf(b.g.state) ||
        startupName(a.f).localeCompare(startupName(b.f)),
    );
  const counts = ORDER.map((s) => [s, rows.filter((r) => r.g.state === s).length] as const).filter(
    ([, n]) => n > 0,
  );
  const isCurrent = week === program.week;

  return (
    <section className="panel gate-board" aria-labelledby="gate-title">
      <div className="gate-head">
        <div className="min-w-0">
          <p className="eyebrow">
            {isCurrent ? "This week's gate" : `Week ${w.week} gate`} ·{" "}
            {w.gateDate ? formatDay(w.gateDate) : "—"}
          </p>
          <h2 id="gate-title" className="gate-title">
            {w.deliverable || "No deliverable this week"}
          </h2>
          <div className="gate-summary">
            {counts.map(([s, n]) => (
              <span key={s}>
                <strong>{n}</strong> {GATE_LABEL[s].toLowerCase()}
              </span>
            ))}
          </div>
        </div>
        <div className="stepper" role="group" aria-label="Choose gate week">
          <button
            type="button"
            aria-label="Previous week"
            disabled={week <= program.week}
            onClick={() => setWeek(week - 1)}
          >
            <ChevronLeft size={16} />
          </button>
          <span>Week {week}</span>
          <button
            type="button"
            aria-label="Next week"
            disabled={week >= program.totalWeeks}
            onClick={() => setWeek(week + 1)}
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </div>

      {rows.length === 0 ? (
        <p className="empty">No startups yet.</p>
      ) : (
        <div className="gate-table" role="table" aria-label="Gate readiness by startup">
          <div className="gate-row gate-row-head" role="row">
            <span role="columnheader">Startup</span>
            <span role="columnheader">Status</span>
            <span role="columnheader">Progress</span>
            <span role="columnheader">Evidence this week</span>
            <span role="columnheader">Last update</span>
          </div>
          {rows.map(({ f, g }) => (
            <button
              key={f.id}
              type="button"
              role="row"
              className="gate-row"
              onClick={() => openStartup(f.id)}
            >
              <span role="cell" className="gate-startup">
                <span className="avatar">{initials(startupName(f))}</span>
                <span className="min-w-0">
                  <span className="row-title">{startupName(f)}</span>
                  <span className="row-reason">{g.reason}</span>
                </span>
              </span>
              <span role="cell">
                <GatePill state={g.state} />
              </span>
              <span role="cell" className="gate-progress">
                <Progress
                  value={g.progress ?? 0}
                  {...(isCurrent ? { expected: g.expected } : {})}
                />
                <span>{g.progress === null ? "—" : `${g.progress}%`}</span>
              </span>
              <span role="cell" className="gate-evidence">
                <span title="Check-ins this week">
                  <MessageSquare size={14} /> {g.checkins}
                </span>
                <span title="Commits, PRs and issues on monitored repos">
                  <GitPullRequest size={14} /> {g.work}
                </span>
                <span title="Meetings">
                  <Video size={14} /> {g.meetings}
                </span>
              </span>
              <span role="cell" className="gate-when">
                {g.lastUpdate ? relativeTime(g.lastUpdate, now) : "Never"}
              </span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

/** Every startup against all 12 gates at a glance. */
export function GateMatrix({
  founders,
  program,
  subs,
  signals,
  milestones,
  now,
  openStartup,
}: Common) {
  return (
    <section className="panel" aria-labelledby="matrix-title">
      <div className="panel-head">
        <h2 id="matrix-title">Gates by startup</h2>
      </div>
      <div className="matrix-scroll">
        <table className="gate-matrix">
          <thead>
            <tr>
              <th scope="col">Startup</th>
              {program.weeks.map((w) => (
                <th
                  key={w.week}
                  scope="col"
                  className={w.week === program.week ? "now" : ""}
                  title={w.deliverable}
                >
                  {w.week}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {founders.map((f) => (
              <tr key={f.id}>
                <th scope="row">
                  <button type="button" className="link-btn" onClick={() => openStartup(f.id)}>
                    {startupName(f)}
                  </button>
                </th>
                {program.weeks.map((w) => {
                  const g = gateStatus(f.id, w, subs, signals, now, milestones);
                  return (
                    <td key={w.week} className={w.week === program.week ? "now" : ""}>
                      <span
                        className={`cell cell-${g.state}`}
                        title={`Week ${w.week} · ${GATE_LABEL[g.state]}${g.progress === null ? "" : ` · ${g.progress}%`}`}
                      >
                        <span className="sr-only">{GATE_LABEL[g.state]}</span>
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="matrix-legend">
        {(["submitted", "on_track", "behind", "blocked", "no_update"] as const).map((s) => (
          <span key={s}>
            <span className={`cell cell-${s}`} /> {GATE_LABEL[s]}
          </span>
        ))}
      </div>
    </section>
  );
}
