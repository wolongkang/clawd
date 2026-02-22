#!/bin/bash
# Run this ONCE on your VPS to set up everything
set -e

echo "=== OpenClaw VPS Setup ==="

# Install system deps
apt update && apt install -y python3 python3-venv python3-pip ffmpeg git

# Clone repo (change URL to your repo)
cd /root
if [ ! -d "videobot" ]; then
    git clone https://github.com/YOUR_USERNAME/videobot.git
fi
cd videobot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Remind about .env
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo ">>> EDIT .env WITH YOUR API KEYS: nano /root/videobot/.env"
    echo ""
fi

# Install systemd service
cp videobot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable videobot
systemctl start videobot

# Install auto-update cron (pulls from GitHub every 60 seconds)
CRON_CMD="* * * * * cd /root/videobot && git pull --ff-only && systemctl restart videobot"
(crontab -l 2>/dev/null | grep -v "videobot"; echo "$CRON_CMD") | crontab -

echo ""
echo "=== DONE ==="
echo "Bot status: systemctl status videobot"
echo "Bot logs:   journalctl -u videobot -f"
echo "Auto-update: every 60s from GitHub"
