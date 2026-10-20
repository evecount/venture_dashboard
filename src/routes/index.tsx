import { createFileRoute } from "@tanstack/react-router";
import { CommandCenter } from "@/components/dashboard/command-center";
import { parsePerspective } from "@/components/dashboard/data";
function IndexPage() {
  const { as, s, c } = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <CommandCenter
      initialPerspective={parsePerspective(as)}
      onPerspectiveChange={(value) => navigate({ search: { as: value }, replace: true })}
      openStartupId={s}
      // Opening a startup pushes a history entry, so the browser's back button returns to the list.
      onOpenStartup={(id) => navigate({ search: (prev) => ({ ...prev, s: id }) })}
      initialCohortId={c}
      onCohortChange={(id) => navigate({ search: (prev) => ({ ...prev, c: id }), replace: true })}
    />
  );
}

export const Route = createFileRoute("/")({
  // Presentation-only deep link (e.g. ?as=demo-founder-01), not an access control.
  validateSearch: (
    search: Record<string, unknown>,
  ): { as?: string | undefined; s?: string | undefined; c?: string | undefined } => ({
    as: typeof search["as"] === "string" ? search["as"] : undefined,
    s:
      typeof search["s"] === "string" && /^[A-Za-z0-9_-]{1,64}$/.test(search["s"])
        ? search["s"]
        : undefined,
    c:
      typeof search["c"] === "string" && /^[A-Za-z0-9_-]{1,64}$/.test(search["c"])
        ? search["c"]
        : undefined,
  }),
  head: () => ({
    meta: [
      { title: "Cohort Pulse · Venture Studio MVP" },
      {
        name: "description",
        content:
          "Venture Studio’s command center for the MVP Program cohorts. Track sprint momentum, founder check-ins, deliverables and priority blockers.",
      },
      { property: "og:title", content: "Cohort Pulse · Venture Studio MVP" },
      {
        property: "og:description",
        content:
          "A clear view of founder progress, sprint milestones and studio priorities for the MVP Program cohorts.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: IndexPage,
});
