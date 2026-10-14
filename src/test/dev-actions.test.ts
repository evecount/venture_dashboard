import { describe, expect, it } from "vitest";
import { validDevAction } from "@/lib/dev-actions";

describe("Developer page actions", () => {
  it("accepts well-formed channel, setting and command actions", () => {
    expect(validDevAction({ type: "channel", id: "C0ABC123", enabled: true })).toEqual({
      type: "channel",
      id: "C0ABC123",
      enabled: true,
    });
    expect(validDevAction({ type: "setting", key: "paused", value: true })).not.toBeNull();
    expect(validDevAction({ type: "setting", key: "ai_model", value: "gemini-3.8-flash" })).not.toBeNull();
    expect(
      validDevAction({ type: "command", command: "ask", args: { text: "hi", as_slack_id: "U0ABC12" } }),
    ).not.toBeNull();
  });

  it("rejects unknown commands, settings, argument names and bad ids", () => {
    expect(validDevAction({ type: "command", command: "drop_tables", args: {} })).toBeNull();
    expect(validDevAction({ type: "command", command: "ask", args: { sql: "x" } })).toBeNull();
    expect(validDevAction({ type: "command", command: "sync_channel", args: { channel_id: "general" } })).toBeNull();
    expect(validDevAction({ type: "setting", key: "SLACK_BOT_TOKEN", value: "x" })).toBeNull();
    expect(validDevAction({ type: "setting", key: "paused", value: "yes" })).toBeNull();
    expect(validDevAction({ type: "channel", id: "C1';--", enabled: true })).toBeNull();
    expect(validDevAction(null)).toBeNull();
  });
});
