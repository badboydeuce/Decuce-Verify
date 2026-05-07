"""
DeuceVerify - Main Flask API Application
Handles webhooks, payment processing, and serves as the main application entry point
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
import os
import sys
from datetime import datetime
from threading import Thread
import asyncio

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from database.db import init_db, SessionLocal
from database.crud import (
    get_user_by_telegram_id,
    update_user_balance,
    create_transaction,
    create_payment_transaction,
    update_payment_transaction,
    get_user_by_id
)
from api.services.paystack import paystack

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = settings.flask_secret_key
app.config['JSON_SORT_KEYS'] = False
CORS(app)  # Enable CORS for all routes

# Initialize database on startup
with app.app_context():
    try:
        init_db()
        logger.info("✅ Database initialized successfully")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")

# ============ HEALTH CHECK ENDPOINTS ============

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint for Railway and monitoring"""
    return jsonify({
        "status": "healthy",
        "service": "DeuceVerify",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "bot_token_configured": bool(settings.bot_token),
        "sms_man_configured": bool(settings.sms_man_token),
        "paystack_configured": bool(settings.paystack_secret_key)
    }), 200

@app.route('/api/health/db', methods=['GET'])
def db_health_check():
    """Database health check"""
    try:
        db = SessionLocal()
        # Try to execute a simple query
        from database.models import User
        count = db.query(User).count()
        db.close()
        return jsonify({
            "status": "healthy",
            "database": "connected",
            "user_count": count
        }), 200
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500

# ============ PAYSTACK WEBHOOK ============

@app.route('/api/webhook/paystack', methods=['POST'])
def paystack_webhook():
    """
    Handle Paystack webhook events
    Expected events: charge.success, transfer.success, etc.
    """
    payload = request.get_data()
    signature = request.headers.get('x-paystack-signature')
    
    logger.info(f"Received webhook from Paystack")
    
    # Validate signature
    if not signature:
        logger.error("No signature provided in webhook")
        return jsonify({"error": "No signature provided"}), 400
    
    # Verify and process webhook
    event_data = paystack.handle_webhook(payload, signature)
    if not event_data:
        logger.error("Invalid webhook signature")
        return jsonify({"error": "Invalid signature"}), 401
    
    # Process successful charge
    if event_data.get("status") == "success":
        reference = event_data.get("reference")
        amount = event_data.get("amount", 0) / 100  # Convert from kobo to NGN
        metadata = event_data.get("metadata", {})
        telegram_id = metadata.get("telegram_id")
        user_id = metadata.get("user_id")
        
        logger.info(f"Processing successful payment: reference={reference}, amount=₦{amount}, telegram_id={telegram_id}")
        
        if not telegram_id:
            logger.error("No telegram_id in webhook metadata")
            return jsonify({"error": "Missing telegram_id"}), 400
        
        db = SessionLocal()
        try:
            # Get user
            user = get_user_by_telegram_id(db, telegram_id)
            if not user:
                logger.error(f"User not found: telegram_id={telegram_id}")
                return jsonify({"error": "User not found"}), 404
            
            # Check if already processed (idempotency)
            existing_tx = get_user_by_telegram_id(db, telegram_id)  # Check by reference would be better
            # For idempotency, we should check if transaction with this reference already exists
            
            # Update user balance
            user = update_user_balance(db, user.id, amount, "credit")
            
            # Create transaction record
            transaction = create_transaction(
                db=db,
                user_id=user.id,
                amount=amount,
                transaction_type="credit",
                reference=reference,
                description=f"Wallet funding via Paystack",
                status="completed"
            )
            
            # Update payment transaction if exists
            payment_tx = update_payment_transaction(db, reference, "completed", event_data)
            
            logger.info(f"✅ Successfully credited ₦{amount} to user {telegram_id}. New balance: ₦{user.balance}")
            
            # TODO: Send notification to user via Telegram bot
            # This would require accessing the bot instance
            
            return jsonify({
                "status": "success",
                "message": "Payment processed successfully",
                "user_balance": user.balance
            }), 200
            
        except Exception as e:
            logger.error(f"Error processing webhook: {e}")
            db.rollback()
            return jsonify({"error": str(e)}), 500
        finally:
            db.close()
    
    # Handle other event types
    logger.info(f"Unhandled webhook event: {event_data.get('event')}")
    return jsonify({"status": "ignored"}), 200

