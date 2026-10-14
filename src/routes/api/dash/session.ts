import { createFileRoute } from "@tanstack/react-router";
import { clearSessionCookie, identityFromRequest, json } from "@/lib/dash-auth";
import { developerFromRequest } from "@/lib/dev-auth";

// Who is signed in (role re-checked against the mentors/founders tables on every call). DELETE signs out.
export const Route = createFileRoute("/api/dash/session")({
  server: {
    handlers: {
      GET: async ({ request }) => {
        const identity = await identityFromRequest(request);
        if (!identity) return json({ identity: null }, 401);
        // `dev` only shows the Developer menu entry; /api/dev/* re-checks on every call.
        return json({ identity, dev: Boolean(await developerFromRequest(request)) });
      },
      DELETE: async ({ request }) =>
        json({ ok: true }, 200, { "set-cookie": clearSessionCookie(request) }),
    },
  },
});
