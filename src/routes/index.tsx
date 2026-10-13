import { createFileRoute } from "@tanstack/react-router";
import { CommandCenter } from "@/components/dashboard/command-center";
import { parsePerspective } from "@/components/dashboard/data";
function IndexPage() {
  const { as } = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <CommandCenter
      initialPerspective={parsePerspective(as)}
      onPerspectiveChange={(value) =>
        navigate({ search: { as: value }, replace: true })
      }
    />
  );
}

export const Route = createFileRoute("/")({
  // Presentation-only deep link (e.g. ?as=demo-founder-01), not an access control.
  validateSearch: (search: Record<string, unknown>): { as?: string | undefined } => ({
    as: typeof search["as"] === "string" ? search["as"] : undefined,
  }),
  head: () => ({
    meta: [
      { title: "Cohort Pulse · Adventure Studio SG#01" },
      {
        name: "description",
        content:
          "Adventure Studio’s command center for Cohort SG#01. Track sprint momentum, founder check-ins, deliverables and priority blockers.",
      },
      { property: "og:title", content: "Cohort Pulse · Adventure Studio SG#01" },
      {
        property: "og:description",
        content:
          "A clear view of founder progress, sprint milestones and studio priorities for Cohort SG#01.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: IndexPage,
});
