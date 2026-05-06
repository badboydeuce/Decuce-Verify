from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import hmac
import hashlib
import json
from datetime import datetime
from loguru import logger

load_dotenv()

app = Flask(__name__)
CORS(app)

from models.database import DatabaseManager, User, Transaction, TransactionType, TransactionStatus, Order
db_manager = DatabaseManager(os.getenv('DATABASE_URL'))

# ==================== HEALTH CHECK ====================
@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "DeuceVerify API",
        "timestamp": datetime.utcnow().isoformat()
    })

# ==================== PAYSTACK WEBHOOK (CORRECT IMPLEMENTATION) ====================
@app.route('/webhook/paystack', methods=['POST'])
def paystack_webhook():
    """
    Handle Paystack webhook events
    Documentation: https://paystack.com/docs/webhooks
    """
    
    # 1. Get the signature from headers
    signature = request.headers.get('x-paystack-signature')
    
    if not signature:
        logger.warning("No signature header found")
        return jsonify({"error": "No signature"}), 401
    
    # 2. Get raw payload
    payload = request.get_data(as_text=True)
    
    # 3. Verify signature using HMAC SHA512
    secret_key = os.getenv('PAYSTACK_SECRET_KEY')
    expected_signature = hmac.new(
        secret_key.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha512
    ).hexdigest()
    
    # 4. Compare signatures
    if not hmac.compare_digest(expected_signature, signature):
        logger.error(f"Invalid signature. Expected: {expected_signature}, Got: {signature}")
        return jsonify({"error": "Invalid signature"}), 401
    
    # 5. Parse event
    event = request.json
    event_type = event.get('event')
    data = event.get('data')
    
    logger.info(f"Webhook received: {event_type}")
    
    # 6. Process event based on type
    if event_type == 'charge.success':
        # Successful payment
        return handle_charge_success(data)
    
    elif event_type == 'transfer.success':
        # Successful transfer (refund)
        return handle_transfer_success(data)
    
    elif event_type == 'transfer.failed':
        # Failed transfer
        return handle_transfer_failed(data)
    
    elif event_type == 'refund.processed':
        # Refund processed
        return handle_refund_processed(data)
    
    elif event_type == 'charge.dispute.create':
        # Dispute created
        logger.warning(f"Dispute created for transaction: {data.get('transaction', {}).get('id')}")
        return jsonify({"status": "received"}), 200
    
    else:
        # Unknown event type - still return 200
        logger.info(f"Unhandled event type: {event_type}")
        return jsonify({"status": "ignored"}), 200

def handle_charge_success(data):
    """
    Handle successful charge webhook
    Event: charge.success
    """
    session = db_manager.get_session()
    
    try:
        # Extract data
        reference = data.get('reference')
        amount = data.get('amount', 0) / 100  # Convert from kobo to NGN
        currency = data.get('currency', 'NGN')
        customer = data.get('customer', {})
        metadata = data.get('metadata', {})
        
        telegram_id = metadata.get('telegram_id')
        email = customer.get('email')
        
        logger.info(f"Processing successful charge: {reference} - Amount: {amount} NGN - User: {telegram_id}")
        
        if not telegram_id:
            logger.error(f"No telegram_id in metadata for reference: {reference}")
            return jsonify({"status": "error", "message": "No user ID"}), 200
        
        # Find pending transaction
        transaction = session.query(Transaction).filter_by(
            payment_reference=reference,
            status=TransactionStatus.PENDING
        ).first()
        
        if not transaction:
            logger.warning(f"Transaction not found or already processed: {reference}")
            # Could be a new transaction, create it
            transaction = Transaction(
                user_id=telegram_id,
                amount=amount,
                type=TransactionType.CREDIT,
                status=TransactionStatus.COMPLETED,
                payment_method="paystack",
                payment_reference=reference,
                description=f"Payment via Paystack ({reference})"
            )
            session.add(transaction)
        else:
            # Update existing transaction
            transaction.status = TransactionStatus.COMPLETED
            transaction.completed_at = datetime.utcnow()
        
        # Update user balance
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if user:
            # Convert NGN to USD (assuming 1 USD = 1500 NGN)
            usd_amount = amount / 1500
            user.balance += usd_amount
            
            logger.info(f"Updated user {telegram_id} balance: +${usd_amount:.2f} (Total: ${user.balance:.2f})")
        else:
            # Create user if doesn't exist (shouldn't happen)
            user = User(
                telegram_id=telegram_id,
                email=email,
                balance=usd_amount
            )
            session.add(user)
            logger.info(f"Created new user from webhook: {telegram_id}")
        
        session.commit()
        
        # Send notification to user via Telegram (async)
        from bot.utils.helpers import send_balance_update
        send_balance_update(telegram_id, amount, user.balance)
        
        return jsonify({"status": "success", "message": "Balance updated"}), 200
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error processing charge.success: {e}")
        # Still return 200 to prevent retries
        return jsonify({"status": "error", "message": str(e)}), 200
    finally:
        session.close()

