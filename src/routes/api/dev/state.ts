import { createFileRoute } from "@tanstack/react-router";
import { json } from "@/lib/dash-auth";
import { developerFromRequest } from "@/lib/dev-auth";
import { admin } from "@/lib/supabase-admin";

// Everything the Developer page shows. Developer only; anyone else gets a 404 so the page stays invisible.
export const Route = createFileRoute("/api/dev/state")({
  server: {
    handlers: {
      GET: async ({ request }) => {
        if (!(await developerFromRequest(request))) return json({ ok: false }, 404);
        const [heartbeat, channels, settings, commands, logs] = await Promise.all([
          admin<unknown[]>("bot_heartbeat?select=*&id=eq.main"),
          admin<unknown[]>(
            "bot_channels?select=id,name,is_private,is_member,num_members,enabled,status,backfilled_at&order=name",
          ),
          admin<unknown[]>("bot_settings?select=key,value"),
          admin<unknown[]>(
            "bot_commands?select=id,command,args,status,result,created_at,finished_at&order=created_at.desc&limit=25",
          ),
          admin<unknown[]>("bot_logs?select=id,line,created_at&order=id.desc&limit=300"),
        ]);
        const missing = [
          ["bot_channels", channels],
          ["bot_settings", settings],
          ["bot_commands", commands],
          ["bot_logs", logs],
        ]
          .filter(([, r]) => !(r as { ok: boolean }).ok)
          .map(([name]) => name);
        return json({
          ok: true,
          missing,
          heartbeat: heartbeat.data?.[0] ?? null,
          channels: channels.data ?? [],
          settings: Object.fromEntries(
            ((settings.data ?? []) as { key: string; value: unknown }[]).map((s) => [s.key, s.value]),
          ),
          commands: commands.data ?? [],
          logs: logs.data ?? [],
        });
      },
    },
  },
});
