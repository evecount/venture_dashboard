// Small presentational pieces shared by the dashboard views.
import type { ReactNode } from "react";
import { CircleAlert } from "lucide-react";
import type { Founder } from "./data";
import type { ProgramState } from "./program";
import { GATE_LABEL, type GateState } from "./insights";

export function initials(name: string): string {
  const parts = name.split(/[\s,]+/).filter(Boolean);
  if (parts.length === 1) return (parts[0] ?? "?").slice(0, 2).toUpperCase();
  return ((parts[0]?.[0] ?? "?") + (parts[1]?.[0] ?? "")).toUpperCase();
}

/** "Cybrdeck · tagline" -> "Cybrdeck" */
export const startupName = (f: Founder) => f.startup.split(" · ")[0] ?? f.startup;

export function HealthPill({ founder }: { founder: Founder }) {
  if (founder.health === "blocked") {
    return (
      <span className="pill pill-danger">
        <CircleAlert size={11} /> Blocked
      </span>
    );
  }
  if (founder.health === "quiet") {
    return (
      <span className="pill pill-warning" title={founder.healthDetail}>
        Quiet
      </span>
    );
  }
  return <span className="pill pill-success">On track</span>;
}

const GATE_TONE: Record<GateState, string> = {
  submitted: "pill-success",
  on_track: "pill-info",
  behind: "pill-warning",
  blocked: "pill-danger",
  no_update: "pill-neutral",
  upcoming: "pill-neutral",
};

export function GatePill({ state, title }: { state: GateState; title?: string }) {
  return (
    <span className={`pill ${GATE_TONE[state]}`} title={title}>
      {GATE_LABEL[state]}
    </span>
  );
}

export function StreamTag({ founder }: { founder: Founder }) {
  const unassigned = !founder.stream || founder.stream === "Unassigned";
  return (
    <span
      className="pill pill-neutral"
      title={unassigned ? "No stream yet" : `Stream: ${founder.stream}`}
    >
      {unassigned ? "No stream" : founder.stream}
    </span>
  );
}

/** A progress bar, optionally with a tick where progress should be by now. */
export function Progress({ value, expected }: { value: number; expected?: number }) {
  return (
    <div
      className="progress"
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div style={{ width: `${value > 0 ? Math.max(2, Math.min(100, value)) : 0}%` }} />
      {expected !== undefined && expected > 0 && expected < 100 && (
        <span
          className="progress-expected"
          style={{ left: `${expected}%` }}
          title={`About ${expected}% expected by now`}
        />
      )}
    </div>
  );
}

export function Kpi({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: ReactNode;
  sub: ReactNode;
  tone?: "warning" | "danger" | "success" | undefined;
}) {
  return (
    <div className="kpi">
      <p className="kpi-label">{label}</p>
      <p className="kpi-value">{value}</p>
      <p className={`kpi-sub ${tone ? `text-${tone}` : ""}`}>{sub}</p>
    </div>
  );
}

export function PageHead({
  title,
  sub,
  right,
}: {
  title: ReactNode;
  sub: ReactNode;
  right?: ReactNode;
}) {
  return (
    <div className="page-head">
      <div className="min-w-0">
        <h1>{title}</h1>
        <p>{sub}</p>
      </div>
      {right}
    </div>
  );
}

export function gateLabel(p: ProgramState): string {
  if (p.daysToGate === null) return "—";
  if (p.daysToGate <= 0) return "Today";
  return `${p.daysToGate} day${p.daysToGate === 1 ? "" : "s"}`;
}

export function greeting(now: Date): string {
  const hour = Number(
    new Intl.DateTimeFormat("en-SG", {
      hour: "numeric",
      hourCycle: "h23",
      timeZone: "Asia/Singapore",
    }).format(now),
  );
  return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}

/**
 * Progress per program week as small bars: past weeks solid, this week outlined, future weeks empty.
 * `size="lg"` adds week numbers and percentages for the startup page.
 */
export function WeekBars({
  series,
  current,
  size = "sm",
}: {
  series: Array<{ week: number; progress: number | null }>;
  current: number;
  size?: "sm" | "lg";
}) {
  const lg = size === "lg";
  const h = lg ? 120 : 28;
  const label = series
    .filter((p) => p.week <= current)
    .map((p) => `week ${p.week}: ${p.progress === null ? "no update" : `${p.progress}%`}`)
    .join(", ");
  return (
    <div
      className={`week-bars ${lg ? "lg" : ""}`}
      role="img"
      aria-label={`Progress by week. ${label}`}
    >
      {series.map((p) => {
        const state = p.week < current ? "past" : p.week === current ? "now" : "future";
        const pct = p.progress ?? 0;
        return (
          <div
            key={p.week}
            className={`wb ${state}`}
            title={`Week ${p.week}: ${p.progress === null ? "no update" : `${pct}%`}`}
          >
            {lg && (
              <span className="wb-val">
                {p.progress === null || state === "future" ? "" : `${pct}%`}
              </span>
            )}
            <div className="wb-track" style={{ height: h }}>
              {state !== "future" && (
                <div
                  className="wb-fill"
                  style={{ height: `${Math.max(p.progress === null ? 0 : 4, pct)}%` }}
                />
              )}
            </div>
            {lg && <span className="wb-week">{p.week}</span>}
          </div>
        );
      })}
    </div>
  );
}
