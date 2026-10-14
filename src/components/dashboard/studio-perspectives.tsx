import { Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { studioRoles, type DemoPerspective, type Founder } from "./data";
import { leadMentor, type MentorLike } from "./insights";

/** Mentors only: preview the layout a founder sees. Presentation only; access comes from the signed-in role. */
export function ViewAs({
  perspective,
  members,
  onChange,
}: {
  perspective: DemoPerspective;
  members: Founder[];
  onChange: (value: DemoPerspective) => void;
}) {
  const member = members.find(
    (founder) => founder.id === perspective || founder.founderIds?.includes(perspective),
  );
  return (
    <label className="view-as" title="Preview the dashboard as a founder sees it">
      <span className="sr-only">Preview as</span>
      <select
        id="demo-perspective"
        value={member?.id ?? perspective}
        onChange={(event) => {
          const value = event.target.value;
          const valid = [
            ...studioRoles.map((item) => item.id),
            ...members.map((item) => item.id),
          ].find((id) => id === value);
          if (valid) onChange(valid as DemoPerspective);
        }}
      >
        <option value="coordinator">Mentor view</option>
        <optgroup label="Cohort members · preview as founder">
          {members.map((founder) => (
            <option key={founder.id} value={founder.id}>
              {founder.startup.split(" · ")[0]}
            </option>
          ))}
        </optgroup>
      </select>
    </label>
  );
}

/** The studio team: the real mentors and the startups each one leads, then what each program role covers. */
export function TeamPopover({
  perspective,
  mentors = [],
  founders = [],
}: {
  perspective: DemoPerspective;
  mentors?: MentorLike[];
  founders?: Founder[];
}) {
  const ledBy = (m: MentorLike) =>
    founders
      .filter((f) => leadMentor(f.lead, mentors)?.id === m.id)
      .map((f) => f.startup.split(" · ")[0]);
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="quiet" size="sm" className="gap-1.5">
          <Users size={15} />
          <span className="hide-sm">Team</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="max-h-[70vh] w-80 overflow-y-auto p-0">
        {mentors.length > 0 && (
          <>
            <div className="border-b border-border px-4 py-3">
              <p className="text-sm font-semibold">Mentors</p>
              <p className="mt-0.5 text-xs text-muted-foreground">Signed up through the bot</p>
            </div>
            <ul className="divide-y divide-border border-b border-border">
              {mentors.map((m) => {
                const led = ledBy(m);
                return (
                  <li key={m.id} className="px-4 py-3">
                    <p className="text-sm font-medium">{m.name}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {m.title || "Mentor"} ·{" "}
                      {led.length ? `Leads ${led.join(", ")}` : "No startups yet"}
                    </p>
                  </li>
                );
              })}
            </ul>
          </>
        )}
        <div className="border-b border-border px-4 py-3">
          <p className="text-sm font-semibold">Program roles</p>
          <p className="mt-0.5 text-xs text-muted-foreground">MVP program core team</p>
        </div>
        <ul className="divide-y divide-border">
          {studioRoles.map((item) => (
            <li key={item.id} className="px-4 py-3">
              <p className="text-xs text-muted-foreground">{item.focus}</p>
              <p
                className={`mt-0.5 text-sm font-medium ${item.id === perspective ? "text-primary" : ""}`}
              >
                {item.title}
              </p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                {item.responsibility}
              </p>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}
