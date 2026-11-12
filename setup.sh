#!/usr/bin/env bash
# One-shot setup for reel-bot on Debian/Ubuntu. Run as root: bash setup.sh
# Creates its own user and folder; does not touch any other service on the server.
# It asks for the three keys interactively and writes them to a 600-mode .env.
set -euo pipefail

APP_USER=reelbot
APP_DIR=/home/$APP_USER/reel-bot

[ "$(id -u)" -eq 0 ] || { echo "Run as root"; exit 1; }

id "$APP_USER" >/dev/null 2>&1 || adduser --disabled-password --gecos "" "$APP_USER"
apt-get update -y && apt-get install -y ffmpeg python3-venv git

if [ -d "$APP_DIR/.git" ]; then
  sudo -u "$APP_USER" git -C "$APP_DIR" pull --ff-only
else
  sudo -u "$APP_USER" git clone https://github.com/callipegah/reel-bot.git "$APP_DIR"
fi
sudo -u "$APP_USER" mkdir -p "$APP_DIR/data"
sudo -u "$APP_USER" bash -c "cd $APP_DIR && python3 -m venv venv && venv/bin/pip install -q -r requirements.txt"

if [ ! -f "$APP_DIR/.env" ]; then
  echo "Paste the keys (input is hidden)."
  read -rsp "TELEGRAM_BOT_TOKEN: " TG; echo
  read -rsp "GROQ_API_KEY: " GQ; echo
  read -rsp "ANTHROPIC_API_KEY: " AN; echo
  umask 077
  sed -e "s|^TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=$TG|" \
      -e "s|^GROQ_API_KEY=.*|GROQ_API_KEY=$GQ|" \
      -e "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$AN|" \
      "$APP_DIR/.env.example" > "$APP_DIR/.env"
  chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
fi

cp "$APP_DIR/reel-bot.service" /etc/systemd/system/reel-bot.service
systemctl daemon-reload
systemctl enable --now reel-bot
sleep 3
systemctl --no-pager status reel-bot | head -12
echo
echo "Next: send /id to your bot, put the number in $APP_DIR/.env as ALLOWED_USER_ID, then: systemctl restart reel-bot"
