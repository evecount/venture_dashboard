#!/usr/bin/env bash
# Run once on a fresh Ubuntu/Debian VM, from the folder that holds the unzipped bot files:
#   sudo bash setup.sh
set -euo pipefail
apt-get update -y && apt-get install -y python3 python3-venv
id venturebot >/dev/null 2>&1 || useradd --system --home /opt/venturebot venturebot
mkdir -p /opt/venturebot
cp -r ./* ./.env /opt/venturebot/ 2>/dev/null || cp -r ./* /opt/venturebot/
cd /opt/venturebot
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
chown -R venturebot:venturebot /opt/venturebot
chmod 600 /opt/venturebot/.env /opt/venturebot/*.pem 2>/dev/null || true
cp deploy/venturebot.service /etc/systemd/system/venturebot.service
systemctl daemon-reload
systemctl enable --now venturebot
sleep 5
systemctl --no-pager status venturebot | head -12
echo "Follow the log with: journalctl -u venturebot -f"
