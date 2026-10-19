import { CheckCheck, Circle, Target } from "lucide-react";
import { useMilestones } from "@/hooks/use-milestones";
import { goalValue, isMilestoneComplete, milestoneValue } from "./insights";
import type { SetBy } from "@/hooks/use-dash-data";
import type { Founder } from "./data";

const ROLE = { mentor: "Mentor", founder: "Founder" } as const;

/** "Ben Lim · Mentor", or just the role when the person's record is gone. */
export function setByLabel(by: SetBy | undefined): string | null {
  if (!by) return null;
  return by.name ? `${by.name} · ${ROLE[by.role]}` : ROLE[by.role];
}

export function Milestones({ founder }: { founder: Founder }) {
  const items = useMilestones(founder.startupId);

  return (
    <>
      <h3 className="detail-heading">Milestones &amp; goals</h3>
      {items === null && <p className="muted-note">Loading milestones…</p>}
      {items && !items.length && (
        <p className="muted-note">
          No milestones yet. Founders and mentors add them by messaging the Slack bot, e.g.
          &ldquo;Set a milestone: 10 customer interviews by Oct 23&rdquo;.
        </p>
      )}
      <div className="drawer-history">
        {items?.map((m) => {
          const done = m.goals.filter((g) => g.done).length;
          const overall = milestoneValue(m.goals, m);
          const pct = overall.pct;
          const by = setByLabel(m.set_by);
          return (
            <article key={m.id}>
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Target size={13} />
                {m.due_date
                  ? `Due ${new Date(m.due_date).toLocaleDateString("en-SG", { month: "short", day: "numeric" })}`
                  : "No due date"}
                {isMilestoneComplete(m) && " · Done"}
              </p>
              <p className="mt-1.5 text-[15px] font-medium">{m.title}</p>
              {by && (
                <p className="mt-1 text-xs text-muted-foreground">
                  Set by <span className="font-medium text-foreground">{by}</span>
                </p>
              )}
              <div
                className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-muted"
                role="progressbar"
                aria-valuenow={pct}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`About ${pct}% done`}
              >
                <div
                  className={`h-full ${overall.estimated ? "est-fill" : "bg-primary"}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <p className="mt-1.5 text-xs text-muted-foreground">
                {m.goals.length ? `${done}/${m.goals.length} goals done` : "No goals yet"}
                {pct > 0 && (
                  <>
                    {" · "}
                    {!overall.estimated
                      ? `${pct}%`
                      : m.goals.length
                        ? `~${pct}% incl. GitHub estimates`
                        : `~${pct}% est. from GitHub`}
                  </>
                )}
              </p>
              {!m.goals.length && overall.estimated && m.est_reason && (
                <p className="mt-1 text-xs text-muted-foreground">{m.est_reason}</p>
              )}
              <ul className="mt-2 space-y-1.5">
                {m.goals.map((g) => {
                  // Only call out who added a goal when it differs from whoever set the milestone.
                  const goalBy = setByLabel(g.set_by);
                  const differs = goalBy && goalBy !== by;
                  const v = goalValue(g);
                  return (
                    <li key={g.id} className="flex items-start gap-2 text-sm leading-relaxed">
                      {g.done ? (
                        <CheckCheck size={14} className="mt-1 shrink-0 text-success" />
                      ) : (
                        <Circle size={13} className="mt-1 shrink-0 text-muted-foreground" />
                      )}
                      <span className="min-w-0">
                        <span className={g.done ? "text-muted-foreground line-through" : ""}>
                          {g.title}
                        </span>
                        {!g.done && v.pct > 0 && (
                          <span
                            className={`goal-pct ${v.estimated ? "est" : ""}`}
                            title={
                              v.estimated
                                ? (g.est_reason ?? "Estimated from GitHub work")
                                : undefined
                            }
                          >
                            {v.estimated ? `~${v.pct}% est. from GitHub` : `${v.pct}%`}
                          </span>
                        )}
                        {v.estimated && g.est_reason && (
                          <span className="block text-xs text-muted-foreground">
                            {g.est_reason}
                          </span>
                        )}
                        {differs && (
                          <span className="block text-xs text-muted-foreground">
                            Added by {goalBy}
                          </span>
                        )}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </article>
          );
        })}
      </div>
    </>
  );
}
