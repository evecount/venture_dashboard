// Server-only: the Developer page is for the developer accounts in DEV_EMAILS (default ben@evecount.com), matched
// against the signed-in mentor's email in the `mentors` table. Never import this from client code.
import { admin } from "@/lib/supabase-admin";
import { identityFromRequest, type Identity } from "@/lib/dash-auth";

const devEmails = () =>
  (process.env["DEV_EMAILS"] ?? "ben@evecount.com")
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean);

export async function developerFromRequest(request: Request): Promise<Identity | null> {
  const identity = await identityFromRequest(request);
  if (identity?.role !== "mentor") return null;
  const res = await admin<{ email: string | null }[]>(
    `mentors?select=email&id=eq.${encodeURIComponent(identity.mentorId)}&limit=1`,
  );
  const email = res.data?.[0]?.email?.trim().toLowerCase();
  return email && devEmails().includes(email) ? identity : null;
}
