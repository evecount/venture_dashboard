# Venture Studio OS: Live Slack & Supabase Setup Guide

This guide walks through deploying the live database and connecting the Slack bot so founder messages in Slack update the Venture Command Center automatically with zero clicking.

---

## 1. Database Setup (Supabase)

1. Open your [Supabase Dashboard](https://supabase.com/dashboard) and create or select your project.
2. Go to the **SQL Editor** in the left sidebar.
3. Open [`supabase/schema.sql`](./schema.sql), paste the entire script into the SQL editor, and click **Run**.
4. This will create:
   - `cohorts`, `startups`, `founders`
   - `deliverables` (pre-seeded with the Mamba syllabus)
   - `submissions` (storing founder status, progress, blockers, digests)
   - `signals` (powering the real-time activity ticker)
   - Realtime publication on `submissions`, `signals`, and `startups`.

---

## 2. Slack App Configuration (api.slack.com)

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and create an app **"From an app manifest"**.
2. Select your venture studio Slack workspace.
3. Use the following manifest:

```json
{
  "display_information": {
    "name": "MVP_buddy",
    "description": "Autonomous technical and venture lead agent"
  },
  "features": {
    "app_home": {
      "home_tab_enabled": true,
      "messages_tab_enabled": true,
      "messages_tab_read_only_enabled": false
    },
    "bot_user": {
      "display_name": "MVP_buddy",
      "always_online": true
    }
  },
  "oauth_config": {
    "scopes": {
      "bot": [
        "chat:write",
        "commands",
        "app_mentions:read",
        "channels:history",
        "groups:history",
        "im:history",
        "mpim:history",
        "files:read",
        "channels:read",
        "groups:read",
        "mpim:read",
        "users:read",
        "users:read.email"
      ]
    }
  },
  "settings": {
    "event_subscriptions": {
      "bot_events": ["app_mention", "message.im", "app_home_opened", "team_join", "member_joined_channel"]
    },
    "socket_mode_enabled": true,
    "interactivity": {
      "is_enabled": true
    }
  }
}
```

4. Under **Basic Information** ➔ **App-Level Tokens**, create a token with `connections:write` scope named `socket-token` (`xapp-...`).
5. Under **Install App**, install the app to your workspace and copy the **Bot User OAuth Token** (`xoxb-...`).

---

## 3. Environment Variables (.env)

Create a `.env` file in the root directory:

```bash
# Slack Tokens
SLACK_BOT_TOKEN="xoxb-your-bot-token"
SLACK_APP_TOKEN="xapp-your-app-level-token"

# Supabase Credentials (from Project Settings -> API)
VITE_SUPABASE_URL="https://your-project.supabase.co"
SUPABASE_SERVICE_ROLE_KEY="your-service-role-key"

# Optional: public dashboard URL, adds "Open dashboard" buttons in Slack
# DASHBOARD_URL="https://your-dashboard.example.com"

# Mentors enter this in the Slack "Set up my profile" form to verify they are mentors
MENTOR_CODE="MENTOR-XXXX-XXXX"

# Optional: founders must enter this code when self-onboarding in Slack
# ONBOARDING_CODE="choose-a-secret"

# AI Inference Key: use GEMINI_API_KEY (default model gemini-3.8-flash, override with AI_MODEL),
# or QWEN_API_KEY for Qwen / DashScope / OpenAI
GEMINI_API_KEY="your-gemini-key"
QWEN_API_KEY="your-dashscope-or-openai-key"
# Optional: Set base URL if using standard OpenAI
# QWEN_BASE_URL="https://api.openai.com/v1"
```

---

## 4. Running the Autonomous Slack Bot

Install Python dependencies:
```bash
pip install -r requirements.txt
pip install apscheduler
```

Run in dry-run simulation mode (no keys needed):
```bash
python slack_bot.py --simulate
```

Run in live Socket Mode:
```bash
python slack_bot.py
```

When founders send a voice note or message to `@MVP_buddy`:
1. The bot resolves their identity and fetches their active deliverable.
2. AI extracts `status`, `progress`, `blocker`, and `digest`.
3. The bot posts a Block Kit confirmation card with `[Confirm & Sync Dashboard]`.
4. Once clicked, the change commits to Supabase and broadcasts via WebSockets to the Command Center in real time.

---

## 5. Founder Onboarding (Invite ➔ Auto-Link)

1. **Pre-register** each founder (and their startup) before sending Slack invites:
   ```sql
   insert into public.founders (id, startup_id, name, email, role)
   values ('founder-sam', 'startup-auvira', 'Sam Tan', 'sam@example.com', 'Founder');
   ```
   Use the **same email** you send the Slack invite to. `slack_user_id` stays empty for now.
2. When they join the workspace or channel, the bot reads their Slack profile email, links the matching founder row, and DMs a welcome. No form needed.
3. **Fallback:** if the email doesn't match (different address, not pre-registered), they get a **Set up my profile** button that opens a modal (name, startup, and the optional `ONBOARDING_CODE`).

Existing projects: run the migration lines noted above the `deliverables` table in `schema.sql`, and re-install the Slack app so the new scopes/events apply.

## 6. App Home Tab

Founders opening the bot see their **sprint radar**: startup, this week's deliverable and due date, their latest confirmed check-in (status, progress, blocker), and an **Open dashboard** button when `DASHBOARD_URL` is set. It refreshes when they open the tab, when they're linked, and after each confirmed check-in. Unregistered users see the **Set up my profile** button instead. Requires the `app_home_opened` event (in the manifest above).
