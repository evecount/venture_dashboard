import { createFileRoute } from "@tanstack/react-router";
import { clearSessionCookie, identityFromRequest, json } from "@/lib/dash-auth";

// Who is signed in (role re-checked against the mentors/founders tables on every call). DELETE signs out.
export const Route = createFileRoute("/api/dash/session")({
  server: {
    handlers: {
      GET: async ({ request }) => {
        const identity = await identityFromRequest(request);
        return identity ? json({ identity }) : json({ identity: null }, 401);
      },
      DELETE: async ({ request }) =>
        json({ ok: true }, 200, { "set-cookie": clearSessionCookie(request) }),
    },
  },
});