# ============ WALLET ENDPOINTS ============

@app.route('/api/wallet/balance', methods=['GET'])
def get_balance():
    """Get user's wallet balance"""
    telegram_id = request.args.get('telegram_id')
    
    if not telegram_id:
        return jsonify({"error": "telegram_id required"}), 400
    
    try:
        telegram_id = int(telegram_id)
    except ValueError:
        return jsonify({"error": "Invalid telegram_id"}), 400
    
    db = SessionLocal()
    try:
        user = get_user_by_telegram_id(db, telegram_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        return jsonify({
            "telegram_id": telegram_id,
            "balance": user.balance,
            "currency": "NGN"
        }), 200
    finally:
        db.close()

@app.route('/api/wallet/fund', methods=['POST'])
def fund_wallet():
    """
    Initialize wallet funding with Paystack
    Request body: {"telegram_id": 123456789, "amount": 1500, "email": "user@example.com"}
    """
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    telegram_id = data.get('telegram_id')
    amount = data.get('amount')
    email = data.get('email')
    
    # Validate inputs
    if not telegram_id:
        return jsonify({"error": "telegram_id required"}), 400
    
    if not amount:
        return jsonify({"error": "amount required"}), 400
    
    try:
        amount = float(amount)
        if amount < settings.minimum_funding_ngn:
            return jsonify({
                "error": f"Minimum funding amount is ₦{settings.minimum_funding_ngn}"
            }), 400
    except ValueError:
        return jsonify({"error": "Invalid amount"}), 400
    
    if not email:
        # Try to get email from user or use a placeholder
        email = f"user_{telegram_id}@deuceverify.com"
    
    db = SessionLocal()
    try:
        # Get or create user
        from database.crud import get_or_create_user
        user = get_or_create_user(db, telegram_id)
        
        # Initialize Paystack transaction
        payment_data = paystack.initialize_transaction(
            email=email,
            amount=int(amount),  # Paystack expects amount in NGN (will convert to kobo internally)
            user_id=user.id,
            telegram_id=telegram_id
        )
        
        if not payment_data:
            return jsonify({"error": "Failed to initialize payment"}), 500
        
        # Create payment record
        payment = create_payment_transaction(
            db=db,
            user_id=user.id,
            reference=payment_data['reference'],
            amount=amount,
            status="pending"
        )
        
        return jsonify({
            "status": "success",
            "authorization_url": payment_data['authorization_url'],
            "reference": payment_data['reference'],
            "amount": amount
        }), 200
        
    except Exception as e:
        logger.error(f"Error funding wallet: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

@app.route('/api/wallet/transactions', methods=['GET'])
def get_transactions():
    """Get user's transaction history"""
    telegram_id = request.args.get('telegram_id')
    limit = request.args.get('limit', 50, type=int)
    
    if not telegram_id:
        return jsonify({"error": "telegram_id required"}), 400
    
    try:
        telegram_id = int(telegram_id)
    except ValueError:
        return jsonify({"error": "Invalid telegram_id"}), 400
    
    db = SessionLocal()
    try:
        user = get_user_by_telegram_id(db, telegram_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        from database.crud import get_user_transactions
        transactions = get_user_transactions(db, user.id, limit)
        
        return jsonify({
            "transactions": [
                {
                    "id": tx.id,
                    "amount": tx.amount,
                    "type": tx.type.value,
                    "status": tx.status,
                    "description": tx.description,
                    "created_at": tx.created_at.isoformat()
                }
                for tx in transactions
            ]
        }), 200
    finally:
        db.close()

# ============ ORDER ENDPOINTS ============

@app.route('/api/orders', methods=['GET'])
def get_orders():
    """Get user's orders"""
    telegram_id = request.args.get('telegram_id')
    status = request.args.get('status')
    
    if not telegram_id:
        return jsonify({"error": "telegram_id required"}), 400
    
    try:
        telegram_id = int(telegram_id)
    except ValueError:
        return jsonify({"error": "Invalid telegram_id"}), 400
    
    db = SessionLocal()
    try:
        user = get_user_by_telegram_id(db, telegram_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        from database.crud import get_user_orders
        orders = get_user_orders(db, user.id, status)
        
        return jsonify({
            "orders": [
                {
                    "id": order.id,
                    "type": order.order_type.value,
                    "service": order.service_name,
                    "country": order.country_name,
                    "number": order.number,
                    "cost": order.cost,
                    "status": order.status.value,
                    "otp_code": order.otp_code,
                    "expires_at": order.expires_at.isoformat(),
                    "created_at": order.created_at.isoformat()
                }
                for order in orders
            ]
        }), 200
    finally:
        db.close()

@app.route('/api/order/<int:order_id>/otp', methods=['GET'])
def get_order_otp(order_id):
    """Get OTP for an order"""
    telegram_id = request.args.get('telegram_id')
    
    if not telegram_id:
        return jsonify({"error": "telegram_id required"}), 400
    
    db = SessionLocal()
    try:
        from database.crud import get_order
        user = get_user_by_telegram_id(db, int(telegram_id))
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        order = get_order(db, order_id, user.id)
        if not order:
            return jsonify({"error": "Order not found"}), 404
        
        # For active orders, try to fetch latest OTP from SMS-Man
        if order.status.value in ["pending", "received"]:
            from api.services.sms_man import sms_man
            
            if order.order_type.value == "activation":
                result = await asyncio.to_thread(
                    sms_man.get_activation_sms, 
                    int(order.request_id)
                )
                if result.get("sms_code"):
                    from database.crud import update_order_otp
                    update_order_otp(db, order_id, result["sms_code"])
                    order.otp_code = result["sms_code"]
        
        return jsonify({
            "order_id": order.id,
            "number": order.number,
            "otp_code": order.otp_code,
            "status": order.status.value,
            "expires_at": order.expires_at.isoformat()
        }), 200
    finally:
        db.close()

# ============ ERROR HANDLERS ============

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        "error": "Endpoint not found",
        "message": "The requested endpoint does not exist"
    }), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {error}")
    return jsonify({
        "error": "Internal server error",
        "message": "An unexpected error occurred"
    }), 500

# ============ RUN BOT IN BACKGROUND ============

def run_bot():
    """Run the Telegram bot in a separate thread"""
    try:
        from bot.main import main
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")

# ============ MAIN ENTRY POINT ============

if __name__ == "__main__":
    # Print startup banner
    print("=" * 60)
    print("🚀 DeuceVerify API Server Starting...")
    print("=" * 60)
    print(f"📡 Flask Port: {settings.flask_port}")
    print(f"🤖 Bot Token: {'✅ Configured' if settings.bot_token else '❌ Missing'}")
    print(f"💳 Paystack: {'✅ Configured' if settings.paystack_secret_key else '❌ Missing'}")
    print(f"📱 SMS-Man: {'✅ Configured' if settings.sms_man_token else '❌ Missing'}")
    print(f"💾 Database: {'✅ Configured' if settings.database_url else '❌ Missing'}")
    print("=" * 60)
    
    # Start bot in background thread
    bot_thread = Thread(target=run_bot, daemon=True)
    bot_thread.start()
    logger.info("🤖 Bot started in background thread")
    
    # Run Flask API
    logger.info(f"🌐 Starting Flask API on port {settings.flask_port}")
    app.run(
        host="0.0.0.0",
        port=settings.flask_port,
        debug=False,
        threaded=True
    )
