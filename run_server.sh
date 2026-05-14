#!/usr/bin/env bash
cd "$(dirname "$0")"

if [ ! -f .env ]; then
    echo "Create .env from .env.example and fill in your data"
    exit 1
fi

set -a
source .env 2>/dev/null || true
set +a

PYTHON_BIN="${PYTHON_BIN:-./venv/bin/python}"

echo "Starting bot in background..."
nohup "$PYTHON_BIN" main.py > bot.log 2>&1 &
BOT_PID=$!
echo "Bot PID: $BOT_PID"

sleep 2

echo "Starting web panel..."
nohup "$PYTHON_BIN" api.py >> web.log 2>&1 &
WEB_PID=$!
echo "Web PID: $WEB_PID"

echo ""
echo "Bot and web panel started."
echo "Web: http://SERVER_IP:${WEB_PORT:-5001}"
echo "To stop: kill $BOT_PID $WEB_PID"
