import { useState } from "react";
import {
  CalendarDays,
  CheckCheck,
  CircleAlert,
  CircleDot,
  GitCommitHorizontal,
  GitPullRequest,
  Radio,
  TrendingUp,
} from "lucide-react";
import { formatDistanceToNowStrict } from "date-fns";
import {
  entryGroup,
  useTimeline,
  workSummary,
  type TimelineEntry,
  type TimelineGroup,
} from "@/hooks/use-timeline";
import type { Founder } from "./data";
import { useMilestones } from "@/hooks/use-milestones";
import { milestoneProgress } from "./insights";
import { sgtDate } from "./program";
import { deliverableId } from "./insights";
import { cohortProgram } from "./program";
import { useDashData } from "@/hooks/use-dash-data";

const DAY = 24 * 60 * 60 * 1000;

function blockedForDays(entries: TimelineEntry[]): number | null {
  // Entries are newest-first; walk back through consecutive blocked check-ins.
  const checkins = entries.filter((e) => e.kind === "checkin" || e.kind === "blocker");
  if (checkins[0]?.kind !== "blocker") return null;
  let since = Date.parse(checkins[0].at);
  for (const c of checkins) {
    if (c.kind !== "blocker") break;
    since = Date.parse(c.at);
  }
  return Math.max(0, Math.floor((Date.now() - since) / DAY));
}

function progressDelta(entries: TimelineEntry[], index: number): number | null {
  const current = entries[index];
  if (current?.progress === undefined) return null;
  // Progress is per deliverable: a new week's 20% is not a drop from last week's 60%.
  const previous = entries
    .slice(index + 1)
    .find((e) => e.progress !== undefined && e.deliverableId === current.deliverableId);
  return previous?.progress === undefined ? null : current.progress - previous.progress;
}

/** "on current deliverable" only when the check-in is for this program week; otherwise name its week. */
export function progressScope(e: TimelineEntry, now = new Date(), cohortStart?: string | null): string {
  const current = deliverableId(cohortProgram(now, cohortStart).week); // each cohort runs the syllabus from its own start
  if (!e.deliverableId || e.deliverableId === current) return "on current deliverable";
  const week = Number(e.deliverableId.replace(/\D/g, ""));
  return week ? `on week ${week}'s deliverable (last check-in)` : "on an earlier deliverable";
}

function icon(e: TimelineEntry) {
  if (e.kind === "checkin") return <CheckCheck size={12} />;
  if (e.kind === "blocker") return <CircleAlert size={12} />;
  if (e.type === "commit") return <GitCommitHorizontal size={12} />;
  if (e.type === "pull_request") return <GitPullRequest size={12} />;
  if (e.type === "issue") return <CircleDot size={12} />;
  if (e.type === "meeting") return <CalendarDays size={12} />;
  return <Radio size={12} />;
}

const FILTERS: { id: "all" | TimelineGroup; label: string }[] = [
  { id: "all", label: "All" },
  { id: "checkin", label: "Check-ins" },
  { id: "code", label: "Code" },
  { id: "meeting", label: "Meetings" },
];

export function Timeline({ founder, refreshKey }: { founder: Founder; refreshKey: string }) {
  const { entries, loading } = useTimeline(founder.startupId, refreshKey);
  const cohortStart = useDashData().snapshot?.cohorts?.find((c) => c.id === founder.cohortId)?.start_date;
  const milestones = useMilestones(founder.startupId);
  const mp =
    founder.startupId && milestones
      ? milestoneProgress(milestones, founder.startupId, sgtDate(new Date()))
      : null;
  const [filter, setFilter] = useState<"all" | TimelineGroup>("all");

  if (!entries) {
    return (
      <>
        <h3 className="detail-heading">Timeline</h3>
        <p className="muted-note">Loading the timeline…</p>
      </>
    );
  }

  const blocked = blockedForDays(entries);
  const latest = entries.find((e) => e.progress !== undefined);
  const work = workSummary(entries);
  const shown = filter === "all" ? entries : entries.filter((e) => entryGroup(e) === filter);

  return (
    <>
      <h3 className="detail-heading">Timeline</h3>
      {(latest || work.commits || work.prsMerged || work.meetings) && (
        <div className="mb-4 flex flex-wrap items-center gap-2 text-[11px]">
          {mp ? (
            <span
              className="pill pill-neutral"
              title="Average completion of the milestones in play"
            >
              <TrendingUp size={10} /> {mp.pct}% of milestones
            </span>
          ) : (
            latest && (
              <span className="pill pill-neutral">
                <TrendingUp size={10} /> {latest.progress}% {progressScope(latest, new Date(), cohortStart)}
              </span>
            )
          )}
          {blocked !== null && (
            <span className="pill pill-danger">
              <CircleAlert size={10} /> Blocked for{" "}
              {blocked === 0 ? "under a day" : `${blocked} day${blocked === 1 ? "" : "s"}`}
            </span>
          )}
          {(work.commits > 0 || work.prsMerged > 0) && (
            <span className="pill pill-neutral" title="Last 7 days">
              <GitCommitHorizontal size={10} /> {work.commits} commit{work.commits === 1 ? "" : "s"}
              {work.prsMerged > 0 &&
                ` · ${work.prsMerged} PR${work.prsMerged === 1 ? "" : "s"} merged`}
            </span>
          )}
          {work.meetings > 0 && (
            <span className="pill pill-neutral" title="Last 7 days">
              <CalendarDays size={10} /> {work.meetings} meeting{work.meetings === 1 ? "" : "s"}
            </span>
          )}
        </div>
      )}
      <div className="mb-3 flex flex-wrap gap-1.5" role="tablist" aria-label="Timeline filter">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            role="tab"
            aria-selected={filter === f.id}
            onClick={() => setFilter(f.id)}
            className={`rounded-full border px-2.5 py-1 text-[11px] ${
              filter === f.id
                ? "border-primary bg-primary/10 text-foreground"
                : "border-border text-muted-foreground hover:text-foreground"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>
      {loading && !entries.length && (
        <p className="text-[11px] text-muted-foreground">Loading...</p>
      )}
      {!loading && !shown.length && (
        <p className="text-[11px] text-muted-foreground">
          {filter === "all" ? "No confirmed activity yet." : "Nothing in this category yet."}
        </p>
      )}
      <ol className="drawer-history">
        {shown.map((e) => {
          const delta = e.kind === "signal" ? null : progressDelta(entries, entries.indexOf(e));
          return (
            <li key={e.id}>
              <article>
                <p className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                  {icon(e)}
                  {formatDistanceToNowStrict(new Date(e.at), { addSuffix: true })} &middot;{" "}
                  {new Date(e.at).toLocaleDateString("en-SG", { month: "short", day: "numeric", timeZone: "Asia/Singapore" })}
                </p>
                <p className="mt-2 flex flex-wrap items-center gap-2 text-xs font-medium">
                  {e.title}
                  {e.progress !== undefined && (
                    <span
                      className="text-muted-foreground"
                      title="The progress they reported in this check-in"
                    >
                      reported {e.progress}%{delta ? ` (${delta > 0 ? "+" : ""}${delta})` : ""}
                    </span>
                  )}
                </p>
                {e.detail && (
                  <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{e.detail}</p>
                )}
              </article>
            </li>
          );
        })}
      </ol>
    </>
  );
}
