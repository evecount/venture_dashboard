import paramiko
import time
import os
from dotenv import load_dotenv

load_dotenv()

SERVER_IP = "172.104.167.151"
SERVER_USER = "root"
SERVER_PASS = os.environ.get("LINODE_ROOT_PASSWORD", "mamba2026!760356")

print(f"Connecting via SSH to {SERVER_USER}@{SERVER_IP}...")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    ssh.connect(SERVER_IP, username=SERVER_USER, password=SERVER_PASS, timeout=15)
    print("SSH connection established successfully!")
except Exception as e:
    print(f"SSH connection failed: {e}")
    exit(1)

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def run_remote_command(cmd, wait_time=2):
    print(f"\n[REMOTE EXEC]: {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd)
    # Stream output
    exit_status = stdout.channel.recv_exit_status()
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    if out:
        summary_out = out.strip()[-500:] if len(out) > 500 else out.strip()
        print(f"[STDOUT (summary)]:\n{summary_out}")
    if err and exit_status != 0:
        print(f"[STDERR]:\n{err.strip()[-500:]}")
    return exit_status, out

# 1. Update and install prerequisites
run_remote_command("apt-get update -y && apt-get install -y git python3-pip docker.io docker-compose-v2")

# 2. Start and enable Docker
run_remote_command("systemctl start docker && systemctl enable docker")

# 3. Clone or pull repository
run_remote_command("""
if [ -d "/root/venture_dashboard" ]; then
    echo "Updating existing repository..."
    cd /root/venture_dashboard && git fetch origin main && git reset --hard origin/main
else
    echo "Cloning repository..."
    cd /root && git clone https://github.com/evecount/venture_dashboard.git
fi
""")

# 4. Write .env on remote server (unquoted for Docker --env-file)
def clean_env_val(key):
    return (os.environ.get(key) or '').replace('"', '').replace("'", "").strip()

env_content = f"""VITE_SUPABASE_URL={clean_env_val('VITE_SUPABASE_URL')}
VITE_SUPABASE_ANON_KEY={clean_env_val('VITE_SUPABASE_ANON_KEY')}
QWEN_API_KEY={clean_env_val('QWEN_API_KEY')}
SUPABASE_SERVICE_ROLE_KEY={clean_env_val('SUPABASE_SERVICE_ROLE_KEY')}
SLACK_BOT_TOKEN={clean_env_val('SLACK_BOT_TOKEN')}
SLACK_APP_TOKEN={clean_env_val('SLACK_APP_TOKEN')}
"""

sftp = ssh.open_sftp()
with sftp.open("/root/venture_dashboard/.env", "w") as f:
    f.write(env_content)
sftp.close()
print("Remote .env file successfully synchronized!")

# 5. Build and launch Docker container with restart=always
run_remote_command("""
cd /root/venture_dashboard && \
docker build -t mvp-slack-bot . && \
docker stop mvp-slack-bot 2>/dev/null || true && \
docker rm mvp-slack-bot 2>/dev/null || true && \
docker run -d --name mvp-slack-bot --restart always --env-file .env mvp-slack-bot
""")

# 6. Check running containers and logs
time.sleep(3)
run_remote_command("docker ps")
run_remote_command("docker logs --tail 25 mvp-slack-bot")

ssh.close()
print("\n=== DEPLOYMENT COMPLETE! MVP_buddy IS RUNNING 24/7 ON LINODE! ===")
