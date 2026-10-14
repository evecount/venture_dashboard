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
  const previous = entries.slice(index + 1).find((e) => e.progress !== undefined);
  return previous?.progress === undefined ? null : current.progress - previous.progress;
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
          {latest && (
            <span className="pill pill-neutral">
              <TrendingUp size={10} /> {latest.progress}% on current deliverable
            </span>
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
              {work.prsMerged > 0 && ` · ${work.prsMerged} PR${work.prsMerged === 1 ? "" : "s"} merged`}
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
      {loading && !entries.length && <p className="text-[11px] text-muted-foreground">Loading...</p>}
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
                  {new Date(e.at).toLocaleDateString("en-SG", { month: "short", day: "numeric" })}
                </p>
                <p className="mt-2 flex flex-wrap items-center gap-2 text-xs font-medium">
                  {e.title}
                  {e.progress !== undefined && (
                    <span className="text-muted-foreground">
                      {e.progress}%{delta ? ` (${delta > 0 ? "+" : ""}${delta})` : ""}
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
