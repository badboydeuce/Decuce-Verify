#!/bin/bash

# Start DeuceVerify - Both Flask API and Telegram Bot

echo "============================================================"
echo "🚀 Starting DeuceVerify"
echo "============================================================"

# Start Flask API in background
echo "📡 Starting Flask API on port 5000..."
python api/app.py &
FLASK_PID=$!

# Wait a bit for Flask to start
sleep 3

# Start Telegram Bot
echo "🤖 Starting Telegram Bot..."
python run_bot.py &
BOT_PID=$!

echo "============================================================"
echo "✅ Both services started!"
echo "📡 Flask API PID: $FLASK_PID"
echo "🤖 Bot PID: $BOT_PID"
echo "============================================================"

# Handle shutdown
function shutdown() {
    echo "🛑 Shutting down..."
    kill $FLASK_PID $BOT_PID 2>/dev/null
    exit 0
}

trap shutdown SIGINT SIGTERM

# Wait for both processes
wait
