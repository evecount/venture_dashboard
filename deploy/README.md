# Running the bot 24/7 on a free VM

The bot only makes outbound connections (Slack Socket Mode, Supabase, GitHub), so it needs no domain, open ports or web server.
Any small Linux VM works. Only run ONE copy at a time: stop the one on your computer once the VM works.

1. Create the VM (Google Cloud e2-micro in us-central1/us-west1/us-east1 is free; Oracle Always Free ARM also works). Ubuntu 22.04+.
2. On your computer, zip the bot (not node_modules, .output or .git):
   - slack_bot.py bot_agent.py bot_memory.py mentor_home.py syllabus.py integrations.py github_app.py daily_checkin.py profile_rules.py
   - requirements.txt, .env, your *.pem GitHub key, deploy/, and src/data/syllabus.json (keep that folder path)
3. Copy it up and unzip, e.g. `scp venturebot.zip user@VM_IP:~` then `unzip venturebot.zip -d venturebot && cd venturebot`.
4. `sudo bash deploy/setup.sh` (installs Python, creates a locked-down service user, starts the bot on boot, restarts it if it crashes).
5. Check it: `journalctl -u venturebot -f` should show "Bolt app is running!".
6. Update later: copy the new files over /opt/venturebot and `sudo systemctl restart venturebot`.
