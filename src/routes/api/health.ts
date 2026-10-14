import { createFileRoute } from "@tanstack/react-router";
import { admin } from "@/lib/supabase-admin";

const STALE_AFTER_SECONDS = 150; // the bot beats every 30s

const json = (body: unknown, status: number) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });

// Is the Slack bot alive AND connected to Slack? An external uptime check calls this and alerts when it isn't 200.
export const Route = createFileRoute("/api/health")({
  server: {
    handlers: {
      GET: async () => {
        const res = await admin<{ beat_at: string; slack_connected: boolean }[]>(
          "bot_heartbeat?select=beat_at,slack_connected&id=eq.main",
        );
        const row = res.data?.[0];
        if (!res.ok || !row) return json({ ok: false, reason: "no heartbeat recorded" }, 503);
        const age = Math.round((Date.now() - Date.parse(row.beat_at)) / 1000);
        if (age > STALE_AFTER_SECONDS) return json({ ok: false, reason: "bot heartbeat is stale", ageSeconds: age }, 503);
        if (!row.slack_connected) return json({ ok: false, reason: "bot is not connected to Slack", ageSeconds: age }, 503);
        return json({ ok: true, ageSeconds: age }, 200);
      },
    },
  },
});
