import { createFileRoute } from "@tanstack/react-router";
import { admin } from "@/lib/supabase-admin";
import { isMonitored, mapGithubEvent, mergeRepos, verifyGithubSignature } from "@/lib/integrations";

type Integration = { id: string; startup_id: string; repos: string[] | null; selected_repos: string[] | null };
type Staged = { repos: string[] | null };

/* eslint-disable @typescript-eslint/no-explicit-any */
export const Route = createFileRoute("/api/github/webhook")({
  server: {
    handlers: {
      POST: async ({ request }) => {
        const raw = await request.text();
        const ok = await verifyGithubSignature(
          raw,
          request.headers.get("x-hub-signature-256"),
          process.env["GITHUB_WEBHOOK_SECRET"] ?? "",
        );
        if (!ok) return new Response("invalid signature", { status: 401 });

        const event = request.headers.get("x-github-event") ?? "";
        if (event === "ping") return new Response("pong");
        const payload: any = JSON.parse(raw);
        const installationId = String(payload?.installation?.id ?? "");
        if (!installationId) return new Response("ignored", { status: 202 });
        const account: string | undefined = payload.installation?.account?.login;
        const id = encodeURIComponent(installationId);

        const found = await admin<Integration[]>(
          `integrations?select=id,startup_id,repos,selected_repos&provider=eq.github&external_id=eq.${id}`,
        );
        const integration = found.data?.[0];

        // App lifecycle. The founder's browser can return to us after these arrive, so unlinked installs are parked.
        if (event === "installation" || event === "installation_repositories") {
          if (event === "installation" && payload.action === "deleted") {
            await admin(`integrations?provider=eq.github&external_id=eq.${id}`, { method: "DELETE" });
            await admin(`github_installations?installation_id=eq.${id}`, { method: "DELETE" });
            return new Response("removed");
          }
          if (integration) {
            const repos = mergeRepos(integration.repos ?? [], event, payload);
            await admin(`integrations?id=eq.${integration.id}`, { method: "PATCH", body: { repos, ...(account ? { account } : {}) } });
          } else {
            const staged = await admin<Staged[]>(`github_installations?select=repos&installation_id=eq.${id}`);
            const repos = mergeRepos(staged.data?.[0]?.repos ?? [], event, payload);
            await admin("github_installations?on_conflict=installation_id", {
              method: "POST",
              prefer: "resolution=merge-duplicates,return=minimal",
              body: { installation_id: installationId, account: account ?? null, repos, updated_at: new Date().toISOString() },
            });
          }
          return new Response("updated");
        }

        if (!integration) return new Response("installation not linked", { status: 202 });
        if (!isMonitored(integration.selected_repos, payload.repository?.full_name, integration.repos)) {
          return new Response("repository not monitored", { status: 202 });
        }
        const signal = mapGithubEvent(event, payload, integration.startup_id);
        if (!signal) return new Response("ignored", { status: 202 });
        const res = await admin("signals", { method: "POST", body: signal, prefer: "return=minimal" });
        return new Response(res.ok ? "ok" : "store failed", { status: res.ok ? 200 : 500 });
      },
    },
  },
});
