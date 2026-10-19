import { createFileRoute } from "@tanstack/react-router";
import { admin } from "@/lib/supabase-admin";
import { identityFromRequest, json } from "@/lib/dash-auth";

// "Mark handled" on the mentor dashboard, for signed-in mentors only. Body: { startup_id, handled, note? }.
// handled=false clears the mark. Who handled it comes from the session, never the request.
export const Route = createFileRoute("/api/dash/handled")({
  server: {
    handlers: {
      POST: async ({ request }) => {
        const identity = await identityFromRequest(request);
        if (identity?.role !== "mentor") return json({ ok: false }, identity ? 403 : 401);
        let body: { startup_id?: unknown; handled?: unknown; note?: unknown } = {};
        try {
          body = await request.json();
        } catch {
          return json({ ok: false }, 400);
        }
        const id = typeof body.startup_id === "string" ? body.startup_id : "";
        if (!/^[A-Za-z0-9_-]{1,64}$/.test(id)) return json({ ok: false }, 400);

        const note = typeof body.note === "string" ? body.note.trim().slice(0, 300) : "";
        const upsert = (row: Record<string, unknown>) =>
          admin("blocker_reviews?on_conflict=startup_id", {
            method: "POST",
            body: row,
            prefer: "resolution=merge-duplicates,return=minimal",
          });
        const base = { startup_id: id, handled_at: new Date().toISOString() };
        let res;
        if (body.handled === false) {
          res = await admin(`blocker_reviews?startup_id=eq.${encodeURIComponent(id)}`, {
            method: "DELETE",
          });
        } else {
          res = await upsert({ ...base, handled_by: identity.name, note: note || null });
          // Before 2026-10-milestone-progress.sql runs there are no handled_by/note columns.
          if (!res.ok) res = await upsert(base);
        }
        return json({ ok: res.ok }, res.ok ? 200 : 502);
      },
    },
  },
});
