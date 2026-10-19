import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type { Identity } from "@/lib/dash-auth";

type Auth = { identity: Identity; signOut: () => Promise<void> };
const AuthContext = createContext<Auth | null>(null);

/** The signed-in person. Only available under <SignInGate>. */
export function useAuth(): Auth {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error("useAuth must be used inside <SignInGate>");
  return auth;
}

const MESSAGES: Record<string, string> = {
  used: "That dashboard link has already been used. Sign in with Slack, or press Open dashboard in Slack again.",
  expired:
    "That dashboard link has expired. Sign in with Slack, or press Open dashboard in Slack again.",
  not_on_roster: "That Slack account isn't on the program roster. Ask the studio team to add you.",
  denied: "That Slack account isn't on the program roster. Ask the studio team to add you.",
  cancelled: "Sign-in was cancelled.",
  failed: "Slack sign-in didn't complete. Try again.",
  unavailable: "Sign in with Slack isn't set up yet. Press Open dashboard in Slack instead.",
};

/**
 * Only people on the program roster get past this: a mentor (mentors table) or a founder (founders table),
 * identified through Slack. Either the bot's single-use "Open dashboard" link or Sign in with Slack.
 */
export function SignInGate({ children }: { children: ReactNode }) {
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [state, setState] = useState<"checking" | "signed-out" | "signed-in">("checking");
  const [reason, setReason] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const url = new URL(window.location.href);
      const pass = url.searchParams.get("k");
      const signin = url.searchParams.get("signin");
      let why = signin;
      if (pass || signin) {
        url.searchParams.delete("k"); // keep the pass out of the address bar and browser history
        url.searchParams.delete("signin");
        window.history.replaceState(null, "", url.toString());
      }
      if (pass) {
        const res = await fetch("/api/dash/claim", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ k: pass }),
        }).catch(() => null);
        const body = (await res?.json().catch(() => null)) as {
          ok?: boolean;
          reason?: string;
        } | null;
        if (!body?.ok) why = body?.reason ?? "expired";
      }
      const res = await fetch("/api/dash/session").catch(() => null);
      const body = (await res?.json().catch(() => null)) as { identity?: Identity | null } | null;
      if (cancelled) return;
      if (body?.identity) {
        setIdentity(body.identity);
        setState("signed-in");
      } else {
        setReason(why);
        setState("signed-out");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function signOut() {
    await fetch("/api/dash/session", { method: "DELETE" }).catch(() => null);
    setIdentity(null);
    setReason(null);
    setState("signed-out");
  }

  if (state === "signed-in" && identity) {
    return <AuthContext.Provider value={{ identity, signOut }}>{children}</AuthContext.Provider>;
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm rounded-2xl border border-border bg-card p-8 text-center">
        <div className="brand-mark mx-auto">
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              d="M3 19 11 4l4 7-4 8H3Z M13 19l4-8 4 8h-8Z"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinejoin="round"
            />
          </svg>
        </div>
        <h1 className="mt-5 text-xl font-semibold">Adventure Studio · MVP Program</h1>
        {state === "checking" ? (
          <p className="mt-2 text-sm text-muted-foreground">Signing you in…</p>
        ) : (
          <>
            <p className="mt-2 text-sm text-muted-foreground">
              For program mentors and founders. Sign in with the Slack account you use for the
              program.
            </p>
            {reason && MESSAGES[reason] && (
              <p
                role="alert"
                className="mt-4 rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning"
              >
                {MESSAGES[reason]}
              </p>
            )}
            <a
              href="/api/auth/slack"
              className="mt-6 flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-foreground text-sm font-medium text-card hover:opacity-90"
            >
              Sign in with Slack
            </a>
            <p className="mt-4 text-xs text-muted-foreground">
              Or press <span className="font-medium text-foreground">Open dashboard</span> on the
              bot&apos;s Home tab in Slack.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
