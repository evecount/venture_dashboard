import unittest

from dev_controls import DEFAULTS
from dev_home import build_dev_home, build_settings_modal, build_test_modal, mode_switch, result_blocks


def action_ids(block):
    if block["type"] == "actions":
        return [e["action_id"] for e in block["elements"]]
    acc = block.get("accessory")
    return [acc["action_id"]] if acc else []


class DevHomeTest(unittest.TestCase):
    def state(self, n_channels=3, **settings):
        chans = [{"id": f"C{i:04d}", "name": f"chan{i}", "is_private": i == 0, "num_members": 5,
                  "enabled": i == 1, "status": "Reading." if i == 1 else None} for i in range(n_channels)]
        return {"status": "🟢 ok", "settings": {**DEFAULTS, **settings}, "channels": chans,
                "last": {"label": "Status & scopes", "text": "All good"}, "warnings": ["[Agent Error] boom"]}

    def test_valid_slack_view(self):
        blocks = build_dev_home(self.state(n_channels=200))
        self.assertLessEqual(len(blocks), 100)
        for b in blocks:
            ids = action_ids(b)
            self.assertEqual(len(ids), len(set(ids)), b)  # Slack rejects duplicate action_ids in a block
            if b.get("text"):
                self.assertLessEqual(len(b["text"]["text"]), 3000)

    def test_enabled_channels_first_and_toggle_labels(self):
        blocks = build_dev_home(self.state())
        toggles = [b for b in blocks if (b.get("accessory") or {}).get("action_id") == "dev_channel_toggle"]
        self.assertEqual(toggles[0]["accessory"]["value"], "C0001")
        self.assertEqual(toggles[0]["accessory"]["text"]["text"], "Turn off")
        self.assertIn("confirm", toggles[0]["accessory"])
        self.assertEqual(toggles[1]["accessory"]["text"]["text"], "Turn on")

    def test_setting_toggles_reflect_settings(self):
        blocks = build_dev_home(self.state(paused=True))
        paused = next(b for b in blocks if (b.get("accessory") or {}).get("value") == "paused")
        self.assertEqual(paused["accessory"]["text"]["text"], "Turn off")

    def test_mode_switch_highlights_current(self):
        dev = mode_switch("dev")["elements"]
        self.assertEqual([e.get("style") for e in dev], [None, "primary"])

    def test_result_sits_under_tools_and_splits_long_text(self):
        blocks = build_dev_home(self.state())
        tools = next(i for i, b in enumerate(blocks) if b.get("block_id") == "dev_tools")
        self.assertEqual(blocks[tools + 1]["text"]["text"], "*Status & scopes*")
        long = result_blocks({"label": "What the bot sees", "text": "x" * 30000})
        self.assertEqual(len(long), 1 + 8 + 1)  # heading, 8 chunks, "showing the first" note
        self.assertTrue(all(len(b["text"]["text"]) <= 3000 for b in long if b["type"] == "section"))
        working = result_blocks({"label": "Ask", "working": True})
        self.assertIn("Working", working[1]["elements"][0]["text"])

    def test_modals(self):
        m = build_settings_modal({"ai_model": "x", "extra_instructions": ""})
        self.assertEqual(m["blocks"][0]["element"]["initial_value"], "x")
        self.assertNotIn("initial_value", m["blocks"][1]["element"])
        self.assertEqual(build_test_modal()["callback_id"], "modal_dev_test")


if __name__ == "__main__":
    unittest.main()
