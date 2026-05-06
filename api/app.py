"""
DeuceVerify Flask API
Handles payment webhooks, user management, and order processing
"""


import sys
import os

# Add the project root to Python path so 'models' can be found
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import hmac
import hashlib
import json
import requests
from datetime import datetime
from loguru import logger

# Load environment variables
load_dotenv()

# Rest of your app code...

# ==================== CREATE FLASK APP ====================

app = Flask(__name__)
CORS(app)

# Configuration
app.config['SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['PAYSTACK_SECRET_KEY'] = os.getenv('PAYSTACK_SECRET_KEY')
app.config['PAYSTACK_PUBLIC_KEY'] = os.getenv('PAYSTACK_PUBLIC_KEY')
app.config['COINBASE_API_KEY'] = os.getenv('COINBASE_API_KEY')
app.config['COINBASE_WEBHOOK_SECRET'] = os.getenv('COINBASE_WEBHOOK_SECRET')
app.config['TG_WALLET_TOKEN'] = os.getenv('TG_WALLET_TOKEN')
app.config['ENV'] = os.getenv('APP_ENV', 'development')
app.config['DEBUG'] = os.getenv('DEBUG', 'False').lower() == 'true'

# Paystack IP whitelist (optional security)
PAYSTACK_IPS = [
    '52.31.139.75',
    '52.49.173.169',
    '52.214.14.220'
]

# ==================== DATABASE SETUP ====================

from models.database import DatabaseManager, User, Transaction, TransactionType, TransactionStatus, Order, OrderStatus

# Initialize database manager
db_manager = DatabaseManager(os.getenv('DATABASE_URL'))

# Create tables on startup if they don't exist
try:
    db_manager.create_tables()
    logger.info("Database tables verified/created successfully")
except Exception as e:
    logger.error(f"Database initialization error: {e}")

# ==================== HELPER FUNCTIONS ====================

def verify_paystack_signature(payload: bytes, signature: str) -> bool:
    """Verify Paystack webhook signature"""
    if not signature or not app.config['PAYSTACK_SECRET_KEY']:
        return False
    
    expected = hmac.new(
        app.config['PAYSTACK_SECRET_KEY'].encode('utf-8'),
        payload,
        hashlib.sha512
    ).hexdigest()
    
    return hmac.compare_digest(expected, signature)

def verify_coinbase_signature(payload: bytes, signature: str) -> bool:
    """Verify Coinbase Commerce webhook signature"""
    if not signature or not app.config['COINBASE_WEBHOOK_SECRET']:
        return False
    
    expected = hmac.new(
        app.config['COINBASE_WEBHOOK_SECRET'].encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected, signature)

def send_telegram_notification(telegram_id: int, message: str):
    """Send notification to Telegram user"""
    try:
        bot_token = os.getenv('BOT_TOKEN')
        if not bot_token:
            logger.warning("BOT_TOKEN not configured for notifications")
            return
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": telegram_id,
            "text": message,
            "parse_mode": "HTML"
        }
        
        # Send async (don't wait for response)
        import threading
        threading.Thread(target=lambda: requests.post(url, json=payload, timeout=5)).start()
        
    except Exception as e:
        logger.error(f"Failed to send Telegram notification: {e}")

def convert_ngn_to_usd(amount_ngn: float) -> float:
    """Convert NGN to USD (1 USD = 1500 NGN approx)"""
    return amount_ngn / 1500

def convert_usd_to_ngn(amount_usd: float) -> float:
    """Convert USD to NGN"""
    return amount_usd * 1500

