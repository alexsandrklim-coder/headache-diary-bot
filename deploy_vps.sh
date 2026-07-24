#!/bin/bash
# Oracle Cloud VPS deploy script for headache diary bot
# Run this on the VPS after SSH login

set -e

echo "=== Setting up headache diary bot ==="

# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.11 and pip
sudo apt install -y python3.11 python3.11-venv python3-pip git

# Create bot directory
mkdir -p ~/headache-bot
cd ~/headache-bot

# Clone or copy bot code
# (you'll upload bot.py after SSH)

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install python-telegram-bot python-docx

# Create systemd service for auto-restart
sudo tee /etc/systemd/system/headache-bot.service > /dev/null <<EOF
[Unit]
Description=Headache Diary Telegram Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$HOME/headache-bot
ExecStart=$HOME/headache-bot/venv/bin/python bot.py
Restart=always
RestartSec=10
Environment=TELEGRAM_BOT_TOKEN=8986910594:AAHD-1w4Tc-hnTs9bN0fj2WB4dcfzX91XWM

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable headache-bot
sudo systemctl start headache-bot

echo "=== Bot deployed! ==="
echo "Check status: sudo systemctl status headache-bot"
echo "Check logs: sudo journalctl -u headache-bot -f"
