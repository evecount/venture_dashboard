import { createFileRoute } from "@tanstack/react-router";
import { lookupIdentity, readToken, sessionCookie } from "@/lib/dash-auth";

const redirect = (to: string, headers: Record<string, string> = {}) =>
  new Response(null, {
    status: 302,
    headers: { location: to, "cache-control": "no-store", ...headers },
  });

function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const part = token.split(".")[1] ?? "";
    return JSON.parse(atob(part.replace(/-/g, "+").replace(/_/g, "/"))) as Record<string, unknown>;
  } catch {
    return null;
  }
}

// Slack sends the person back here. Being in the Slack workspace isn't enough: they must also be in the
// `mentors` or `founders` table (the same roster the bot uses), otherwise they're turned away.
export const Route = createFileRoute("/api/auth/slack/callback")({
  server: {
    handlers: {
      GET: async ({ request }) => {
        const url = new URL(request.url);
        const origin = url.origin;
        const state = await readToken<{ n: string }>("oidc", url.searchParams.get("state"));
        const code = url.searchParams.get("code");
        if (!state || !code) return redirect(`${origin}/?signin=cancelled`);

        const clientId = process.env["SLACK_CLIENT_ID"] ?? "";
        const res = await fetch("https://slack.com/api/openid.connect.token", {
          method: "POST",
          headers: { "content-type": "application/x-www-form-urlencoded" },
          body: new URLSearchParams({
            client_id: clientId,
            client_secret: process.env["SLACK_CLIENT_SECRET"] ?? "",
            code,
            redirect_uri: `${origin}/api/auth/slack/callback`,
          }),
        });
        const token = (await res.json().catch(() => ({}))) as { ok?: boolean; id_token?: string };
        // The ID token came straight from Slack over TLS in exchange for our client secret, so its claims are Slack's.
        const claims = token.ok && token.id_token ? decodeJwtPayload(token.id_token) : null;
        if (!claims || claims["aud"] !== clientId || claims["nonce"] !== state.n) {
          return redirect(`${origin}/?signin=failed`);
        }
        const team = process.env["SLACK_TEAM_ID"];
        if (team && claims["https://slack.com/team_id"] !== team)
          return redirect(`${origin}/?signin=denied`);

        const identity = await lookupIdentity(String(claims["https://slack.com/user_id"] ?? ""));
        if (!identity) return redirect(`${origin}/?signin=denied`);
        return redirect(`${origin}/`, {
          "set-cookie": await sessionCookie(request, identity.slackUserId),
        });
      },
    },
  },
});