def handle_transfer_success(data):
    """
    Handle successful transfer (refund) webhook
    Event: transfer.success
    """
    session = db_manager.get_session()
    
    try:
        reference = data.get('reference')
        amount = data.get('amount', 0) / 100
        recipient = data.get('recipient', {})
        
        logger.info(f"Transfer successful: {reference} - Amount: {amount}")
        
        # Find related refund transaction
        transaction = session.query(Transaction).filter_by(
            payment_reference=reference
        ).first()
        
        if transaction:
            transaction.status = TransactionStatus.COMPLETED
            transaction.completed_at = datetime.utcnow()
            session.commit()
            logger.info(f"Refund transaction completed: {reference}")
        
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
    except Exception as e:
        logger.error(f"Error updating failed transaction: {e}")
    finally:
        session.close()
    
    return jsonify({"status": "received"}), 200

def handle_refund_processed(data):
    """Handle refund processed webhook"""
    reference = data.get('reference')
    amount = data.get('amount', 0) / 100
    
    logger.info(f"Refund processed: {reference} - Amount: {amount}")
    
    session = db_manager.get_session()
    try:
        # Update order status
        transaction = session.query(Transaction).filter_by(
            payment_reference=reference
        ).first()
        
        if transaction and transaction.order_id:
            order = session.query(Order).filter_by(id=transaction.order_id).first()
            if order:
                order.status = "refunded"
                session.commit()
                logger.info(f"Order {transaction.order_id} marked as refunded")
    except Exception as e:
        logger.error(f"Error updating refund status: {e}")
    finally:
        session.close()
    
    return jsonify({"status": "success"}), 200

# ==================== OTHER API ENDPOINTS ====================

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
                "currency": "USD"
            })
        return jsonify({"success": False, "error": "User not found"}), 404
    finally:
        session.close()

@app.route('/api/transactions/<int:telegram_id>', methods=['GET'])
def get_transactions(telegram_id):
    """Get user transaction history"""
    session = db_manager.get_session()
    try:
        transactions = session.query(Transaction).filter_by(
            user_id=telegram_id
        ).order_by(Transaction.created_at.desc()).limit(50).all()
        
        return jsonify({
            "success": True,
            "transactions": [
                {
                    "id": t.id,
                    "amount": t.amount,
                    "type": t.type.value,
                    "status": t.status.value,
                    "description": t.description,
                    "created_at": t.created_at.isoformat()
                }
                for t in transactions
            ]
        })
    finally:
        session.close()

@app.route('/api/create-payment', methods=['POST'])
def create_payment():
    """Initialize Paystack payment"""
    import requests
    
    data = request.json
    telegram_id = data.get('telegram_id')
    email = data.get('email', f"user{telegram_id}@deuceverify.com")
    amount_ngn = data.get('amount', 1000)  # Default 1000 NGN
    
    # Validate amount
    if amount_ngn < 500:
        return jsonify({"error": "Minimum amount is 500 NGN"}), 400
    if amount_ngn > 500000:
        return jsonify({"error": "Maximum amount is 500,000 NGN"}), 400
    
    # Create transaction record
    session = db_manager.get_session()
    try:
        reference = f"DV_{telegram_id}_{datetime.utcnow().timestamp()}"
        
        transaction = Transaction(
            user_id=telegram_id,
            amount=amount_ngn / 1500,  # Store in USD
            type=TransactionType.CREDIT,
            status=TransactionStatus.PENDING,
            payment_method="paystack",
            payment_reference=reference,
            description=f"Wallet funding - {amount_ngn} NGN"
        )
        session.add(transaction)
        session.commit()
        
        # Initialize Paystack transaction
        headers = {
            "Authorization": f"Bearer {os.getenv('PAYSTACK_SECRET_KEY')}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "email": email,
            "amount": amount_ngn * 100,  # Convert to kobo
            "currency": "NGN",
            "reference": reference,
            "callback_url": os.getenv('PAYSTACK_CALLBACK_URL', 'https://deuceverify.com/deposit'),
            "metadata": {
                "telegram_id": telegram_id,
                "purpose": "wallet_funding"
            }
        }
        
        response = requests.post(
            "https://api.paystack.co/transaction/initialize",
            json=payload,
            headers=headers
        )
        
        result = response.json()
        
        if result.get('status'):
            return jsonify({
                "success": True,
                "authorization_url": result['data']['authorization_url'],
                "reference": reference
            })
        else:
            return jsonify({"error": result.get('message', 'Payment initialization failed')}), 500
            
    except Exception as e:
        session.rollback()
        logger.error(f"Payment creation error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()

# ==================== IP WHITELISTING (OPTIONAL) ====================
PAYSTACK_IPS = [
    '52.31.139.75',
    '52.49.173.169', 
    '52.214.14.220'
]

@app.before_request
def whitelist_paystack_ips():
    """Optional: Whitelist Paystack IP addresses for webhook endpoint"""
    if request.path == '/webhook/paystack' and request.method == 'POST':
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        # Uncomment to enable IP whitelisting
        # if client_ip not in PAYSTACK_IPS:
        #     logger.warning(f"Blocked webhook from non-Paystack IP: {client_ip}")
        #     return jsonify({"error": "Forbidden"}), 403

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.getenv('DEBUG', 'False').lower() == 'true')
