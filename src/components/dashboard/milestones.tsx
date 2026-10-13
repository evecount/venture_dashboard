import { CheckCheck, Circle, Target } from "lucide-react";
import { useMilestones } from "@/hooks/use-milestones";
import type { Founder } from "./data";

export function Milestones({ founder }: { founder: Founder }) {
  const items = useMilestones(founder.startupId);

  return (
    <>
      <h3 className="detail-heading">Milestones &amp; goals</h3>
      {items === null && (
        <div className="rounded-md border border-border p-3 text-[11px] text-muted-foreground">
          Milestones appear here when the dashboard is connected to the live ledger.
        </div>
      )}
      {items && !items.length && (
        <div className="rounded-md border border-border p-3 text-[11px] text-muted-foreground">
          No milestones yet. Founders and mentors add them by messaging the Slack bot, e.g. &ldquo;Set a milestone: 10
          customer interviews by Oct 23&rdquo;.
        </div>
      )}
      <div className="drawer-history">
        {items?.map((m) => {
          const done = m.goals.filter((g) => g.done).length;
          const pct = m.goals.length ? Math.round((done / m.goals.length) * 100) : m.status === "done" ? 100 : 0;
          return (
            <article key={m.id}>
              <p className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                <Target size={12} />
                {m.due_date ? `Due ${new Date(m.due_date).toLocaleDateString("en-SG", { month: "short", day: "numeric" })}` : "No due date"}
                {m.status === "done" && " · Done"}
              </p>
              <p className="mt-2 text-xs font-medium">{m.title}</p>
              <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted" aria-label={`${pct}% of goals done`}>
                <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
              </div>
              <p className="mt-1 text-[10px] text-muted-foreground">
                {done}/{m.goals.length} goals done
              </p>
              <ul className="mt-2 space-y-1">
                {m.goals.map((g) => (
                  <li key={g.id} className="flex items-start gap-2 text-xs leading-relaxed">
                    {g.done ? (
                      <CheckCheck size={12} className="mt-0.5 shrink-0 text-success" />
                    ) : (
                      <Circle size={11} className="mt-0.5 shrink-0 text-muted-foreground" />
                    )}
                    <span className={g.done ? "text-muted-foreground line-through" : ""}>{g.title}</span>
                  </li>
                ))}
              </ul>
            </article>
          );
        })}
      </div>
    </>
  );
}
