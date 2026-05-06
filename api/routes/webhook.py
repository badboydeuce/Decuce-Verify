from flask import Blueprint, request, jsonify
from api.services.paystack import paystack
from database.crud import (
    get_user_by_telegram_id, update_balance, create_transaction,
    create_payment_transaction, update_payment_transaction
)
from database.db import SessionLocal
import logging

bp = Blueprint('webhook', __name__, url_prefix='/api/webhook')
logger = logging.getLogger(__name__)

@bp.route('/paystack', methods=['POST'])
def paystack_webhook():
    """Handle Paystack webhook events"""
    payload = request.get_data()
    signature = request.headers.get('x-paystack-signature')
    
    if not signature:
        return jsonify({"error": "No signature provided"}), 400
    
    # Verify and process webhook
    event_data = paystack.handle_webhook(payload, signature)
    if not event_data:
        return jsonify({"error": "Invalid signature"}), 401
    
    # Process successful charge
    if event_data.get("status") == "success":
        reference = event_data.get("reference")
        amount = event_data.get("amount") / 100  # Convert from kobo
        metadata = event_data.get("metadata", {})
        telegram_id = metadata.get("telegram_id")
        
        if telegram_id:
            db = SessionLocal()
            try:
                user = get_user_by_telegram_id(db, telegram_id)
                if user:
                    # Update balance
                    update_balance(db, user.id, amount, "credit")
                    
                    # Create transaction record
                    create_transaction(
                        db, user.id, amount, "credit", reference,
                        f"Wallet funding via Paystack"
                    )
                    
                    # Update payment transaction
                    update_payment_transaction(db, reference, "completed")
                    
                    logger.info(f"Wallet funded for user {telegram_id}: ₦{amount}")
            finally:
                db.close()
    
    return jsonify({"status": "success"}), 200
