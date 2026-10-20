import { createFileRoute, Link } from "@tanstack/react-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, Hash, Lock, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import type { DevAction, DevCommand, DevSetting } from "@/lib/dev-actions";

export const Route = createFileRoute("/dev")({
  head: () => ({ meta: [{ title: "Developer · Venture Buddy" }] }),
  component: DevPage,
});

type Channel = {
  id: string;
  name: string;
  is_private: boolean;
  is_member: boolean;
  num_members: number | null;
  enabled: boolean;
  status: string | null;
  backfilled_at: string | null;
};
type Command = {
  id: string;
  command: string;
  args: Record<string, string>;
  status: "queued" | "running" | "done" | "error";
  result: string | null;
  created_at: string;
};
type State = {
  missing: string[];
  heartbeat: { beat_at: string; slack_connected: boolean; scopes?: string | null } | null;
  channels: Channel[];
  settings: Partial<Record<DevSetting, boolean | string>>;
  commands: Command[];
  logs: { id: number; line: string; created_at: string }[];
};

const DEFAULTS: Record<DevSetting, boolean | string> = {
  paused: false,
  daily_checkin: true,
  channel_context: true,
  ai_model: "",
  ai_reasoning: "none",
  fast_model: "",
  extra_instructions: "",
};
const LABELS: Record<string, string> = {
  status: "Status & scopes",
  refresh_channels: "Refresh channel list",
  sync_channel: "Sync channel",
  prune: "Prune old messages",
  ask: "Ask",
  show_context: "What the bot sees",
  post_message: "Post as bot",
  republish_homes: "Republish Home tabs",
  daily_preview: "Preview daily prompts",
  clear_history: "Clear conversation memory",
};

const time = (iso: string) =>
  new Date(iso).toLocaleString("en-SG", { dateStyle: "medium", timeStyle: "short" });

function DevPage() {
  const [state, setState] = useState<State | null>(null);
  const [denied, setDenied] = useState(false);

  const load = useCallback(async () => {
    const res = await fetch("/api/dev/state").catch(() => null);
    if (res?.status === 404) return setDenied(true);
    const body = (await res?.json().catch(() => null)) as (State & { ok: boolean }) | null;
    if (body?.ok) setState(body);
  }, []);

  const busy = state?.commands.some((c) => c.status === "queued" || c.status === "running");
  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), busy ? 2500 : 15000);
    return () => clearInterval(t);
  }, [load, busy]);

  const act = useCallback(
    async (action: DevAction) => {
      await fetch("/api/dev/action", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(action),
      }).catch(() => null);
      await load();
    },
    [load],
  );
  const run = (command: DevCommand, args: Record<string, string> = {}) =>
    act({ type: "command", command, args });

  if (denied)
    return (
      <main className="mx-auto max-w-xl px-4 py-16 text-center">
        <h1 className="text-xl font-semibold">Page not found</h1>
        <Link to="/" className="mt-4 inline-block text-sm underline">
          Back to the dashboard
        </Link>
      </main>
    );
  if (!state)
    return <p className="p-8 text-sm text-muted-foreground">Loading developer tools…</p>;

  const settings = { ...DEFAULTS, ...state.settings };
  const beatAge = state.heartbeat ? (Date.now() - Date.parse(state.heartbeat.beat_at)) / 1000 : null;
  const alive = beatAge !== null && beatAge < 90 && state.heartbeat?.slack_connected;

  return (
    <main className="mx-auto max-w-5xl px-4 py-6 md:px-8">
      <header className="flex flex-wrap items-center gap-3">
        <Link to="/" className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft size={15} /> Dashboard
        </Link>
        <h1 className="text-xl font-semibold">Developer</h1>
        <span
          className={`ml-auto rounded-full px-3 py-1 text-xs font-medium ${alive ? "bg-success-soft text-success" : "bg-warning-soft text-warning"}`}
        >
          {alive
            ? "Bot online"
            : beatAge === null
              ? "No heartbeat yet"
              : `Bot offline · last seen ${time(state.heartbeat!.beat_at)}`}
        </span>
        {settings.paused === true && (
          <span className="rounded-full bg-warning-soft px-3 py-1 text-xs font-medium text-warning">
            Paused
          </span>
        )}
      </header>

      {state.missing.length > 0 && (
        <p role="alert" className="mt-4 rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning">
          Tables missing: {state.missing.join(", ")}. Run{" "}
          <code>supabase/migrations/2026-10-channel-memory-and-dev.sql</code> in the Supabase SQL
          editor, then update the bot on the VM.
        </p>
      )}

      <Tabs defaultValue="channels" className="mt-6">
        <TabsList>
          <TabsTrigger value="channels">Channels</TabsTrigger>
          <TabsTrigger value="console">Test console</TabsTrigger>
          <TabsTrigger value="controls">Controls</TabsTrigger>
          <TabsTrigger value="logs">Logs</TabsTrigger>
        </TabsList>
        <TabsContent value="channels">
          <Channels channels={state.channels} act={act} run={run} />
        </TabsContent>
        <TabsContent value="console">
          <Console run={run} commands={state.commands} />
        </TabsContent>
        <TabsContent value="controls">
          <Controls settings={settings} act={act} run={run} state={state} />
        </TabsContent>
        <TabsContent value="logs">
          <Logs logs={state.logs} />
        </TabsContent>
      </Tabs>
    </main>
  );
}

