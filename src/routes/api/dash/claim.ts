import { createFileRoute } from "@tanstack/react-router";
import { admin } from "@/lib/supabase-admin";
import { verifyState } from "@/lib/integrations";
import { json, lookupIdentity, sessionCookie } from "@/lib/dash-auth";

type DashPass = { f: string; u?: string; j?: string; p: string };

// The "Open dashboard" button in Slack carries a signed, short-lived, single-use pass (?k=...) naming the person.
// A valid pass signs them in (cookie); a used, forged or expired one falls back to Sign in with Slack.
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
        const pass = (await verifyState(
          body.k ?? null,
          process.env["STATE_SECRET"] ?? "",
        )) as DashPass | null;
        if (!pass || pass.p !== "dash" || !pass.j)
          return json({ ok: false, reason: "expired" }, 401);

        // Single use: a forwarded or leaked link stops working once its owner has opened it.
        const used = await admin("dash_link_uses", {
          method: "POST",
          body: { jti: pass.j },
          prefer: "return=minimal",
        });
        if (!used.ok) return json({ ok: false, reason: "used" }, 401);

        let slackUserId = pass.u;
        if (!slackUserId && pass.f.startsWith("founder-")) {
          const row = await admin<{ slack_user_id: string | null }[]>(
            `founders?select=slack_user_id&id=eq.${encodeURIComponent(pass.f)}&limit=1`,
          );
          slackUserId = row.data?.[0]?.slack_user_id ?? undefined;
        }
        const identity = slackUserId ? await lookupIdentity(slackUserId) : null;
        if (!identity) return json({ ok: false, reason: "not_on_roster" }, 403);
        return json({ ok: true }, 200, {
          "set-cookie": await sessionCookie(request, identity.slackUserId),
        });
      },
    },
  },
});
