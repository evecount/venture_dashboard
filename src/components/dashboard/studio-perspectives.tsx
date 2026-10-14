import { Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { studioRoles, type DemoPerspective, type Founder } from "./data";

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

/** The studio team and what each role covers, tucked behind a button instead of taking up the page. */
export function TeamPopover({ perspective }: { perspective: DemoPerspective }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="quiet" size="sm" className="gap-1.5">
          <Users size={15} />
          <span className="hide-sm">Team</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0">
        <div className="border-b border-border px-4 py-3">
          <p className="text-sm font-semibold">Venture studio</p>
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
