import { CircleAlert, CheckCheck, Radio, TrendingUp } from "lucide-react";
import { formatDistanceToNowStrict } from "date-fns";
import { useTimeline, type TimelineEntry } from "@/hooks/use-timeline";
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

const icons = {
  checkin: <CheckCheck size={12} />,
  blocker: <CircleAlert size={12} />,
  signal: <Radio size={12} />,
};

export function Timeline({ founder, refreshKey }: { founder: Founder; refreshKey: string }) {
  const { entries, loading } = useTimeline(founder.startupId, refreshKey);

  if (!entries) {
    return (
      <>
        <h3 className="detail-heading">Timeline</h3>
        <div className="rounded-md border border-border p-3 text-[11px] text-muted-foreground">
          The full history appears when the dashboard is connected to the live ledger. In simulation
          mode only the latest update is available: &ldquo;{founder.digest}&rdquo;
        </div>
      </>
    );
  }

  const blocked = blockedForDays(entries);
  const latest = entries.find((e) => e.progress !== undefined);

  return (
    <>
      <h3 className="detail-heading">Timeline</h3>
      {latest && (
        <div className="mb-4 flex flex-wrap items-center gap-2 text-[11px]">
          <span className="pill pill-neutral">
            <TrendingUp size={10} /> {latest.progress}% on current deliverable
          </span>
          {blocked !== null && (
            <span className="pill pill-danger">
              <CircleAlert size={10} /> Blocked for{" "}
              {blocked === 0 ? "under a day" : `${blocked} day${blocked === 1 ? "" : "s"}`}
            </span>
          )}
        </div>
      )}
      {loading && !entries.length && <p className="text-[11px] text-muted-foreground">Loading...</p>}
      {!loading && !entries.length && (
        <p className="text-[11px] text-muted-foreground">No confirmed activity yet.</p>
      )}
      <ol className="drawer-history">
        {entries.map((e, i) => {
          const delta = e.kind === "signal" ? null : progressDelta(entries, i);
          return (
            <li key={e.id}>
              <article>
                <p className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                  {icons[e.kind]}
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
