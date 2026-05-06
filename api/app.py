from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
from config import settings
from api.services.paystack import paystack
from database.crud import (
    get_user_by_telegram_id, update_balance, create_transaction,
    create_payment_transaction, update_payment_transaction
)
from database.db import SessionLocal
import asyncio
from threading import Thread

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = settings.flask_secret_key
CORS(app)

# Import routes
from api.routes import webhook, wallet, health
app.register_blueprint(webhook.bp)
app.register_blueprint(wallet.bp)
app.register_blueprint(health.bp)

def run_bot():
    """Run the Telegram bot in a separate thread"""
    from bot.main import main
    asyncio.run(main())

if __name__ == "__main__":
    # Start bot in background thread
    bot_thread = Thread(target=run_bot)
    bot_thread.start()
    
    # Run Flask API
    app.run(host="0.0.0.0", port=settings.flask_port)
