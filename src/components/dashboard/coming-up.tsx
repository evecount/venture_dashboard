import { useState, type ReactNode } from "react";
import { CalendarClock, Target, Users, Video } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { DashSnapshot, MeetingRow } from "@/hooks/use-dash-data";
import type { Founder } from "./data";
import {
  formatDay,
  nextSprintSession,
  sgtClock,
  sgtDate,
  sgtTime,
  type ProgramState,
} from "./program";
import { upcomingMilestones } from "./insights";
import { setByLabel } from "./milestones";
import { startupName } from "./parts";

type Item = {
  key: string;
  sort: string;
  kind: "meeting" | "sprint" | "milestone";
  when: string;
  title: string;
  meta: ReactNode;
  state: "" | "now" | "overdue";
  onClick?: (() => void) | undefined;
  href?: string | null | undefined;
};

const ICON = {
  meeting: <Video size={15} />,
  sprint: <Users size={15} />,
  milestone: <Target size={15} />,
};

const dot = <span className="dot-sep">·</span>;

/**
 * What's next across the cohort, in date order: studio-calendar meetings (next 2 weeks), the next fortnightly
 * sprint session, and open milestones (undated last).
 */
export function ComingUp({
  founders,
  snapshot,
  program,
  now,
  openStartup,
}: {
  founders: Founder[];
  snapshot: DashSnapshot;
  program: ProgramState;
  now: Date;
  openStartup: (id: string) => void;
}) {
  const [showAll, setShowAll] = useState(false);
  const today = sgtDate(now);
  const horizon = sgtDate(new Date(now.getTime() + 14 * 86_400_000));
  const names = new Map(founders.map((f) => [f.id, startupName(f)]));
  const items: Item[] = [];

  for (const m of snapshot.meetings) {
    const day = sgtDate(new Date(m.starts_at));
    if (day < today || day > horizon || (m.ends_at && Date.parse(m.ends_at) < now.getTime()))
      continue;
    items.push(meetingItem(m, day, today, names));
  }

  const sprint = nextSprintSession(program.weeks, today);
  if (sprint) {
    items.push({
      key: `sprint-${sprint.date}`,
      sort: `${sprint.date} 00:00`,
      kind: "sprint",
      when: sprint.date === today ? "Today" : formatDay(sprint.date),
      title: `Sprint ${sprint.sprint} session`,
      meta: "Fortnightly, every other Thursday",
      state: sprint.date === today ? "now" : "",
    });
  }

  for (const m of upcomingMilestones(snapshot.milestones, today)) {
    if (!names.has(m.startup_id)) continue;
    const done = m.goals.filter((g) => g.done).length;
    const by = setByLabel(m.set_by);
    items.push({
      key: m.id,
      sort: m.due_date ? `${m.due_date} 23:59` : "9999",
      kind: "milestone",
      when: !m.due_date
        ? "No due date"
        : m.overdue
          ? `Overdue · was due ${formatDay(m.due_date)}`
          : m.dueToday
            ? "Due today"
            : `Due ${formatDay(m.due_date)}`,
      title: m.title,
      meta: (
        <>
          {names.get(m.startup_id)}
          {m.goals.length > 0 && (
            <>
              {dot}
              {done}/{m.goals.length} goals
            </>
          )}
          {by && (
            <>
              {dot}Set by {by}
            </>
          )}
        </>
      ),
      state: m.overdue ? "overdue" : m.dueToday ? "now" : "",
      onClick: () => openStartup(m.startup_id),
    });
  }

  items.sort((a, b) => a.sort.localeCompare(b.sort));
  const LIMIT = 7;
  const shown = showAll ? items : items.slice(0, LIMIT);

  return (
    <section className="panel" aria-labelledby="coming-up">
      <div className="panel-head">
        <h2 id="coming-up">Coming up</h2>
        <span className="panel-meta">Meetings, sprint sessions and milestones</span>
      </div>
      {items.length === 0 ? (
        <p className="muted-note">Nothing scheduled yet.</p>
      ) : (
        <ol className="agenda">
          {shown.map((it) => {
            const body = (
              <>
                <p className="agenda-when">
                  <span className="agenda-kind" aria-hidden="true">
                    {ICON[it.kind]}
                  </span>
                  {it.when}
                </p>
                <p className="agenda-what">{it.title}</p>
                <p className="agenda-who">{it.meta}</p>
              </>
            );
            return (
              <li key={it.key} className={`${it.state} agenda-${it.kind}`}>
                {it.onClick ? (
                  <button type="button" className="agenda-btn" onClick={it.onClick}>
                    {body}
                  </button>
                ) : (
                  <div>{body}</div>
                )}
                {it.href && (
                  <a className="agenda-join" href={it.href} target="_blank" rel="noreferrer">
                    <Video size={13} /> Join
                  </a>
                )}
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
      {snapshot.meetings.length === 0 && (
        <p className="muted-note mt-3 flex items-center gap-1.5">
          <CalendarClock size={13} /> Meetings booked through the bot appear here.
        </p>
      )}
    </section>
  );
}

function meetingItem(m: MeetingRow, day: string, today: string, names: Map<string, string>): Item {
  const span = sgtTime(m.starts_at) + (m.ends_at ? `–${sgtTime(m.ends_at)}` : "");
  const who = m.startup_ids.map((id) => names.get(id)).filter(Boolean);
  return {
    key: `meet-${m.id}`,
    sort: `${day} ${sgtClock(m.starts_at)}`,
    kind: "meeting",
    when: `${day === today ? "Today" : formatDay(day)}, ${span}`,
    title: m.title,
    meta: (
      <>
        {m.meet_url ? "Google Meet" : m.location || "Meeting"}
        {who.length > 0 && (
          <>
            {dot}
            {who.join(", ")}
          </>
        )}
      </>
    ),
    state: day === today ? "now" : "",
    href: m.meet_url,
  };
}
