import { Users, ArrowUpRight, Target } from "lucide-react";
import { Button } from "@/components/ui/button";
import { founders, studioRoles, type DemoPerspective, type Founder } from "./data";

export function StudioPerspectives({ perspective, onChange, openFounder }: {
  perspective: DemoPerspective;
  onChange: (value: DemoPerspective) => void;
  openFounder: (founder: Founder, tab?: string) => void;
}) {
  const member = founders.find((founder) => founder.id === perspective);
  const role = studioRoles.find((item) => item.id === perspective);
  return (
    <section className="mb-8 border-y border-border py-5" aria-labelledby="studio-team-title">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 id="studio-team-title" className="flex items-center gap-2 text-sm font-semibold"><Users size={15} /> Venture studio</h2>
          <p className="mt-1 text-[11px] text-muted-foreground">Cohort members & MVP program core team</p>
        </div>
        <div className="w-full sm:w-80">
          <label htmlFor="demo-perspective" className="text-[10px] font-medium text-muted-foreground">Demo perspective · No sign-in or access control</label>
          <select id="demo-perspective" className="mt-1 w-full rounded-md border border-border bg-card p-2 text-xs" value={perspective} onChange={(event) => {
            const value = event.target.value;
            const valid = [...studioRoles.map((item) => item.id), "demo-founder-01", "demo-founder-02"].find((id) => id === value);
            if (valid) onChange(valid as DemoPerspective);
          }}>
            <optgroup label="MVP program core team">{studioRoles.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</optgroup>
            <optgroup label="Cohort members">{founders.map((founder) => <option key={founder.id} value={founder.id}>{founder.name} · Cohort member</option>)}</optgroup>
          </select>
        </div>
      </div>
      <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {studioRoles.map((item) => (
          <div key={item.id} className={`border-l-2 pl-3 ${item.id === perspective ? "border-primary" : "border-border"}`}>
            <p className="text-[9px] uppercase text-muted-foreground">{item.focus}</p>
            <h3 className="mt-1 text-xs font-semibold leading-relaxed">{item.title}</h3>
            <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">{item.responsibility}</p>
          </div>
        ))}
      </div>
      {role && <div className="mt-5 flex items-start gap-2 border-t border-border pt-4 text-xs"><Target size={14} className="shrink-0 text-primary" /><div><p className="font-medium">{role.title} · Demo priority</p><p className="mt-1 text-muted-foreground">{role.task}</p></div></div>}
      {member && <div className="mt-6 border-t border-border pt-5" id="cohort">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div><h3 className="text-sm font-semibold">{member.name} · My venture</h3><p className="mt-1 text-xs text-muted-foreground">{member.startup}</p></div>
          <span className="pill pill-neutral">Cohort member · Fictional</span>
        </div>
        <div className="mt-5 grid gap-5 sm:grid-cols-3">
          <div><p className="text-[10px] text-muted-foreground">Sprint 1 deliverable</p><p className="mt-2 text-xs">1-page venture thesis · {member.progress}%</p><p className="mt-2 text-[11px] text-muted-foreground">Demo gate · October 16</p></div>
          <div><p className="text-[10px] text-muted-foreground">My latest check-in</p><p className="mt-2 text-xs leading-relaxed">{member.digest}</p></div>
          <div><p className="text-[10px] text-muted-foreground">My support request</p><p className="mt-2 text-xs leading-relaxed">{member.blocker}</p><p className="mt-2 text-[11px] text-primary">{member.lead}</p></div>
        </div>
        <div className="mt-5 flex flex-wrap gap-2"><Button variant="outline" size="sm" onClick={() => openFounder(member, "Check-ins")}>My check-ins <ArrowUpRight size={12} /></Button><Button variant="outline" size="sm" onClick={() => openFounder(member, "Office hours")}>My office hours <ArrowUpRight size={12} /></Button></div>
      </div>}
    </section>
  );
}