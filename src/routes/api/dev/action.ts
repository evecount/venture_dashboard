import { createFileRoute } from "@tanstack/react-router";
import { json } from "@/lib/dash-auth";
import { developerFromRequest } from "@/lib/dev-auth";
import { admin } from "@/lib/supabase-admin";
import { validDevAction } from "@/lib/dev-actions";

// Developer page writes: switch a channel on/off, change a bot setting, or queue a bot command.
// The bot (VM) picks commands up within ~5 s and writes the result back to bot_commands.
export const Route = createFileRoute("/api/dev/action")({
  server: {
    handlers: {
      POST: async ({ request }) => {
        const dev = await developerFromRequest(request);
        if (!dev) return json({ ok: false }, 404);
        const action = validDevAction(await request.json().catch(() => null));
        if (!action) return json({ ok: false, error: "invalid" }, 400);
        const now = new Date().toISOString();

        if (action.type === "channel") {
          const id = encodeURIComponent(action.id);
          const res = await admin(`bot_channels?id=eq.${id}`, {
            method: "PATCH",
            body: action.enabled
              ? { enabled: true, status: "Syncing…", updated_at: now }
              : { enabled: false, status: "Off. Its messages were forgotten.", updated_at: now },
            prefer: "return=minimal",
          });
          if (!res.ok) return json({ ok: false }, 502);
          if (action.enabled)
            await queue("sync_channel", { channel_id: action.id }, dev.slackUserId);
          else await admin(`channel_messages?channel_id=eq.${id}`, { method: "DELETE" });
          return json({ ok: true });
        }

        if (action.type === "setting") {
          const res = await admin("bot_settings?on_conflict=key", {
            method: "POST",
            body: { key: action.key, value: action.value, updated_at: now },
            prefer: "resolution=merge-duplicates,return=minimal",
          });
          return json({ ok: res.ok }, res.ok ? 200 : 502);
        }

        const id = await queue(action.command, action.args, dev.slackUserId);
        return json({ ok: Boolean(id), id }, id ? 200 : 502);
      },
    },
  },
});

async function queue(command: string, args: Record<string, string>, by: string) {
  const res = await admin<{ id: string }[]>("bot_commands", {
    method: "POST",
    body: { command, args, requested_by: by },
    prefer: "return=representation",
  });
  return res.data?.[0]?.id ?? null;
}
