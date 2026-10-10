import { createFileRoute } from "@tanstack/react-router";
import { CommandCenter } from "@/components/dashboard/command-center";
export const Route = createFileRoute("/")({
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
  component: CommandCenter,
});
