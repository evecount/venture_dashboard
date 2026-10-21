import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/supabase-admin", () => ({ admin: vi.fn() }));

import { admin } from "@/lib/supabase-admin";
import { identityFromRequest, lookupIdentity, readToken, signToken } from "@/lib/dash-auth";

const mockAdmin = vi.mocked(admin);
const reply = (data: unknown) => ({ ok: true, status: 200, data });

describe("dashboard sign-in", () => {
  beforeEach(() => {
    process.env["STATE_SECRET"] = "test-secret";
    mockAdmin.mockReset();
  });
  afterEach(() => {
    delete process.env["STATE_SECRET"];
  });

  it("rejects tokens that were tampered with, expired, or made for another purpose", async () => {
    const token = await signToken("session", { u: "U123" }, 60);
    expect(await readToken("session", token)).toMatchObject({ u: "U123" });
    expect(await readToken("oidc", token)).toBeNull();
    expect(await readToken("session", token.replace(/^./, "x"))).toBeNull();
    expect(await readToken("session", await signToken("session", { u: "U123" }, -1))).toBeNull();
  });

  it("lets in mentors and founders from the roster, and nobody else", async () => {
    mockAdmin.mockImplementation(async (path: string) =>
      reply(
        path.startsWith("mentors") && path.includes("UMENTOR")
          ? [{ id: "m1", name: "Mentor" }]
          : path.startsWith("founders") && path.includes("UFOUNDER")
            ? [{ id: "f1", name: "Founder", startup_id: "startup-a" }]
            : [],
      ),
    );
    expect(await lookupIdentity("UMENTOR")).toMatchObject({ role: "mentor" });
    expect(await lookupIdentity("UFOUNDER")).toMatchObject({
      role: "founder",
      startupId: "startup-a",
    });
    expect(await lookupIdentity("USTRANGER")).toBeNull();
    expect(await lookupIdentity("not-a-slack-id")).toBeNull();
  });

  it("re-checks the roster on every request, so removed people lose access", async () => {
    const cookie = `vd_session=${await signToken("session", { u: "UFOUNDER" }, 60)}`;
    const request = new Request("https://dash.example/api/dash/snapshot", { headers: { cookie } });
    mockAdmin.mockResolvedValue(reply([]));
    expect(await identityFromRequest(request)).toBeNull();
  });
});

describe("sign-in browser binding", () => {
  it("scopes the flow cookie to the sign-in routes, HttpOnly and Lax", async () => {
    const { oidcCookie, readCookie, OIDC_COOKIE } = await import("@/lib/dash-auth");
    const set = oidcCookie(new Request("https://dash.example/api/auth/slack"), "nonce-1");
    expect(set).toContain("vd_oidc=nonce-1");
    expect(set).toContain("Path=/api/auth/slack");
    expect(set).toMatch(/HttpOnly/);
    expect(set).toMatch(/SameSite=Lax/);
    expect(set).toMatch(/Secure/);
    const back = new Request("https://dash.example/api/auth/slack/callback", { headers: { cookie: `a=1; ${OIDC_COOKIE}=nonce-1` } });
    expect(readCookie(back, OIDC_COOKIE)).toBe("nonce-1");
    expect(readCookie(new Request("https://dash.example/x"), OIDC_COOKIE)).toBeNull(); // another browser: no cookie, no sign-in
  });
});
