"""
DeuceVerify - Main Flask API Application
This runs ONLY the Flask API - Bot runs separately
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
import os
import sys
from datetime import datetime

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
    get_or_create_user,
    get_user_orders,
    get_order,
    update_order_otp,
    get_user_transactions
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
CORS(app)

# Initialize database tables (but don't start bot!)
with app.app_context():
    try:
        init_db()
        logger.info("✅ Database initialized successfully")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")

# ============ HEALTH CHECK ENDPOINTS ============

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "DeuceVerify API",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "database": "connected"
    }), 200

@app.route('/api/health/db', methods=['GET'])
def db_health_check():
    """Database health check"""
    try:
        db = SessionLocal()
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
    """Handle Paystack webhook events"""
    payload = request.get_data()
    signature = request.headers.get('x-paystack-signature')
    
    logger.info(f"Received webhook from Paystack")
    
    if not signature:
        logger.error("No signature provided")
        return jsonify({"error": "No signature provided"}), 400
    
    event_data = paystack.handle_webhook(payload, signature)
    if not event_data:
        logger.error("Invalid webhook signature")
        return jsonify({"error": "Invalid signature"}), 401
    
    if event_data.get("status") == "success":
        reference = event_data.get("reference")
        amount = event_data.get("amount", 0) / 100
        metadata = event_data.get("metadata", {})
        telegram_id = metadata.get("telegram_id")
        
        if not telegram_id:
            return jsonify({"error": "Missing telegram_id"}), 400
        
        db = SessionLocal()
        try:
            user = get_user_by_telegram_id(db, telegram_id)
            if not user:
                return jsonify({"error": "User not found"}), 404
            
            from database.models import Transaction
            existing_tx = db.query(Transaction).filter(Transaction.reference == reference).first()
            if existing_tx:
                return jsonify({"status": "already_processed"}), 200
            
            user = update_user_balance(db, user.id, amount, "credit")
            create_transaction(
                db=db,
                user_id=user.id,
                amount=amount,
                transaction_type="credit",
                reference=reference,
                description="Wallet funding via Paystack",
                status="completed"
            )
            update_payment_transaction(db, reference, "completed", event_data)
            
            logger.info(f"✅ Credited ₦{amount} to user {telegram_id}")
            
            return jsonify({
                "status": "success",
                "user_balance": user.balance
            }), 200
            
        except Exception as e:
            logger.error(f"Error processing webhook: {e}")
            db.rollback()
            return jsonify({"error": str(e)}), 500
        finally:
            db.close()
    
    return jsonify({"status": "ignored"}), 200

# ============ WALLET ENDPOINTS ============

@app.route('/api/wallet/balance', methods=['GET'])
def get_balance():
    """Get user's wallet balance"""
    telegram_id = request.args.get('telegram_id')
    
    if not telegram_id:
        return jsonify({"error": "telegram_id required"}), 400
    
    db = SessionLocal()
    try:
        user = get_user_by_telegram_id(db, int(telegram_id))
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        return jsonify({
            "balance": user.balance,
            "currency": "NGN"
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

@app.route('/api/wallet/fund', methods=['POST'])
def fund_wallet():
    """Initialize wallet funding"""
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    telegram_id = data.get('telegram_id')
    amount = data.get('amount')
    email = data.get('email', f"user_{telegram_id}@deuceverify.com")
    
    if not telegram_id or not amount:
        return jsonify({"error": "telegram_id and amount required"}), 400
    
    try:
        amount = float(amount)
        if amount < settings.minimum_funding_ngn:
            return jsonify({"error": f"Minimum amount is ₦{settings.minimum_funding_ngn}"}), 400
    except ValueError:
        return jsonify({"error": "Invalid amount"}), 400
    
    db = SessionLocal()
    try:
        user = get_or_create_user(db, telegram_id)
        
        payment_data = paystack.initialize_transaction(
            email=email,
            amount=int(amount),
            user_id=user.id,
            telegram_id=telegram_id
        )
        
        if not payment_data:
            return jsonify({"error": "Payment initialization failed"}), 500
        
        create_payment_transaction(
            db=db,
            user_id=user.id,
            reference=payment_data['reference'],
            amount=amount,
            status="pending"
        )
        
        return jsonify({
            "authorization_url": payment_data['authorization_url'],
            "reference": payment_data['reference']
        }), 200
        
    except Exception as e:
        logger.error(f"Error funding wallet: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

# ============ ORDER ENDPOINTS ============

@app.route('/api/orders', methods=['GET'])
def get_orders():
    """Get user's orders"""
    telegram_id = request.args.get('telegram_id')
    
    if not telegram_id:
        return jsonify({"error": "telegram_id required"}), 400
    
    db = SessionLocal()
    try:
        user = get_user_by_telegram_id(db, int(telegram_id))
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        orders = get_user_orders(db, user.id, limit=50)
        
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
                    "created_at": order.created_at.isoformat()
                }
                for order in orders
            ]
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

# ============ MAIN ENTRY ============

if __name__ == "__main__":
    print("=" * 50)
    print("🚀 DeuceVerify API Server")
    print("=" * 50)
    print(f"Port: {settings.flask_port}")
    print(f"Database: {'✅' if settings.database_url else '❌'}")
    print("=" * 50)
    print("⚠️  Bot runs separately (run_bot.py)")
    print("=" * 50)
    
    app.run(
        host="0.0.0.0",
        port=settings.flask_port,
        debug=False
    )
