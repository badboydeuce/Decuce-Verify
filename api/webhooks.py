# Payment webhooks
"""
Webhook handlers for DeuceVerify
Handles Paystack, Crypto (Coinbase), and Telegram Wallet webhooks
"""

from flask import Blueprint, request, jsonify, current_app
from datetime import datetime
import hmac
import hashlib
import json
import requests
from loguru import logger

# Create blueprint
bp = Blueprint('webhooks', __name__)

# ==================== PAYSTACK WEBHOOK ====================

@bp.route('/paystack', methods=['POST'])
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
    
    # Verify signature using HMAC SHA512
    secret_key = current_app.config.get('PAYSTACK_SECRET_KEY')
    if not secret_key:
        logger.error("Paystack secret key not configured")
        return jsonify({"error": "Configuration error"}), 500
    
    expected_signature = hmac.new(
        secret_key.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha512
    ).hexdigest()
    
    # Compare signatures
    if not hmac.compare_digest(expected_signature, signature):
        logger.error(f"Paystack webhook: Invalid signature")
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
    session = current_app.db_manager.get_session()
    
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
        
        from models.database import Transaction, TransactionStatus, TransactionType, User
        
        # Find or create transaction
        transaction = session.query(Transaction).filter_by(
            payment_reference=reference
        ).first()
        
        # Convert NGN to USD (1 USD = 1500 NGN)
        usd_amount = amount_ngn / 1500
        
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
            
            # Send notification to user via Telegram (async)
            try:
                from bot.utils.helpers import send_balance_update
                send_balance_update(telegram_id, usd_amount, user.balance)
            except Exception as e:
                logger.error(f"Failed to send Telegram notification: {e}")
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
    session = current_app.db_manager.get_session()
    
    try:
        reference = data.get('reference')
        amount = data.get('amount', 0) / 100
        recipient = data.get('recipient', {})
        
        logger.info(f"Transfer success: {reference} - ₦{amount}")
        
        from models.database import Transaction, TransactionStatus
        
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
    
    session = current_app.db_manager.get_session()
    
    try:
        from models.database import Transaction, TransactionStatus
        
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
    
    logger.info(f"Refund processed: {reference} - ₦{amount}")
    
    session = current_app.db_manager.get_session()
    
    try:
        from models.database import Transaction, Order
        
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


def handle_dispute_created(data):
    """Handle dispute created webhook"""
    transaction_id = data.get('transaction', {}).get('id')
    amount = data.get('transaction', {}).get('amount', 0) / 100
    
    logger.warning(f"Dispute created for transaction: {transaction_id} - Amount: ₦{amount}")
    
    # Notify admin
    try:
        from bot.utils.helpers import notify_admin
        notify_admin(f"⚠️ Dispute created for transaction {transaction_id}\nAmount: ₦{amount}")
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")
    
    return jsonify({"status": "received"}), 200


# ==================== COINBASE (CRYPTO) WEBHOOK ====================

