import { createFileRoute } from "@tanstack/react-router";
import { admin } from "@/lib/supabase-admin";
import { verifyState } from "@/lib/integrations";

const page = (title: string, body: string, status = 200) =>
  new Response(
    `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title>` +
      `<style>body{font-family:system-ui,sans-serif;max-width:32rem;margin:15vh auto;padding:0 1rem;line-height:1.5}</style></head>` +
      `<body><h1>${title}</h1><p>${body}</p></body></html>`,
    { status, headers: { "content-type": "text/html; charset=utf-8" } },
  );

// Google redirects here after the founder approves read-only calendar access. We only park the one-time code;
// the Slack bot (which holds the client secret) exchanges it for tokens.
export const Route = createFileRoute("/api/google/callback")({
  server: {
    handlers: {
      GET: async ({ request }) => {
        const url = new URL(request.url);
        if (url.searchParams.get("error")) {
          return page(
            "Not connected",
            "You declined access, so nothing was connected. You can go back to Slack and try again any time.",
          );
        }
        const state = await verifyState(
          url.searchParams.get("state"),
          process.env["STATE_SECRET"] ?? "",
        );
        const code = url.searchParams.get("code");
        const studio = state?.p === "google-studio";
        const mentor = state?.p === "google-mentor"; // a mentor's own calendar (read-only), not the studio one
        if (!state || (state.p !== "google" && !studio && !mentor) || !code || code.length > 2048) {
          return page(
            "Link expired",
            "This connect link is invalid or has expired. Go back to Slack and ask the bot for a new one.",
            400,
          );
        }
        const res = await admin("google_pending", {
          method: "POST",
          prefer: "return=minimal",
          body:
            studio || mentor
              ? { kind: studio ? "studio" : "mentor", slack_user_id: state.f, code }
              : { founder_id: state.f, startup_id: state.s, code },
        });
        if (!res.ok)
          return page(
            "Something went wrong",
            "I couldn't save the connection. Please try again from Slack.",
            500,
          );
        return page(
          "Google Calendar connected",
          "Head back to Slack: the bot will confirm in a moment. You can close this tab.",
        );
      },
    },
  },
});
