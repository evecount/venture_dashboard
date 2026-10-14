"""
Developer view on the bot's Slack Home tab (Slack only allows Home / Messages / About tabs, so this is a
Mentor view | Developer switch at the top of Home, shown only to developers). Pure block builders.
"""

NL = "\n"
MAX_CHANNELS = 30  # Home views allow 100 blocks


def mode_switch(mode: str) -> dict:
    def btn(text, action, on):
        b = {"type": "button", "text": {"type": "plain_text", "text": text}, "action_id": action}
        return {**b, "style": "primary"} if on else b
    return {"type": "actions", "block_id": "home_mode", "elements": [
        btn("Mentor view", "home_mode_mentor", mode != "dev"), btn("Developer", "home_mode_dev", mode == "dev")]}


def _toggle(label: str, hint: str, on: bool, action: str, value: str, confirm_off: str | None = None) -> dict:
    button = {"type": "button", "text": {"type": "plain_text", "text": "Turn off" if on else "Turn on"},
              "action_id": action, "value": value}
    if not on:
        button["style"] = "primary"
    elif confirm_off:
        button["confirm"] = {"title": {"type": "plain_text", "text": "Are you sure?"},
                             "text": {"type": "mrkdwn", "text": confirm_off},
                             "confirm": {"type": "plain_text", "text": "Turn off"},
                             "deny": {"type": "plain_text", "text": "Cancel"}, "style": "danger"}
    return {"type": "section", "text": {"type": "mrkdwn", "text": f"{'🟢' if on else '⚪'} *{label}*{NL}{hint}"[:3000]},
            "accessory": button}


def build_dev_home(state: dict) -> list:
    """
    state: status (str), settings (dict), channels ([{id,name,is_private,num_members,enabled,status}]),
    last ({label, text} or None), warnings ([str]).
    """
    s, chans = state.get("settings") or {}, state.get("channels") or []
    blocks = [{"type": "header", "text": {"type": "plain_text", "text": "Developer"}}, mode_switch("dev"),
              {"type": "context", "elements": [{"type": "mrkdwn", "text": state.get("status") or "Status unknown"}]}]

    blocks += [{"type": "divider"},
               {"type": "section", "text": {"type": "mrkdwn", "text": (
                   "*Channels the bot reads*" + NL + "Only channels turned on here. The bot keeps their last 7 days and "
                   "forgets older messages; people can only ask about channels they are in. Private channels need "
                   "`/invite @Venture Buddy` first.")},
                "accessory": {"type": "button", "text": {"type": "plain_text", "text": "Refresh list"},
                              "action_id": "dev_refresh_channels"}}]
    if state.get("channels_note"):
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": state["channels_note"][:2000]}]})
    if not chans:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "No channels found yet. Press Refresh list."}]})
    shown = sorted(chans, key=lambda c: (not c.get("enabled"), c.get("name") or ""))[:MAX_CHANNELS]
    for c in shown:
        icon = "🔒" if c.get("is_private") else "#"
        hint = f"{c.get('num_members') or '?'} members" + (f" · {c['status']}" if c.get("status") else "")
        blocks.append(_toggle(f"{icon}{c['name']}", hint, bool(c.get("enabled")), "dev_channel_toggle", c["id"],
                              f"Stop reading #{c['name']} and forget its messages?"))
    if len(chans) > MAX_CHANNELS:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"{len(chans) - MAX_CHANNELS} more channels not shown."}]})

    blocks += [{"type": "divider"}, {"type": "section", "text": {"type": "mrkdwn", "text": "*Behaviour*"}},
               _toggle("Pause the bot", "Everyone except developers gets “back shortly”.", bool(s.get("paused")),
                       "dev_setting_toggle", "paused"),
               _toggle("Daily check-in prompts", "17:00 prompts and 09:30 nudges to founders.", bool(s.get("daily_checkin")),
                       "dev_setting_toggle", "daily_checkin"),
               _toggle("Use channel memory", "Include the last 7 days of readable channels in answers.",
                       bool(s.get("channel_context")), "dev_setting_toggle", "channel_context"),
               {"type": "section", "text": {"type": "mrkdwn", "text": (
                   f"*Model:* `{s.get('ai_model') or 'default'}`{NL}*Extra instructions:* "
                   + (f"_{s['extra_instructions'][:300]}_" if s.get("extra_instructions") else "none"))},
                "accessory": {"type": "button", "text": {"type": "plain_text", "text": "Edit"}, "action_id": "dev_edit_settings"}}]

    blocks += [{"type": "divider"}, {"type": "section", "text": {"type": "mrkdwn", "text": "*Tools*"}},
               {"type": "actions", "block_id": "dev_tools", "elements": [
                   {"type": "button", "text": {"type": "plain_text", "text": "Test as someone"}, "action_id": "dev_test_as"},
                   {"type": "button", "text": {"type": "plain_text", "text": "Status & scopes"}, "action_id": "dev_cmd_status", "value": "status"},
                   {"type": "button", "text": {"type": "plain_text", "text": "What the bot sees"}, "action_id": "dev_cmd_show_context", "value": "show_context"},
                   {"type": "button", "text": {"type": "plain_text", "text": "Preview daily prompts"}, "action_id": "dev_cmd_daily_preview", "value": "daily_preview"},
                   {"type": "button", "text": {"type": "plain_text", "text": "Republish Home tabs"}, "action_id": "dev_cmd_republish_homes", "value": "republish_homes"},
                   {"type": "button", "text": {"type": "plain_text", "text": "Clear my chat memory"}, "action_id": "dev_cmd_clear_history", "value": "clear_history"},
               ]}]
    blocks += result_blocks(state.get("last"))

    warnings = state.get("warnings") or []
    blocks += [{"type": "divider"}, {"type": "section", "text": {"type": "mrkdwn", "text": (
        "*Recent warnings and errors* (Singapore time)" + NL + (f"```{NL.join(warnings)[:2800]}```" if warnings else "None in the last 3 days."))}}]
    return blocks


