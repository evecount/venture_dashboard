// Developer page actions, validated before anything reaches the database. Shared by the page and /api/dev/action.

/** Commands the bot understands (see DEV_COMMANDS in slack_bot.py). */
export const DEV_COMMANDS = [
  "status",
  "refresh_channels",
  "sync_channel",
  "prune",
  "ask",
  "show_context",
  "post_message",
  "republish_homes",
  "daily_preview",
  "clear_history",
] as const;
export type DevCommand = (typeof DEV_COMMANDS)[number];

/** Bot settings and their types (defaults live in dev_controls.py). */
export const DEV_SETTINGS = {
  paused: "boolean",
  daily_checkin: "boolean",
  channel_context: "boolean",
  ai_model: "string",
  ai_reasoning: "string",
  fast_model: "string",
  extra_instructions: "string",
} as const;
/** How hard the model thinks in chat ("" = the provider's default). Skills can ask for more. */
export const REASONING_LEVELS = ["none", "low", "medium", "high", ""] as const;
export type DevSetting = keyof typeof DEV_SETTINGS;

export type DevAction =
  | { type: "channel"; id: string; enabled: boolean }
  | { type: "setting"; key: DevSetting; value: boolean | string }
  | { type: "command"; command: DevCommand; args: Record<string, string> };

const CHANNEL_ID = /^[CG][A-Z0-9]{2,24}$/;
const SLACK_USER = /^[UW][A-Z0-9]{2,24}$/;
const ARG_RULES: Record<string, (v: string) => boolean> = {
  channel_id: (v) => CHANNEL_ID.test(v),
  as_slack_id: (v) => v === "" || SLACK_USER.test(v),
  text: (v) => v.length <= 4000,
};

export function validDevAction(body: unknown): DevAction | null {
  if (!body || typeof body !== "object") return null;
  const b = body as Record<string, unknown>;
  if (b["type"] === "channel") {
    return typeof b["id"] === "string" && CHANNEL_ID.test(b["id"]) && typeof b["enabled"] === "boolean"
      ? { type: "channel", id: b["id"], enabled: b["enabled"] }
      : null;
  }
  if (b["type"] === "setting") {
    const key = b["key"] as DevSetting;
    const value = b["value"];
    if (!(typeof key === "string" && key in DEV_SETTINGS)) return null;
    if (typeof value !== DEV_SETTINGS[key]) return null;
    if (typeof value === "string" && value.length > (key === "extra_instructions" ? 4000 : 100)) return null;
    if (key === "ai_reasoning" && !(REASONING_LEVELS as readonly string[]).includes(value as string)) return null;
    return { type: "setting", key, value: value as boolean | string };
  }
  if (b["type"] === "command") {
    const command = b["command"] as DevCommand;
    if (!DEV_COMMANDS.includes(command)) return null;
    const raw = (b["args"] ?? {}) as Record<string, unknown>;
    if (typeof raw !== "object" || Array.isArray(raw)) return null;
    const args: Record<string, string> = {};
    for (const [k, v] of Object.entries(raw)) {
      const rule = ARG_RULES[k];
      if (!rule || typeof v !== "string" || !rule(v)) return null;
      args[k] = v;
    }
    return { type: "command", command, args };
  }
  return null;
}
