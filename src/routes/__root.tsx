import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Outlet,
  Link,
  createRootRouteWithContext,
  useRouter,
  HeadContent,
  Scripts,
  type ErrorComponentProps,
} from "@tanstack/react-router";
import { useEffect, useState, type ReactNode } from "react";

// ... [skipping to RootComponent replacement]

function RootComponent() {
  const { queryClient } = Route.useRouteContext();
  const [authed, setAuthed] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem("cybr_auth") === "true";
    }
    return false;
  });
  const [pwd, setPwd] = useState("");

  // "Open dashboard" in Slack carries a signed personal pass (?k=...) that skips the access code.
  useEffect(() => {
    if (authed || typeof window === "undefined") return;
    const url = new URL(window.location.href);
    const pass = url.searchParams.get("k");
    if (!pass) return;
    fetch("/api/dash/claim", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ k: pass }),
    })
      .then((r) => r.json())
      .then((res: { ok?: boolean }) => {
        if (res.ok) {
          localStorage.setItem("cybr_auth", "true");
          setAuthed(true);
        }
      })
      .catch(() => {})
      .finally(() => {
        url.searchParams.delete("k"); // keep the pass out of the address bar and browser history
        window.history.replaceState(null, "", url.toString());
      });
  }, [authed]);

  if (!authed) {
    return (
      <div className="flex h-screen items-center justify-center bg-zinc-950 text-white font-sans">
        <div className="w-[400px] rounded-xl border border-white/10 bg-zinc-900/50 p-8 shadow-2xl backdrop-blur-sm">
          <h2 className="mb-6 text-2xl font-bold tracking-tight text-zinc-100">Prototype Access</h2>
          <input 
            type="password" 
            placeholder="Enter access code..."
            className="w-full rounded-md bg-zinc-950/50 border border-white/10 px-4 py-3 text-white outline-none transition-colors focus:border-white/30"
            value={pwd}
            onChange={(e) => setPwd(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && pwd === "mamba2026") {
                localStorage.setItem("cybr_auth", "true");
                setAuthed(true);
              }
            }}
          />
          <button 
            className="mt-4 w-full rounded-md bg-zinc-100 px-4 py-3 font-medium text-zinc-900 transition-colors hover:bg-white"
            onClick={() => {
              if (pwd === "mamba2026") {
                localStorage.setItem("cybr_auth", "true");
                setAuthed(true);
              }
            }}
          >
            Enter Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <QueryClientProvider client={queryClient}>
      {/* Required: nested routes render here. Removing <Outlet /> breaks all child routes. */}
      <Outlet />
    </QueryClientProvider>
  );
}

import appCss from "../styles.css?url";
import { reportLovableError } from "../lib/lovable-error-reporting";

function NotFoundComponent() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-7xl font-bold text-foreground">404</h1>
        <h2 className="mt-4 text-xl font-semibold text-foreground">Page not found</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <div className="mt-6">
          <Link
            to="/"
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Go home
          </Link>
        </div>
      </div>
    </div>
  );
}

function ErrorComponent({ error, reset }: ErrorComponentProps) {
  console.error(error);
  const router = useRouter();
  useEffect(() => {
    reportLovableError(error, { boundary: "tanstack_root_error_component" });
  }, [error]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-xl font-semibold tracking-tight text-foreground">
          This page didn't load
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Something went wrong on our end. You can try refreshing or head back home.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <button
            onClick={() => {
              router.invalidate();
              reset();
            }}
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Try again
          </button>
          <a
            href="/"
            className="inline-flex items-center justify-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
          >
            Go home
          </a>
        </div>
      </div>
    </div>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "Adventure Studio" },
      { name: "description", content: "The Adventure Studio cohort command center." },
      { property: "og:title", content: "Adventure Studio" },
      { property: "og:description", content: "The Adventure Studio cohort command center." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
    links: [
      {
        rel: "stylesheet",
        href: "https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&display=swap",
      },
      {
        rel: "stylesheet",
        href: appCss,
      },
      { rel: "icon", href: "/favicon.ico", type: "image/x-icon" },
    ],
  }),
  shellComponent: RootShell,
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
  errorComponent: ErrorComponent,
});

function RootShell({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  );
}