type Act = (a: DevAction) => Promise<void>;
type Run = (c: DevCommand, args?: Record<string, string>) => Promise<void>;

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="mt-4 rounded-xl border border-border bg-card p-4">
      <h2 className="font-semibold">{title}</h2>
      {hint && <p className="mt-1 text-sm text-muted-foreground">{hint}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

function Channels({ channels, act, run }: { channels: Channel[]; act: Act; run: Run }) {
  const [q, setQ] = useState("");
  const shown = useMemo(
    () =>
      channels
        .filter((c) => c.name.toLowerCase().includes(q.toLowerCase()))
        .sort((a, b) => Number(b.enabled) - Number(a.enabled)),
    [channels, q],
  );
  return (
    <Section
      title="Channels the bot reads"
      hint="The bot only reads channels switched on here, keeps their last 7 days and forgets anything older. People can only ask about channels they are in themselves. Switching a channel off deletes what the bot remembered from it. Private channels need the bot invited first (/invite @Venture Buddy)."
    >
      <div className="flex flex-wrap gap-2">
        <Input
          placeholder="Filter channels"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="max-w-xs"
        />
        <Button variant="outline" onClick={() => void run("refresh_channels")}>
          <RefreshCw /> Refresh channel list
        </Button>
      </div>
      {channels.length === 0 ? (
        <p className="mt-4 text-sm text-muted-foreground">
          No channels yet. Press Refresh channel list (the bot needs the channels:read scope).
        </p>
      ) : (
        <ul className="mt-3 divide-y divide-border">
          {shown.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center gap-3 py-2.5">
              <span className="flex min-w-0 flex-1 items-center gap-1.5">
                {c.is_private ? <Lock size={14} /> : <Hash size={14} />}
                <span className="truncate font-medium">{c.name}</span>
                <span className="text-xs text-muted-foreground">
                  {c.num_members ?? "?"} members{c.is_member ? " · bot is in it" : ""}
                </span>
              </span>
              {c.status && (
                <span className="w-full text-xs text-muted-foreground sm:order-none sm:w-auto sm:max-w-xs sm:truncate" title={c.status}>
                  {c.status}
                </span>
              )}
              {c.enabled && (
                <Button size="sm" variant="ghost" onClick={() => void run("sync_channel", { channel_id: c.id })}>
                  Sync
                </Button>
              )}
              <Switch
                checked={c.enabled}
                aria-label={`Let the bot read #${c.name}`}
                onCheckedChange={(on) => {
                  if (!on && !confirm(`Stop reading #${c.name} and forget its messages?`)) return;
                  void act({ type: "channel", id: c.id, enabled: on });
                }}
              />
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

function CommandLog({ commands, only }: { commands: Command[]; only?: DevCommand[] }) {
  const list = only ? commands.filter((c) => only.includes(c.command as DevCommand)) : commands;
  if (!list.length) return null;
  return (
    <ul className="mt-4 space-y-3">
      {list.slice(0, 8).map((c) => (
        <li key={c.id} className="rounded-lg border border-border p-3 text-sm">
          <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">{LABELS[c.command] ?? c.command}</span>
            <span>{time(c.created_at)}</span>
            <span className={c.status === "error" ? "text-destructive" : ""}>{c.status}</span>
          </div>
          {c.args["text"] && <p className="mt-1 italic text-muted-foreground">“{c.args["text"]}”</p>}
          {c.result && (
            <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap break-words font-sans">
              {c.result}
            </pre>
          )}
          {(c.status === "queued" || c.status === "running") && (
            <p className="mt-1 text-xs text-muted-foreground">Waiting for the bot…</p>
          )}
        </li>
      ))}
    </ul>
  );
}

function Console({ run, commands }: { run: Run; commands: Command[] }) {
  const [text, setText] = useState("");
  const [as, setAs] = useState("");
  const args = as.trim() ? { as_slack_id: as.trim() } : {};
  return (
    <Section
      title="Test console"
      hint="Talk to the bot without Slack. It answers exactly as it would in a DM, using your account (or another person's Slack id to preview what they would get). Actions such as adding tasks are real; check-in, rename and meeting cards are only described."
    >
      <Textarea
        rows={3}
        placeholder="e.g. What did we decide about pricing in #launch this week?"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <div className="mt-2 flex flex-wrap gap-2">
        <Input
          placeholder="Ask as Slack id (optional, e.g. U0123ABC)"
          value={as}
          onChange={(e) => setAs(e.target.value.toUpperCase())}
          className="max-w-xs"
        />
        <Button
          disabled={!text.trim()}
          onClick={() => {
            void run("ask", { ...args, text: text.trim() });
            setText("");
          }}
        >
          Ask
        </Button>
        <Button variant="outline" onClick={() => void run("show_context", args)}>
          What the bot sees
        </Button>
        <Button variant="ghost" onClick={() => void run("clear_history", args)}>
          Clear conversation memory
        </Button>
      </div>
      <CommandLog commands={commands} only={["ask", "show_context", "clear_history"]} />
    </Section>
  );
}

function Controls({ settings, act, run, state }: { settings: Record<DevSetting, boolean | string>; act: Act; run: Run; state: State }) {
  const [model, setModel] = useState(String(settings.ai_model));
  const [fast, setFast] = useState(String(settings.fast_model));
  const [extra, setExtra] = useState(String(settings.extra_instructions));
  const [post, setPost] = useState({ channel: "", text: "" });
  const set = (key: DevSetting, value: boolean | string) => act({ type: "setting", key, value });
  const toggles: [DevSetting, string, string][] = [
    ["paused", "Pause the bot", "Everyone except you gets “back shortly” while you work on it."],
    ["daily_checkin", "Daily check-in prompts", "17:00 prompts and 09:30 nudges to founders."],
    ["channel_context", "Use channel memory", "Include the last 7 days of readable channels in answers."],
  ];
  const postable = state.channels.filter((c) => c.is_member);
  return (
    <>
      <Section title="Behaviour" hint="Changes reach the bot within about 15 seconds. No restart needed.">
        <ul className="space-y-3">
          {toggles.map(([key, label, hint]) => (
            <li key={key} className="flex items-center gap-3">
              <div className="flex-1">
                <p className="text-sm font-medium">{label}</p>
                <p className="text-xs text-muted-foreground">{hint}</p>
              </div>
              <Switch checked={settings[key] === true} onCheckedChange={(on) => void set(key, on)} aria-label={label} />
            </li>
          ))}
        </ul>
        <div className="mt-4 flex flex-wrap items-end gap-2">
          <label className="text-sm">
            <span className="block font-medium">AI model override</span>
            <Input value={model} onChange={(e) => setModel(e.target.value)} placeholder="Default from AI_MODEL" className="mt-1 w-72 max-w-full" />
          </label>
          <Button variant="outline" onClick={() => void set("ai_model", model.trim())}>
            Save
          </Button>
        </div>
        <div className="mt-4 flex flex-wrap items-end gap-2">
          <label className="text-sm">
            <span className="block font-medium">Thinking in chat</span>
            <span className="block text-xs text-muted-foreground">None is fastest. Skills like the digest think a little more on their own.</span>
            <select
              value={String(settings.ai_reasoning)}
              onChange={(e) => void set("ai_reasoning", e.target.value)}
              className="mt-1 h-9 w-72 max-w-full rounded-md border border-input bg-background px-3 text-sm"
              aria-label="Thinking in chat"
            >
              <option value="none">None (fastest)</option>
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High (slowest)</option>
              <option value="">Model default</option>
            </select>
          </label>
        </div>
        <div className="mt-4 flex flex-wrap items-end gap-2">
          <label className="text-sm">
            <span className="block font-medium">Small-talk model</span>
            <span className="block text-xs text-muted-foreground">Used for thanks and greetings. Type <code>off</code> to always use the main model.</span>
            <Input value={fast} onChange={(e) => setFast(e.target.value)} placeholder="Default from AI_FAST_MODEL" className="mt-1 w-72 max-w-full" />
          </label>
          <Button variant="outline" onClick={() => void set("fast_model", fast.trim())}>
            Save
          </Button>
        </div>
        <label className="mt-4 block text-sm">
          <span className="block font-medium">Extra instructions</span>
          <span className="block text-xs text-muted-foreground">Added to the bot's system prompt for every conversation.</span>
          <Textarea rows={4} value={extra} onChange={(e) => setExtra(e.target.value)} className="mt-1" />
        </label>
        <Button variant="outline" className="mt-2" onClick={() => void set("extra_instructions", extra)}>
          Save instructions
        </Button>
      </Section>

      <Section title="Actions">
        <div className="flex flex-wrap gap-2">
          {(["status", "republish_homes", "daily_preview", "prune"] as DevCommand[]).map((c) => (
            <Button key={c} variant="outline" onClick={() => void run(c)}>
              {LABELS[c]}
            </Button>
          ))}
        </div>
        {state.heartbeat?.scopes && (
          <p className="mt-3 break-words text-xs text-muted-foreground">Scopes: {state.heartbeat.scopes}</p>
        )}
        <div className="mt-4 flex flex-wrap gap-2">
          <select
            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            value={post.channel}
            onChange={(e) => setPost({ ...post, channel: e.target.value })}
            aria-label="Channel to post in"
          >
            <option value="">Post as the bot in…</option>
            {postable.map((c) => (
              <option key={c.id} value={c.id}>
                #{c.name}
              </option>
            ))}
          </select>
          <Input value={post.text} onChange={(e) => setPost({ ...post, text: e.target.value })} placeholder="Message" className="min-w-0 flex-1" />
          <Button
            disabled={!post.channel || !post.text.trim()}
            onClick={() => {
              const name = postable.find((c) => c.id === post.channel)?.name;
              if (!confirm(`Post this in #${name} as Venture Buddy?`)) return;
              void run("post_message", { channel_id: post.channel, text: post.text.trim() });
              setPost({ ...post, text: "" });
            }}
          >
            Post
          </Button>
        </div>
        <CommandLog commands={state.commands} only={["status", "republish_homes", "daily_preview", "prune", "post_message", "refresh_channels", "sync_channel"]} />
      </Section>
    </>
  );
}

function Logs({ logs }: { logs: State["logs"] }) {
  const [q, setQ] = useState("");
  const [problems, setProblems] = useState(false);
  const shown = logs.filter(
    (l) =>
      l.line.toLowerCase().includes(q.toLowerCase()) &&
      (!problems || /warning|error|fail|traceback/i.test(l.line)),
  );
  return (
    <Section title="Bot logs" hint="The bot's console output from the last 3 days, newest first.">
      <div className="flex flex-wrap items-center gap-3">
        <Input placeholder="Filter" value={q} onChange={(e) => setQ(e.target.value)} className="max-w-xs" />
        <label className="flex items-center gap-2 text-sm">
          <Switch checked={problems} onCheckedChange={setProblems} /> Warnings and errors only
        </label>
      </div>
      <pre className="mt-3 max-h-[60vh] overflow-auto rounded-lg bg-secondary p-3 text-xs leading-relaxed">
        {shown.map((l) => `${time(l.created_at)}  ${l.line}`).join("\n") || "Nothing yet."}
      </pre>
    </Section>
  );
}