@bp.route('/coinbase', methods=['POST'])
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
    webhook_secret = current_app.config.get('COINBASE_WEBHOOK_SECRET')
    if not webhook_secret:
        logger.error("Coinbase webhook secret not configured")
        return jsonify({"error": "Configuration error"}), 500
    
    expected_signature = hmac.new(
        webhook_secret.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(expected_signature, signature):
        logger.error("Coinbase webhook: Invalid signature")
        return jsonify({"error": "Invalid signature"}), 401
    
    # Parse event
    event = request.json
    event_type = event.get('type')
    data = event.get('data')
    
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
    session = current_app.db_manager.get_session()
    
    try:
        charge_code = data.get('code')
        metadata = data.get('metadata', {})
        payments = data.get('payments', [])
        
        telegram_id = metadata.get('telegram_id')
        amount_usd = float(metadata.get('amount_usd', 0))
        
        logger.info(f"Crypto payment confirmed: {charge_code} - ${amount_usd} - User: {telegram_id}")
        
        if not telegram_id:
            logger.error(f"No telegram_id in metadata for charge: {charge_code}")
            return jsonify({"status": "error"}), 200
        
        from models.database import Transaction, TransactionStatus, TransactionType, User
        
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
            try:
                from bot.utils.helpers import send_balance_update
                send_balance_update(telegram_id, amount_usd, user.balance)
            except Exception as e:
                logger.error(f"Failed to send notification: {e}")
        
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
    try:
        from bot.utils.helpers import send_payment_failed_notification
        send_payment_failed_notification(telegram_id, "crypto")
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")
    
    return jsonify({"status": "received"}), 200


def handle_crypto_payment_pending(data):
    """Handle pending crypto payment"""
    charge_code = data.get('code')
    logger.info(f"Crypto payment pending: {charge_code}")
    return jsonify({"status": "received"}), 200


# ==================== TELEGRAM WALLET (STARS) WEBHOOK ====================

@bp.route('/telegram-wallet', methods=['POST'])
def telegram_wallet_webhook():
    """
    Handle Telegram Wallet (Stars) webhook
    """
    
    # Verify authorization
    auth_header = request.headers.get('Authorization')
    expected_token = current_app.config.get('TG_WALLET_TOKEN')
    
    if not expected_token:
        logger.warning("Telegram Wallet token not configured")
        return jsonify({"error": "Configuration error"}), 500
    
    if not auth_header or auth_header != f"Bearer {expected_token}":
        logger.warning("Telegram Wallet webhook: Invalid auth")
        return jsonify({"error": "Unauthorized"}), 401
    
    event = request.json
    event_type = event.get('type')
    data = event.get('data')
    
    logger.info(f"Telegram Wallet webhook received: {event_type}")
    
    if event_type == 'payment_success':
        return handle_tg_payment_success(data)
    elif event_type == 'payment_failed':
        return handle_tg_payment_failed(data)
    else:
        return jsonify({"status": "ignored"}), 200


def handle_tg_payment_success(data):
    """Handle successful Telegram Stars payment"""
    session = current_app.db_manager.get_session()
    
    try:
        payment_id = data.get('payment_id')
        amount_stars = data.get('amount', 0)
        metadata = data.get('metadata', {})
        
        telegram_id = metadata.get('telegram_id')
        # Convert stars to USD (1 star = ~$0.01)
        amount_usd = amount_stars * 0.01
        
        logger.info(f"TG Wallet payment: {payment_id} - {amount_stars} stars (${amount_usd}) - User: {telegram_id}")
        
        if not telegram_id:
            logger.error(f"No telegram_id in metadata: {payment_id}")
            return jsonify({"status": "error"}), 200
        
        from models.database import Transaction, TransactionStatus, TransactionType, User
        
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


# ==================== TEST WEBHOOK ENDPOINTS ====================

@bp.route('/test/paystack', methods=['POST'])
def test_paystack_webhook():
    """
    Test endpoint for Paystack webhook (development only)
    """
    if current_app.config.get('ENV') == 'production':
        return jsonify({"error": "Not available in production"}), 403
    
    logger.info("Test Paystack webhook received")
    event = request.json
    logger.info(f"Test event: {event}")
    
    # Process as normal webhook
    return paystack_webhook()


@bp.route('/test/coinbase', methods=['POST'])
def test_coinbase_webhook():
    """
    Test endpoint for Coinbase webhook (development only)
    """
    if current_app.config.get('ENV') == 'production':
        return jsonify({"error": "Not available in production"}), 403
    
    logger.info("Test Coinbase webhook received")
    return coinbase_webhook()


# ==================== WEBHOOK STATUS CHECK ====================

@bp.route('/status', methods=['GET'])
def webhook_status():
    """Check webhook configuration status"""
    
    config_status = {
        "paystack": {
            "configured": bool(current_app.config.get('PAYSTACK_SECRET_KEY')),
            "webhook_url": "/webhook/paystack"
        },
        "coinbase": {
            "configured": bool(current_app.config.get('COINBASE_WEBHOOK_SECRET')),
            "webhook_url": "/webhook/coinbase"
        },
        "telegram_wallet": {
            "configured": bool(current_app.config.get('TG_WALLET_TOKEN')),
            "webhook_url": "/webhook/telegram-wallet"
        }
    }
    
    return jsonify({
        "status": "active",
        "webhooks": config_status,
        "environment": current_app.config.get('ENV', 'development')
    })
