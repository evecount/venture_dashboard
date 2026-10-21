// Server-only: who is looking at the dashboard. Identity comes from Slack (a signed link from the bot, or
// Sign in with Slack) and the role from the same tables the bot uses: anyone in `mentors` is a mentor, anyone in
// `founders` is a founder of their startup, everyone else is turned away. Never import this from client code.
import { admin } from "@/lib/supabase-admin";
import { hmacHex, safeEqual } from "@/lib/integrations";

export type Identity =
  | { role: "mentor"; slackUserId: string; name: string; mentorId: string }
  | { role: "founder"; slackUserId: string; name: string; founderId: string; startupId: string };

const SESSION_COOKIE = "vd_session";
export const SESSION_SECONDS = 30 * 24 * 60 * 60;

const secret = () => process.env["STATE_SECRET"] ?? "";
const b64url = (s: string) => btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const unb64url = (s: string) => atob(s.replace(/-/g, "+").replace(/_/g, "/"));

/** Signs a small payload for our own cookies and OAuth state. `purpose` stops one kind being replayed as another. */
export async function signToken(
  purpose: string,
  payload: Record<string, string>,
  ttlSeconds: number,
) {
  const body = b64url(
    JSON.stringify({ ...payload, exp: Math.floor(Date.now() / 1000) + ttlSeconds }),
  );
  return `${body}.${await hmacHex(secret(), `${purpose}:${body}`)}`;
}

export async function readToken<T extends Record<string, unknown>>(
  purpose: string,
  token: string | null,
) {
  if (!token || !secret()) return null;
  const [body, sig] = token.split(".");
  if (!body || !sig || !safeEqual(await hmacHex(secret(), `${purpose}:${body}`), sig)) return null;
  try {
    const payload = JSON.parse(unb64url(body)) as T & { exp: number };
    return payload.exp > Date.now() / 1000 ? payload : null;
  } catch {
    return null;
  }
}

export function readCookie(request: Request, name: string): string | null {
  for (const part of (request.headers.get("cookie") ?? "").split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k === name) return v.join("=");
  }
  return null;
}

function cookie(request: Request, value: string, maxAge: number) {
  const secure = new URL(request.url).protocol === "https:" ? "; Secure" : "";
  return `${SESSION_COOKIE}=${value}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${maxAge}${secure}`;
}

export async function sessionCookie(request: Request, slackUserId: string) {
  return cookie(
    request,
    await signToken("session", { u: slackUserId }, SESSION_SECONDS),
    SESSION_SECONDS,
  );
}

export const clearSessionCookie = (request: Request) => cookie(request, "", 0);

/** The browser that starts Sign in with Slack gets this short-lived cookie; only that browser can finish it. */
export const OIDC_COOKIE = "vd_oidc";
export function oidcCookie(request: Request, nonce: string, maxAge = 600) {
  const secure = new URL(request.url).protocol === "https:" ? "; Secure" : "";
  return `${OIDC_COOKIE}=${nonce}; Path=/api/auth/slack; HttpOnly; SameSite=Lax; Max-Age=${maxAge}${secure}`;
}

const SLACK_ID = /^[UW][A-Z0-9]{2,24}$/;

/** Looks the person up on every request, so removing someone from the tables locks them out straight away. */
export async function lookupIdentity(slackUserId: string): Promise<Identity | null> {
  if (!SLACK_ID.test(slackUserId)) return null;
  const id = encodeURIComponent(slackUserId);
  const mentor = await admin<{ id: string; name: string }[]>(
    `mentors?select=id,name&slack_user_id=eq.${id}&limit=1`,
  );
  const m = mentor.data?.[0];
  if (m) return { role: "mentor", slackUserId, name: m.name, mentorId: m.id };
  const founder = await admin<{ id: string; name: string; startup_id: string }[]>(
    `founders?select=id,name,startup_id&slack_user_id=eq.${id}&limit=1`,
  );
  const f = founder.data?.[0];
  if (f?.startup_id)
    return { role: "founder", slackUserId, name: f.name, founderId: f.id, startupId: f.startup_id };
  return null;
}

export async function identityFromRequest(request: Request): Promise<Identity | null> {
  const session = await readToken<{ u: string }>("session", readCookie(request, SESSION_COOKIE));
  return session ? lookupIdentity(session.u) : null;
}

export const json = (body: unknown, status = 200, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store", ...headers },
  });
