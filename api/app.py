# Flask API
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import hmac
import hashlib
from datetime import datetime

load_dotenv()

app = Flask(__name__)
CORS(app)

from models.database import DatabaseManager, User, Transaction, TransactionType, TransactionStatus, Order, OrderStatus
db_manager = DatabaseManager(os.getenv('DATABASE_URL'))

# Health check
@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "DeuceVerify"})

# Get user balance
@app.route('/api/balance/<int:telegram_id>', methods=['GET'])
def get_balance(telegram_id):
    session = db_manager.get_session()
    try:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if user:
            return jsonify({"success": True, "balance": user.balance})
        return jsonify({"success": False, "error": "User not found"}), 404
    finally:
        session.close()

# Paystack webhook
@app.route('/api/webhook/paystack', methods=['POST'])
def paystack_webhook():
    signature = request.headers.get('x-paystack-signature')
    payload = request.get_data()
    
    expected = hmac.new(
        os.getenv('PAYSTACK_SECRET_KEY').encode(),
        payload,
        hashlib.sha512
    ).hexdigest()
    
    if not hmac.compare_digest(signature, expected):
        return jsonify({"error": "Invalid signature"}), 401
    
    event = request.json
    if event['event'] == 'charge.success':
        data = event['data']
        reference = data['reference']
        amount = data['amount'] / 100
        telegram_id = data['metadata']['telegram_id']
        
        session = db_manager.get_session()
        try:
            transaction = session.query(Transaction).filter_by(payment_reference=reference).first()
            if transaction and transaction.status == TransactionStatus.PENDING:
                transaction.status = TransactionStatus.COMPLETED
                user = session.query(User).filter_by(telegram_id=telegram_id).first()
                if user:
                    user.balance += amount
                    session.commit()
        except Exception as e:
            session.rollback()
        finally:
            session.close()
    
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