# ==================== HEALTH CHECK ENDPOINTS ====================

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Railway"""
    return jsonify({
        "status": "healthy",
        "service": "DeuceVerify API",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "environment": app.config['ENV']
    })

@app.route('/', methods=['GET'])
def root():
    """Root endpoint with API info"""
    return jsonify({
        "service": "DeuceVerify API",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "user_balance": "/api/balance/<telegram_id>",
            "transaction_history": "/api/transactions/<telegram_id>",
            "create_payment": "/api/create-payment",
            "webhooks": {
                "paystack": "/webhook/paystack",
                "coinbase": "/webhook/coinbase",
                "telegram_wallet": "/webhook/telegram-wallet",
                "status": "/webhook/status"
            }
        }
    })

# ==================== USER API ENDPOINTS ====================

@app.route('/api/balance/<int:telegram_id>', methods=['GET'])
def get_balance(telegram_id):
    """Get user balance"""
    session = db_manager.get_session()
    try:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if user:
            return jsonify({
                "success": True,
                "balance": user.balance,
                "total_spent": user.total_spent,
                "total_orders": user.total_orders,
                "currency": "USD"
            })
        return jsonify({"success": False, "error": "User not found"}), 404
    except Exception as e:
        logger.error(f"Error getting balance: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        session.close()

@app.route('/api/transactions/<int:telegram_id>', methods=['GET'])
def get_transactions(telegram_id):
    """Get user transaction history"""
    session = db_manager.get_session()
    try:
        limit = request.args.get('limit', 50, type=int)
        transactions = session.query(Transaction).filter_by(
            user_id=telegram_id
        ).order_by(Transaction.created_at.desc()).limit(limit).all()
        
        return jsonify({
            "success": True,
            "transactions": [
                {
                    "id": t.id,
                    "amount": t.amount,
                    "type": t.type.value,
                    "status": t.status.value,
                    "payment_method": t.payment_method,
                    "description": t.description,
                    "created_at": t.created_at.isoformat()
                }
                for t in transactions
            ]
        })
    except Exception as e:
        logger.error(f"Error getting transactions: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        session.close()

@app.route('/api/user/create', methods=['POST'])
def create_user():
    """Create or get existing user"""
    session = db_manager.get_session()
    try:
        data = request.json
        telegram_id = data.get('telegram_id')
        username = data.get('username')
        first_name = data.get('first_name')
        last_name = data.get('last_name')
        
        if not telegram_id:
            return jsonify({"success": False, "error": "telegram_id required"}), 400
        
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        
        if not user:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                balance=0.0,
                total_spent=0.0,
                total_orders=0,
                created_at=datetime.utcnow()
            )
            session.add(user)
            session.commit()
            logger.info(f"Created new user: {telegram_id} ({username})")
        
        return jsonify({
            "success": True,
            "user": {
                "telegram_id": user.telegram_id,
                "username": user.username,
                "balance": user.balance,
                "total_spent": user.total_spent,
                "created_at": user.created_at.isoformat()
            }
        })
    except Exception as e:
        session.rollback()
        logger.error(f"Error creating user: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        session.close()

# ==================== PAYMENT INITIALIZATION ====================

@app.route('/api/create-payment', methods=['POST'])
def create_payment():
    """Initialize Paystack payment"""
    session = db_manager.get_session()
    
    try:
        data = request.json
        telegram_id = data.get('telegram_id')
        email = data.get('email', f"user{telegram_id}@deuceverify.com")
        amount_ngn = data.get('amount', 1000)  # Default 1000 NGN
        
        # Validate amount
        if amount_ngn < 500:
            return jsonify({"error": "Minimum amount is 500 NGN"}), 400
        if amount_ngn > 500000:
            return jsonify({"error": "Maximum amount is 500,000 NGN"}), 400
        
        # Create unique reference
        reference = f"DV_{telegram_id}_{int(datetime.utcnow().timestamp())}"
        
        # Create transaction record
        usd_amount = convert_ngn_to_usd(amount_ngn)
        
        transaction = Transaction(
            user_id=telegram_id,
            amount=usd_amount,
            type=TransactionType.CREDIT,
            status=TransactionStatus.PENDING,
            payment_method="paystack",
            payment_reference=reference,
            description=f"Wallet funding - ₦{amount_ngn:,.2f} NGN"
        )
        session.add(transaction)
        session.commit()
        
        # Initialize Paystack transaction
        headers = {
            "Authorization": f"Bearer {app.config['PAYSTACK_SECRET_KEY']}",
            "Content-Type": "application/json"
        }
        
        callback_url = os.getenv('PAYSTACK_CALLBACK_URL', 'https://deuceverify.com/deposit')
        
        payload = {
            "email": email,
            "amount": amount_ngn * 100,  # Convert to kobo
            "currency": "NGN",
            "reference": reference,
            "callback_url": callback_url,
            "metadata": {
                "telegram_id": telegram_id,
                "purpose": "wallet_funding",
                "amount_usd": usd_amount
            }
        }
        
        response = requests.post(
            "https://api.paystack.co/transaction/initialize",
            json=payload,
            headers=headers,
            timeout=30
        )
        
        result = response.json()
        
        if result.get('status'):
            return jsonify({
                "success": True,
                "authorization_url": result['data']['authorization_url'],
                "reference": reference,
                "amount_ngn": amount_ngn,
                "amount_usd": usd_amount
            })
        else:
            # Mark transaction as failed
            transaction.status = TransactionStatus.FAILED
            session.commit()
            
            return jsonify({
                "success": False,
                "error": result.get('message', 'Payment initialization failed')
            }), 500
            
    except Exception as e:
        session.rollback()
        logger.error(f"Payment creation error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()

@app.route('/api/verify-payment/<reference>', methods=['GET'])
def verify_payment(reference):
    """Verify payment status with Paystack"""
    headers = {
        "Authorization": f"Bearer {app.config['PAYSTACK_SECRET_KEY']}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(
            f"https://api.paystack.co/transaction/verify/{reference}",
            headers=headers,
            timeout=30
        )
        
        result = response.json()
        
        if result.get('status') and result['data']['status'] == 'success':
            amount = result['data']['amount'] / 100
            metadata = result['data'].get('metadata', {})
            telegram_id = metadata.get('telegram_id')
            
            # Update database
            session = db_manager.get_session()
            try:
                transaction = session.query(Transaction).filter_by(
                    payment_reference=reference
                ).first()
                
                if transaction and transaction.status == TransactionStatus.PENDING:
                    transaction.status = TransactionStatus.COMPLETED
                    transaction.completed_at = datetime.utcnow()
                    
                    user = session.query(User).filter_by(telegram_id=telegram_id).first()
                    if user:
                        usd_amount = convert_ngn_to_usd(amount)
                        user.balance += usd_amount
                        session.commit()
                        
                        return jsonify({
                            "success": True,
                            "verified": True,
                            "amount": amount,
                            "new_balance": user.balance
                        })
                
                return jsonify({
                    "success": True,
                    "verified": False,
                    "message": "Transaction already processed or not found"
                })
            finally:
                session.close()
        
        return jsonify({
            "success": True,
            "verified": False,
            "status": result['data']['status'] if result.get('data') else 'unknown'
        })
        
    except Exception as e:
        logger.error(f"Payment verification error: {e}")
        return jsonify({"error": str(e)}), 500

# ==================== PAYSTACK WEBHOOK ====================

@app.route('/webhook/paystack', methods=['POST'])
def paystack_webhook():
    """
    Handle Paystack webhook events
    Documentation: https://paystack.com/docs/webhooks
    """
    
    # Get signature from headers
    signature = request.headers.get('x-paystack-signature')
    
    if not signature:
        logger.warning("Paystack webhook: No signature header")
        return jsonify({"error": "No signature"}), 401
    
    # Get raw payload
    payload = request.get_data(as_text=True)
    
    # Verify signature
    if not verify_paystack_signature(payload.encode('utf-8'), signature):
        logger.error("Paystack webhook: Invalid signature")
        return jsonify({"error": "Invalid signature"}), 401
    
    # Parse event
    event = request.json
    event_type = event.get('event')
    data = event.get('data')
    
    logger.info(f"Paystack webhook received: {event_type}")
    
    # Route to appropriate handler
    if event_type == 'charge.success':
        return handle_charge_success(data)
    elif event_type == 'transfer.success':
        return handle_transfer_success(data)
    elif event_type == 'transfer.failed':
        return handle_transfer_failed(data)
    elif event_type == 'refund.processed':
        return handle_refund_processed(data)
    elif event_type == 'charge.dispute.create':
        return handle_dispute_created(data)
    else:
        logger.info(f"Unhandled Paystack event: {event_type}")
        return jsonify({"status": "ignored"}), 200

def handle_charge_success(data):
    """Handle successful charge webhook"""
    session = db_manager.get_session()
    
    try:
        reference = data.get('reference')
        amount_ngn = data.get('amount', 0) / 100  # Convert from kobo
        currency = data.get('currency', 'NGN')
        metadata = data.get('metadata', {})
        customer = data.get('customer', {})
        
        telegram_id = metadata.get('telegram_id')
        email = customer.get('email')
        
        logger.info(f"Processing charge.success: {reference} - ₦{amount_ngn} - User: {telegram_id}")
        
        if not telegram_id:
            logger.error(f"No telegram_id in metadata for reference: {reference}")
            return jsonify({"status": "error", "message": "No user ID"}), 200
        
        # Find transaction
        transaction = session.query(Transaction).filter_by(
            payment_reference=reference
        ).first()
        
        # Convert NGN to USD
        usd_amount = convert_ngn_to_usd(amount_ngn)
        
        if not transaction:
            # Create new transaction
            transaction = Transaction(
                user_id=telegram_id,
                amount=usd_amount,
                type=TransactionType.CREDIT,
                status=TransactionStatus.COMPLETED,
                payment_method="paystack",
                payment_reference=reference,
                description=f"Wallet funding - ₦{amount_ngn:,.2f} NGN"
            )
            session.add(transaction)
            logger.info(f"Created new transaction: {reference}")
        else:
            # Update existing transaction
            transaction.status = TransactionStatus.COMPLETED
            transaction.completed_at = datetime.utcnow()
            logger.info(f"Updated transaction: {reference}")
        
        # Update user balance
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if user:
            user.balance += usd_amount
            session.commit()
            logger.info(f"Updated user {telegram_id} balance: +${usd_amount:.2f} (New: ${user.balance:.2f})")
            
            # Send notification to user
            notification = (
                f"✅ <b>Payment Received!</b>\n\n"
                f"Amount: <b>₦{amount_ngn:,.2f}</b> (${usd_amount:.2f})\n"
                f"New balance: <b>${user.balance:.2f}</b>\n\n"
                f"Thank you for funding your wallet! 🎉"
            )
            send_telegram_notification(telegram_id, notification)
        else:
            logger.error(f"User not found: {telegram_id}")
            return jsonify({"status": "error", "message": "User not found"}), 200
        
        return jsonify({"status": "success", "message": "Balance updated"}), 200
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error processing charge.success: {e}")
        return jsonify({"status": "error", "message": str(e)}), 200
    finally:
        session.close()

def handle_transfer_success(data):
    """Handle successful transfer (refund) webhook"""
    session = db_manager.get_session()
    
    try:
        reference = data.get('reference')
        amount = data.get('amount', 0) / 100
        recipient = data.get('recipient', {})
        
        logger.info(f"Transfer success: {reference} - ₦{amount}")
        
        transaction = session.query(Transaction).filter_by(
            payment_reference=reference
        ).first()
        
        if transaction:
            transaction.status = TransactionStatus.COMPLETED
            transaction.completed_at = datetime.utcnow()
            session.commit()
            logger.info(f"Refund transaction completed: {reference}")
            
            # Notify user
            if transaction.user_id:
                notification = (
                    f"🔄 <b>Refund Processed</b>\n\n"
                    f"Amount: <b>${transaction.amount:.2f}</b>\n"
                    f"Reference: <code>{reference}</code>\n\n"
                    f"The refund has been credited to your wallet."
                )
                send_telegram_notification(transaction.user_id, notification)
        
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error processing transfer.success: {e}")
        return jsonify({"status": "error"}), 200
    finally:
        session.close()

def handle_transfer_failed(data):
    """Handle failed transfer webhook"""
    reference = data.get('reference')
    reason = data.get('reason', 'Unknown')
    
    logger.error(f"Transfer failed: {reference} - Reason: {reason}")
    
    session = db_manager.get_session()
    
    try:
        transaction = session.query(Transaction).filter_by(
            payment_reference=reference
        ).first()
        
        if transaction:
            transaction.status = TransactionStatus.FAILED
            session.commit()
            logger.info(f"Marked transaction as failed: {reference}")
            
            # Notify user
            if transaction.user_id:
                notification = (
                    f"❌ <b>Refund Failed</b>\n\n"
                    f"Amount: <b>${transaction.amount:.2f}</b>\n"
                    f"Reason: {reason}\n\n"
                    f"Please contact support for assistance."
                )
                send_telegram_notification(transaction.user_id, notification)
            
    except Exception as e:
        logger.error(f"Error updating failed transaction: {e}")
    finally:
        session.close()
    
    return jsonify({"status": "received"}), 200

def handle_refund_processed(data):
    """Handle refund processed webhook"""
    reference = data.get('reference')
    amount = data.get('amount', 0) / 100
    
    logger.info(f"Refund processed: {reference} - ₦{amount}")
    
    session = db_manager.get_session()
    
    try:
        transaction = session.query(Transaction).filter_by(
            payment_reference=reference
        ).first()
        
        if transaction and transaction.order_id:
            order = session.query(Order).filter_by(id=transaction.order_id).first()
            if order:
                order.status = OrderStatus.REFUNDED if hasattr(OrderStatus, 'REFUNDED') else "refunded"
                session.commit()
                logger.info(f"Order {transaction.order_id} marked as refunded")
                
    except Exception as e:
        logger.error(f"Error updating refund status: {e}")
    finally:
        session.close()
    
    return jsonify({"status": "success"}), 200

def handle_dispute_created(data):
    """Handle dispute created webhook"""
    transaction_id = data.get('transaction', {}).get('id')
    amount = data.get('transaction', {}).get('amount', 0) / 100
    
    logger.warning(f"Dispute created for transaction: {transaction_id} - Amount: ₦{amount}")
    
    # Notify admin
    admin_ids = os.getenv('ADMIN_IDS', '').split(',')
    for admin_id in admin_ids:
        if admin_id.strip():
            notification = (
                f"⚠️ <b>Dispute Alert</b>\n\n"
                f"Transaction: {transaction_id}\n"
                f"Amount: ₦{amount:,.2f}\n"
                f"Please check Paystack dashboard."
            )
            send_telegram_notification(int(admin_id), notification)
    
    return jsonify({"status": "received"}), 200

# ==================== COINBASE (CRYPTO) WEBHOOK ====================

@app.route('/webhook/coinbase', methods=['POST'])
def coinbase_webhook():
    """
    Handle Coinbase Commerce webhook for crypto payments
    Documentation: https://docs.cloud.coinbase.com/commerce/docs/webhooks
    """
    
    # Get signature header
    signature = request.headers.get('X-CC-Webhook-Signature')
    
    if not signature:
        logger.warning("Coinbase webhook: No signature header")
        return jsonify({"error": "No signature"}), 401
    
    # Get raw payload
    payload = request.get_data(as_text=True)
    
    # Verify signature
    if not verify_coinbase_signature(payload.encode('utf-8'), signature):
        logger.error("Coinbase webhook: Invalid signature")
        return jsonify({"error": "Invalid signature"}), 401
    
    # Parse event
    event = request.json
    event_type = event.get('event', {}).get('type')
    data = event.get('event', {}).get('data', {})
    
    logger.info(f"Coinbase webhook received: {event_type}")
    
    if event_type == 'charge:confirmed':
        return handle_crypto_payment_confirmed(data)
    elif event_type == 'charge:failed':
        return handle_crypto_payment_failed(data)
    elif event_type == 'charge:pending':
        return handle_crypto_payment_pending(data)
    else:
        logger.info(f"Unhandled Coinbase event: {event_type}")
        return jsonify({"status": "ignored"}), 200

def handle_crypto_payment_confirmed(data):
    """Handle confirmed crypto payment"""
    session = db_manager.get_session()
    
    try:
        charge_code = data.get('code')
        metadata = data.get('metadata', {})
        payments = data.get('payments', [])
        
        telegram_id = metadata.get('telegram_id')
        amount_usd = float(metadata.get('amount_usd', 0))
        crypto_amount = data.get('payments', [{}])[0].get('value', {}).get('local', {}).get('amount', 0) if payments else 0
        
        logger.info(f"Crypto payment confirmed: {charge_code} - ${amount_usd} - User: {telegram_id}")
        
        if not telegram_id:
            logger.error(f"No telegram_id in metadata for charge: {charge_code}")
            return jsonify({"status": "error"}), 200
        
        # Check if already processed
        existing = session.query(Transaction).filter_by(
            payment_reference=charge_code
        ).first()
        
        if existing:
            logger.info(f"Crypto payment already processed: {charge_code}")
            return jsonify({"status": "already_processed"}), 200
        
        # Create transaction
        transaction = Transaction(
            user_id=telegram_id,
            amount=amount_usd,
            type=TransactionType.CREDIT,
            status=TransactionStatus.COMPLETED,
            payment_method="crypto",
            payment_reference=charge_code,
            description=f"Crypto deposit - {amount_usd} USDT"
        )
        session.add(transaction)
        
        # Update user balance
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if user:
            user.balance += amount_usd
            session.commit()
            logger.info(f"Updated user {telegram_id} balance: +${amount_usd:.2f}")
            
            # Send notification
            notification = (
                f"✅ <b>Crypto Payment Received!</b>\n\n"
                f"Amount: <b>${amount_usd:.2f} USDT</b>\n"
                f"New balance: <b>${user.balance:.2f}</b>\n\n"
                f"Thank you for funding your wallet! 🎉"
            )
            send_telegram_notification(telegram_id, notification)
        
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error processing crypto payment: {e}")
        return jsonify({"status": "error"}), 200
    finally:
        session.close()

def handle_crypto_payment_failed(data):
    """Handle failed crypto payment"""
    charge_code = data.get('code')
    metadata = data.get('metadata', {})
    telegram_id = metadata.get('telegram_id')
    
    logger.error(f"Crypto payment failed: {charge_code} - User: {telegram_id}")
    
    # Notify user
    if telegram_id:
        notification = (
            f"❌ <b>Crypto Payment Failed</b>\n\n"
            f"Your crypto payment was not confirmed.\n"
            f"Please try again or contact support."
        )
        send_telegram_notification(telegram_id, notification)
    
    return jsonify({"status": "received"}), 200

def handle_crypto_payment_pending(data):
    """Handle pending crypto payment"""
    charge_code = data.get('code')
    logger.info(f"Crypto payment pending: {charge_code}")
    return jsonify({"status": "received"}), 200

# ==================== TELEGRAM WALLET (STARS) WEBHOOK ====================

@app.route('/webhook/telegram-wallet', methods=['POST'])
def telegram_wallet_webhook():
    """
    Handle Telegram Wallet (Stars) webhook
    """
    
    # Verify authorization
    auth_header = request.headers.get('Authorization')
    expected_token = app.config.get('TG_WALLET_TOKEN')
    
    if not expected_token:
        logger.warning("Telegram Wallet token not configured")
        return jsonify({"error": "Configuration error"}), 500
    
    if not auth_header or auth_header != f"Bearer {expected_token}":
        logger.warning("Telegram Wallet webhook: Invalid auth")
        return jsonify({"error": "Unauthorized"}), 401
    
    event = request.json
    event_type = event.get('type')
    data = event.get('data', {})
    
    logger.info(f"Telegram Wallet webhook received: {event_type}")
    
    if event_type == 'payment_success':
        return handle_tg_payment_success(data)
    elif event_type == 'payment_failed':
        return handle_tg_payment_failed(data)
    else:
        return jsonify({"status": "ignored"}), 200

def handle_tg_payment_success(data):
    """Handle successful Telegram Stars payment"""
    session = db_manager.get_session()
    
    try:
        payment_id = data.get('payment_id')
        amount_stars = data.get('amount', 0)
        metadata = data.get('metadata', {})
        
        telegram_id = metadata.get('telegram_id')
        # Convert stars to USD (1 star = ~$0.013)
        amount_usd = amount_stars * 0.013
        
        logger.info(f"TG Wallet payment: {payment_id} - {amount_stars} stars (${amount_usd:.2f}) - User: {telegram_id}")
        
        if not telegram_id:
            logger.error(f"No telegram_id in metadata: {payment_id}")
            return jsonify({"status": "error"}), 200
        
        # Check if already processed
        existing = session.query(Transaction).filter_by(
            payment_reference=payment_id
        ).first()
        
        if existing:
            return jsonify({"status": "already_processed"}), 200
        
        # Create transaction
        transaction = Transaction(
            user_id=telegram_id,
            amount=amount_usd,
            type=TransactionType.CREDIT,
            status=TransactionStatus.COMPLETED,
            payment_method="telegram_wallet",
            payment_reference=payment_id,
            description=f"Telegram Stars payment - {amount_stars} stars"
        )
        session.add(transaction)
        
        # Update user balance
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if user:
            user.balance += amount_usd
            session.commit()
            logger.info(f"Updated user via TG Wallet: +${amount_usd:.2f}")
            
            # Send notification
            notification = (
                f"✅ <b>Telegram Stars Payment Received!</b>\n\n"
                f"Stars: <b>{amount_stars} ⭐</b>\n"
                f"Amount: <b>${amount_usd:.2f}</b>\n"
                f"New balance: <b>${user.balance:.2f}</b>"
            )
            send_telegram_notification(telegram_id, notification)
        
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error processing TG payment: {e}")
        return jsonify({"status": "error"}), 200
    finally:
        session.close()

def handle_tg_payment_failed(data):
    """Handle failed Telegram Stars payment"""
    payment_id = data.get('payment_id')
    error = data.get('error', 'Unknown')
    
    logger.error(f"TG Wallet payment failed: {payment_id} - {error}")
    return jsonify({"status": "received"}), 200

# ==================== WEBHOOK STATUS ENDPOINT ====================

@app.route('/webhook/status', methods=['GET'])
def webhook_status():
    """Check webhook configuration status"""
    
    config_status = {
        "paystack": {
            "configured": bool(app.config.get('PAYSTACK_SECRET_KEY')),
            "webhook_url": "/webhook/paystack",
            "has_public_key": bool(app.config.get('PAYSTACK_PUBLIC_KEY'))
        },
        "coinbase": {
            "configured": bool(app.config.get('COINBASE_WEBHOOK_SECRET')),
            "webhook_url": "/webhook/coinbase",
            "has_api_key": bool(app.config.get('COINBASE_API_KEY'))
        },
        "telegram_wallet": {
            "configured": bool(app.config.get('TG_WALLET_TOKEN')),
            "webhook_url": "/webhook/telegram-wallet"
        }
    }
    
    return jsonify({
        "status": "active",
        "timestamp": datetime.utcnow().isoformat(),
        "webhooks": config_status,
        "environment": app.config.get('ENV', 'development')
    })

# ==================== ORDER MANAGEMENT ENDPOINTS ====================

@app.route('/api/orders/<int:telegram_id>', methods=['GET'])
def get_user_orders(telegram_id):
    """Get user's orders"""
    session = db_manager.get_session()
    try:
        limit = request.args.get('limit', 50, type=int)
        orders = session.query(Order).filter_by(
            user_id=telegram_id
        ).order_by(Order.created_at.desc()).limit(limit).all()
        
        return jsonify({
            "success": True,
            "orders": [
                {
                    "id": o.id,
                    "service_name": o.service_name,
                    "country_name": o.country_name,
                    "number": o.number,
                    "cost": o.cost,
                    "status": o.status.value if hasattr(o.status, 'value') else str(o.status),
                    "otp_code": o.otp_code,
                    "created_at": o.created_at.isoformat(),
                    "expires_at": o.expires_at.isoformat() if o.expires_at else None
                }
                for o in orders
            ]
        })
    except Exception as e:
        logger.error(f"Error getting orders: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        session.close()

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        "error": "Resource not found",
        "path": request.path
    }), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {error}")
    return jsonify({
        "error": "Internal server error",
        "message": str(error) if app.config['DEBUG'] else "An error occurred"
    }), 500

@app.errorhandler(429)
def rate_limit_error(error):
    """Handle rate limit errors"""
    return jsonify({
        "error": "Rate limit exceeded",
        "message": "Too many requests. Please try again later."
    }), 429

# ==================== RUN APP ====================

# At the end of api/app.py, make sure you have:
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    # Must bind to 0.0.0.0 for Railway
    app.run(host='0.0.0.0', port=port, debug=False)
