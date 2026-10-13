import { Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { studioRoles, type DemoPerspective, type Founder } from "./data";

/** "View as" switcher. Presentation only: it changes the layout, never what data is allowed. */
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
    <label className="view-as" title="View as · No sign-in or access control">
      <span className="sr-only">View as · No sign-in or access control</span>
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
        <optgroup label="MVP program core team">
          {studioRoles.map((item) => (
            <option key={item.id} value={item.id}>
              {item.title}
            </option>
          ))}
        </optgroup>
        <optgroup label="Cohort members">
          {members.map((founder) => (
            <option key={founder.id} value={founder.id}>
              {founder.startup.split(" · ")[0]} · {founder.name}
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
