import { createFileRoute } from "@tanstack/react-router";
import { signToken } from "@/lib/dash-auth";

// Starts Sign in with Slack (OpenID Connect). Slack proves who the person is; the callback checks the roster.
export const Route = createFileRoute("/api/auth/slack/")({
  server: {
    handlers: {
      GET: async ({ request }) => {
        const clientId = process.env["SLACK_CLIENT_ID"];
        const origin = new URL(request.url).origin;
        if (!clientId || !process.env["STATE_SECRET"])
          return Response.redirect(`${origin}/?signin=unavailable`, 302);
        const nonce = crypto.randomUUID();
        const params = new URLSearchParams({
          response_type: "code",
          scope: "openid profile",
          client_id: clientId,
          redirect_uri: `${origin}/api/auth/slack/callback`,
          state: await signToken("oidc", { n: nonce }, 600),
          nonce,
        });
        const team = process.env["SLACK_TEAM_ID"];
        if (team) params.set("team", team);
        return Response.redirect(`https://slack.com/openid/connect/authorize?${params}`, 302);
      },
    },
  },
});
