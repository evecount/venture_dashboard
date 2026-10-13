import { createFileRoute } from "@tanstack/react-router";
import { verifyState } from "@/lib/integrations";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

// The "Open dashboard" button in Slack carries a signed personal pass (?k=...). A valid pass skips the access code
// on any device; a missing, forged or expired one just falls back to the code screen.
export const Route = createFileRoute("/api/dash/claim")({
  server: {
    handlers: {
      POST: async ({ request }) => {
        let body: { k?: string } = {};
        try {
          body = await request.json();
        } catch {
          return json({ ok: false }, 400);
        }
        const pass = await verifyState(body.k ?? null, process.env["STATE_SECRET"] ?? "");
        return json({ ok: !!pass && pass.p === "dash" });
      },
    },
  },
});
