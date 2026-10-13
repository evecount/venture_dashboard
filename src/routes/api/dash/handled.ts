import { createFileRoute } from "@tanstack/react-router";
import { admin } from "@/lib/supabase-admin";
import { identityFromRequest, json } from "@/lib/dash-auth";

// "Mark handled" on the mentor dashboard, for signed-in mentors only. Body: { startup_id, handled }.
// handled=false clears the mark.
export const Route = createFileRoute("/api/dash/handled")({
  server: {
    handlers: {
      POST: async ({ request }) => {
        const identity = await identityFromRequest(request);
        if (identity?.role !== "mentor") return json({ ok: false }, identity ? 403 : 401);
        let body: { startup_id?: unknown; handled?: unknown } = {};
        try {
          body = await request.json();
        } catch {
          return json({ ok: false }, 400);
        }
        const id = typeof body.startup_id === "string" ? body.startup_id : "";
        if (!/^[A-Za-z0-9_-]{1,64}$/.test(id)) return json({ ok: false }, 400);

        const res =
          body.handled === false
            ? await admin(`blocker_reviews?startup_id=eq.${encodeURIComponent(id)}`, {
                method: "DELETE",
              })
            : await admin("blocker_reviews?on_conflict=startup_id", {
                method: "POST",
                body: { startup_id: id, handled_at: new Date().toISOString() },
                prefer: "resolution=merge-duplicates,return=minimal",
              });
        return json({ ok: res.ok }, res.ok ? 200 : 502);
      },
    },
  },
});
