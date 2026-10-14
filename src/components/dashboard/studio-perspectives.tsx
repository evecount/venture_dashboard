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
