import { createFileRoute } from "@tanstack/react-router";
import { admin } from "@/lib/supabase-admin";
import { verifyState } from "@/lib/integrations";
import { canLinkInstallation } from "@/lib/dash-scope";

const page = (title: string, body: string, status = 200) =>
  new Response(
    `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title>` +
      `<style>body{font-family:system-ui,sans-serif;max-width:32rem;margin:15vh auto;padding:0 1rem;line-height:1.5}</style></head>` +
      `<body><h1>${title}</h1><p>${body}</p></body></html>`,
    { status, headers: { "content-type": "text/html; charset=utf-8" } },
  );

// GitHub redirects here after the founder installs the app and picks their repositories.
export const Route = createFileRoute("/api/github/callback")({
  server: {
    handlers: {
      GET: async ({ request }) => {
        const url = new URL(request.url);
        const state = await verifyState(url.searchParams.get("state"), process.env["STATE_SECRET"] ?? "");
        const installationId = url.searchParams.get("installation_id");
        // Changing the repo selection later redirects here without our state; the webhook updates the repo list itself.
        if (!state && url.searchParams.get("setup_action") === "update") {
          return page("Repositories updated", "Your repository selection was saved. You can close this tab and go back to Slack.");
        }
        if (!state || state.p !== "github") {
          return page("Link expired", "This connect link is invalid or has expired. Go back to Slack and ask the bot for a new one.", 400);
        }
        if (!installationId || !/^\d+$/.test(installationId)) {
          return page("Nothing to connect", "GitHub didn't send an installation. Go back to Slack and try again.", 400);
        }
        // Repos GitHub already told us about (the webhook usually arrives before the browser does).
        const staged = await admin<{ account: string | null; repos: string[] | null }[]>(
          `github_installations?select=account,repos&installation_id=eq.${installationId}`,
        );
        const known = staged.data?.[0];
        // An installation already linked to another startup is never re-pointed: the id comes from the URL, so a
        // valid link for one startup must not be able to take over someone else's connection.
        const current = await admin<{ startup_id: string }[]>(
          `integrations?select=startup_id&provider=eq.github&external_id=eq.${installationId}&limit=1`,
        );
        if (!current.ok) return page("Something went wrong", "I couldn't check the connection. Please try again from Slack.", 500);
        if (!canLinkInstallation(current.data?.[0], state.s)) {
          return page("Already connected", "That GitHub installation is already linked to another startup, so I left it as it is. Ask a mentor if this looks wrong.", 409);
        }
        const res = await admin("integrations?on_conflict=provider,external_id", {
          method: "POST",
          prefer: "resolution=merge-duplicates,return=minimal",
          body: {
            startup_id: state.s, founder_id: state.f, provider: "github", external_id: installationId,
            ...(known ? { account: known.account, repos: known.repos ?? [] } : {}),
            notified_at: null, // (re)send the Slack confirmation and repo picker
          },
        });
        if (!res.ok) return page("Something went wrong", "I couldn't save the connection. Please try again from Slack.", 500);
        return page("GitHub connected", "Head back to Slack: the bot is sending you a confirmation and lets you choose which repositories to monitor. You can close this tab.");
      },
    },
  },
});
