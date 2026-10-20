// Server-side helpers for the work-signal integrations (GitHub webhooks, signed connect links).
// Pure functions on top of WebCrypto so they run on Cloudflare Workers and in tests.

const enc = new TextEncoder();

export async function hmacHex(secret: string, data: string): Promise<string> {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(data));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Constant-time string comparison. */
export function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export type StatePayload = { f: string; s: string; p: string; exp: number };

/** Verifies a `state` made by the bot (integrations.py sign_state). Returns null if forged, malformed or expired. */
export async function verifyState(state: string | null, secret: string, nowSeconds = Date.now() / 1000): Promise<StatePayload | null> {
  if (!state || !secret) return null;
  const [body, sig] = state.split(".");
  if (!body || !sig) return null;
  if (!safeEqual(await hmacHex(secret, body), sig)) return null;
  try {
    const json = atob(body.replace(/-/g, "+").replace(/_/g, "/"));
    const payload = JSON.parse(json) as StatePayload;
    return payload.exp > nowSeconds && payload.f && payload.s ? payload : null;
  } catch {
    return null;
  }
}

/** GitHub sends `X-Hub-Signature-256: sha256=<hex>` computed over the raw request body. */
export async function verifyGithubSignature(rawBody: string, header: string | null, secret: string): Promise<boolean> {
  if (!header || !secret || !header.startsWith("sha256=")) return false;
  return safeEqual(await hmacHex(secret, rawBody), header.slice("sha256=".length));
}

export type SignalInsert = {
  startup_id: string;
  type: "commit" | "pull_request" | "issue";
  headline: string;
  detail: string;
  stream: string;
  actor: string;
  meta: Record<string, unknown>;
};

const clip = (text: string, n = 140) => (text.length > n ? `${text.slice(0, n - 1)}…` : text);

/* eslint-disable @typescript-eslint/no-explicit-any */
/** Turns a GitHub webhook into one activity signal, or null for events we don't track. */
export function mapGithubEvent(event: string, payload: any, startupId: string): SignalInsert | null {
  const repo: string = payload?.repository?.full_name ?? "a repository";
  const actor: string = payload?.sender?.login ?? payload?.pusher?.name ?? "someone";

  if (event === "push") {
    const commits: any[] = payload.commits ?? [];
    if (payload.deleted || !commits.length) return null;
    const n = commits.length;
    // Every commit's first line and the files it touched: the evidence the bot's progress estimates and
    // "what changed?" answers read (paths like src/pages/pricing.tsx say which goal moved).
    const messages = commits.map((c) => clip(String(c?.message ?? "").split("\n")[0] ?? "", 120)).filter(Boolean).slice(-15);
    const files = [...new Set(commits.flatMap((c) => [...(c?.added ?? []), ...(c?.modified ?? []), ...(c?.removed ?? [])]))]
      .filter((f): f is string => typeof f === "string").slice(0, 40);
    return {
      startup_id: startupId, type: "commit", stream: "Tech", actor,
      headline: `${actor} pushed ${n} commit${n === 1 ? "" : "s"} to ${repo}`,
      detail: clip(String(commits[commits.length - 1]?.message ?? "").split("\n")[0] ?? ""),
      meta: { commits: n, repo, messages, files, branch: String(payload.ref ?? "").replace("refs/heads/", "") || undefined },
    };
  }
  if (event === "pull_request") {
    const pr = payload.pull_request;
    const action: string = payload.action;
    if (!pr || !["opened", "closed", "reopened"].includes(action)) return null;
    const merged = action === "closed" && pr.merged === true;
    if (action === "closed" && !merged) return null; // closed without merging isn't progress
    return {
      startup_id: startupId, type: "pull_request", stream: "Tech", actor,
      headline: `${actor} ${merged ? "merged" : action} PR #${pr.number} in ${repo}`,
      detail: clip(String(pr.title ?? "")),
      meta: {
        action, merged, repo, number: pr.number,
        body: clip(String(pr.body ?? "").replace(/\s+/g, " ").trim(), 400) || undefined,
        changed_files: typeof pr.changed_files === "number" ? pr.changed_files : undefined,
        additions: typeof pr.additions === "number" ? pr.additions : undefined,
        deletions: typeof pr.deletions === "number" ? pr.deletions : undefined,
      },
    };
  }
  if (event === "issues") {
    const action: string = payload.action;
    if (!["opened", "closed"].includes(action) || !payload.issue) return null;
    return {
      startup_id: startupId, type: "issue", stream: "Tech", actor,
      headline: `${actor} ${action} issue #${payload.issue.number} in ${repo}`,
      detail: clip(String(payload.issue.title ?? "")),
      meta: { action, repo, number: payload.issue.number },
    };
  }
  return null;
}

/* eslint-disable @typescript-eslint/no-explicit-any */
/** Repositories the installation currently grants, after applying an `installation` / `installation_repositories` event. */
export function mergeRepos(current: string[], event: string, payload: any): string[] {
  const names = (list: any[] | undefined) => (list ?? []).map((r) => String(r.full_name)).filter(Boolean);
  if (event === "installation") return payload.action === "created" || payload.action === "unsuspend" ? names(payload.repositories) : current;
  if (event === "installation_repositories") {
    const removed = new Set(names(payload.repositories_removed));
    return [...new Set([...current, ...names(payload.repositories_added)])].filter((r) => !removed.has(r));
  }
  return current;
}

/** Should a repository's activity count? Only repos the founder chose (a lone granted repo needs no choosing). */
export function isMonitored(
  selected: string[] | null | undefined,
  repoFullName: string | undefined,
  granted: string[] | null | undefined = [],
): boolean {
  const chosen = granted?.length ? (selected ?? []).filter((r) => granted.includes(r)) : (selected ?? []);
  const effective = chosen.length ? chosen : granted?.length === 1 ? granted : [];
  return !!repoFullName && effective.includes(repoFullName);
}