def result_blocks(last: dict | None, chunk: int = 2900, max_chunks: int = 8) -> list:
    """The latest tool result, in a box right under the Tools buttons (long results split over several blocks)."""
    if not last:
        return []
    text = (last.get("text") or "Done.").strip()
    head = {"type": "section", "text": {"type": "mrkdwn", "text": f"*{last['label']}*"[:3000]},
            "accessory": {"type": "button", "text": {"type": "plain_text", "text": "Clear"}, "action_id": "dev_clear_result"}}
    if last.get("working"):
        return [head, {"type": "context", "elements": [{"type": "mrkdwn", "text": "⏳ Working…"}]}]
    parts = [text[i:i + chunk] for i in range(0, len(text), chunk)]
    blocks = [head] + [{"type": "section", "text": {"type": "mrkdwn", "text": f"```{p}```"}} for p in parts[:max_chunks]]
    if len(parts) > max_chunks:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn",
                       "text": f"Showing the first {chunk * max_chunks:,} of {len(text):,} characters."}]})
    return blocks


def build_settings_modal(settings: dict) -> dict:
    return {"type": "modal", "callback_id": "modal_dev_settings", "title": {"type": "plain_text", "text": "Bot settings"},
            "submit": {"type": "plain_text", "text": "Save"}, "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": [
                {"type": "input", "block_id": "model", "optional": True, "label": {"type": "plain_text", "text": "AI model override"},
                 "hint": {"type": "plain_text", "text": "Leave empty for the default (AI_MODEL)."},
                 "element": {"type": "plain_text_input", "action_id": "v", "max_length": 100,
                             **({"initial_value": settings["ai_model"]} if settings.get("ai_model") else {})}},
                {"type": "input", "block_id": "extra", "optional": True, "label": {"type": "plain_text", "text": "Extra instructions"},
                 "hint": {"type": "plain_text", "text": "Added to the bot's system prompt for every conversation."},
                 "element": {"type": "plain_text_input", "action_id": "v", "multiline": True, "max_length": 3000,
                             **({"initial_value": settings["extra_instructions"]} if settings.get("extra_instructions") else {})}},
            ]}


def build_test_modal() -> dict:
    return {"type": "modal", "callback_id": "modal_dev_test", "title": {"type": "plain_text", "text": "Test as someone"},
            "submit": {"type": "plain_text", "text": "Ask"}, "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": [
                {"type": "context", "elements": [{"type": "mrkdwn", "text": (
                    "The bot answers as if this person had messaged it. The answer appears on your Developer view; nothing is sent to them. "
                    "Actions such as adding tasks are real; confirmation cards are only described.")}]},
                {"type": "input", "block_id": "who", "label": {"type": "plain_text", "text": "Ask as"},
                 "element": {"type": "users_select", "action_id": "v"}},
                {"type": "input", "block_id": "text", "label": {"type": "plain_text", "text": "Message"},
                 "element": {"type": "plain_text_input", "action_id": "v", "multiline": True, "max_length": 3000}},
            ]}
