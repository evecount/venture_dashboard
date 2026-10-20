import { describe, expect, it } from "vitest";
import { hmacHex, mapGithubEvent, verifyGithubSignature, verifyState } from "@/lib/integrations";

// Produced by the bot's Python signer: sign_state({'f':'founder-x','s':'startup-y','p':'github'}, 'test-secret', now=2000000000)
const PY_STATE =
  "eyJleHAiOjIwMDAwMDM2MDAsImYiOiJmb3VuZGVyLXgiLCJwIjoiZ2l0aHViIiwicyI6InN0YXJ0dXAteSJ9.0d7a1baedeb1b767a158a8299f57abf2e42e1e015139128d1502e6c484ebb93c";

describe("signed connect links", () => {
  it("accepts a state signed by the Python bot", async () => {
    const payload = await verifyState(PY_STATE, "test-secret", 2000000100);
    expect(payload).toMatchObject({ f: "founder-x", s: "startup-y", p: "github" });
  });
  it("rejects a wrong secret, tampering and expiry", async () => {
    expect(await verifyState(PY_STATE, "other-secret", 2000000100)).toBeNull();
    const [body, sig] = PY_STATE.split(".");
    expect(await verifyState(`${body}x.${sig}`, "test-secret", 2000000100)).toBeNull();
    expect(await verifyState(PY_STATE, "test-secret", 2000009999)).toBeNull();
    expect(await verifyState(null, "test-secret")).toBeNull();
  });
});

describe("github webhook", () => {
  it("verifies the signature over the raw body", async () => {
    const body = '{"zen":"hi"}';
    const sig = `sha256=${await hmacHex("whsec", body)}`;
    expect(await verifyGithubSignature(body, sig, "whsec")).toBe(true);
    expect(await verifyGithubSignature(body + " ", sig, "whsec")).toBe(false);
    expect(await verifyGithubSignature(body, null, "whsec")).toBe(false);
    expect(await verifyGithubSignature(body, sig, "")).toBe(false);
  });

  it("maps pushes, merged PRs and closed issues; ignores the rest", () => {
    const repo = { full_name: "acme/app" };
    const push = mapGithubEvent("push", { repository: repo, sender: { login: "ann" }, commits: [{ message: "a" }, { message: "Fix pricing\n\nbody" }] }, "s1");
    expect(push).toMatchObject({ type: "commit", headline: "ann pushed 2 commits to acme/app", detail: "Fix pricing", meta: { commits: 2 } });
    const rich = mapGithubEvent("push", { repository: repo, ref: "refs/heads/main", sender: { login: "ann" }, commits: [
      { message: "Add pricing page\n\nlong body", added: ["src/pages/pricing.tsx"], modified: ["src/app.tsx"] },
      { message: "Fix typo", modified: ["src/app.tsx"], removed: ["old.txt"] }] }, "s1");
    expect(rich?.meta).toMatchObject({ messages: ["Add pricing page", "Fix typo"], files: ["src/pages/pricing.tsx", "src/app.tsx", "old.txt"], branch: "main" });

    const merged = mapGithubEvent("pull_request", { repository: repo, sender: { login: "ann" }, action: "closed", pull_request: { number: 7, title: "Add auth", merged: true } }, "s1");
    expect(merged).toMatchObject({ type: "pull_request", headline: "ann merged PR #7 in acme/app", meta: { merged: true } });

    expect(mapGithubEvent("pull_request", { repository: repo, action: "closed", pull_request: { number: 8, merged: false } }, "s1")).toBeNull();
    expect(mapGithubEvent("push", { repository: repo, deleted: true, commits: [] }, "s1")).toBeNull();
    expect(mapGithubEvent("star", {}, "s1")).toBeNull();
    expect(mapGithubEvent("issues", { repository: repo, sender: { login: "bo" }, action: "closed", issue: { number: 3, title: "Bug" } }, "s1")).toMatchObject({ type: "issue" });
  });
});

import { isMonitored, mergeRepos } from "@/lib/integrations";

describe("repository grants", () => {
  it("tracks the granted repos across install and later changes", () => {
    let repos = mergeRepos([], "installation", { action: "created", repositories: [{ full_name: "a/x" }, { full_name: "a/y" }] });
    expect(repos).toEqual(["a/x", "a/y"]);
    repos = mergeRepos(repos, "installation_repositories", { repositories_added: [{ full_name: "a/z" }], repositories_removed: [{ full_name: "a/x" }] });
    expect(repos).toEqual(["a/y", "a/z"]);
    expect(mergeRepos(repos, "installation", { action: "deleted" })).toEqual(repos);
  });
  it("tracks only chosen repos, or the single granted repo", () => {
    expect(isMonitored(null, "a/x", ["a/x", "a/y"])).toBe(false); // many granted, none chosen yet
    expect(isMonitored([], "a/x", ["a/x", "a/y"])).toBe(false);
    expect(isMonitored(null, "a/x", ["a/x"])).toBe(true); // one granted, nothing to choose
    expect(isMonitored(["a/y"], "a/x", ["a/x", "a/y"])).toBe(false);
    expect(isMonitored(["a/y"], "a/y", ["a/x", "a/y"])).toBe(true);
  });
});

describe("isMonitored with repos removed from the app", () => {
  it("ignores a chosen repo the app no longer has", async () => {
    const { isMonitored } = await import("@/lib/integrations");
    expect(isMonitored(["a/web", "a/gone"], "a/gone", ["a/web", "a/api"])).toBe(false);
    expect(isMonitored(["a/web", "a/gone"], "a/web", ["a/web", "a/api"])).toBe(true);
    expect(isMonitored(["a/gone"], "a/web", ["a/web"])).toBe(true); // falls back to the single shared repo
    expect(isMonitored(["a/x"], "a/x", [])).toBe(true); // repo list not loaded yet
  });
});

describe("signalDedupeId", () => {
  const push = (after: string) => ({ repository: { full_name: "a/web" }, after });
  it("is the same for the same event and different for another", async () => {
    const { signalDedupeId } = await import("@/lib/integrations");
    const a = await signalDedupeId("s1", "push", push("abc123"));
    expect(a).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-5[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    expect(await signalDedupeId("s1", "push", push("abc123"))).toBe(a);
    expect(await signalDedupeId("s1", "push", push("def456"))).not.toBe(a);
    expect(await signalDedupeId("s2", "push", push("abc123"))).not.toBe(a);
  });
  it("identifies pull requests and issues by number and action, and gives up on anything else", async () => {
    const { signalDedupeId } = await import("@/lib/integrations");
    const repo = { full_name: "a/web" };
    const opened = await signalDedupeId("s", "pull_request", { repository: repo, action: "opened", pull_request: { number: 7 } });
    const merged = await signalDedupeId("s", "pull_request", { repository: repo, action: "closed", pull_request: { number: 7 } });
    expect(opened).not.toBe(merged);
    expect(await signalDedupeId("s", "issues", { repository: repo, action: "opened", issue: { number: 3 } })).toBeTruthy();
    expect(await signalDedupeId("s", "star", { repository: repo })).toBeNull();
    expect(await signalDedupeId("s", "push", { repository: repo })).toBeNull(); // no head commit
  });
});
